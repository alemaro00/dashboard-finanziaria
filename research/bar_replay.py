"""Exploratory OHLC rule replay, NOT execution-quality validation or broker paper.

Models spread/impact at the next bar open with limit-price protection. Missing
quotes, corporate actions and event feeds remain explicit promotion blockers.
Microstructure/scalping is never run with this model.
"""
from collections import Counter
from datetime import datetime
from math import floor, isfinite
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

from .strategies import Bar, MarketFrame, Position, Quote, SPECS, StrategyContext, evaluate

NEW_YORK = ZoneInfo('America/New_York')
INTERVALS = {'1 min': 60, '5 mins': 300, '1 day': 86400}


def normalize(dataset, now):
    if not dataset.get('complete') or dataset.get('errors'):
        raise ValueError('Historical response incomplete')
    interval = INTERVALS[dataset['bar_size']]
    bars: list[Bar] = []
    for item in dataset['bars']:
        raw = item['date']
        if dataset['bar_size'] == '1 day':
            day = datetime.strptime(raw, '%Y%m%d').replace(hour=16, tzinfo=NEW_YORK)
            at = day.timestamp()
        else:
            at = float(raw) + interval
        # A still-forming bar is never available for a historical signal.
        if at > now:
            continue
        values = [float(item[k]) for k in ('open', 'high', 'low', 'close', 'volume')]
        o, h, low, close, volume = values
        if not all(isfinite(v) for v in values) or not (0 < low <= min(o, close) <= max(o, close) <= h) or volume < 0:
            raise ValueError('Invalid OHLC or volume')
        if bars and at <= bars[-1].timestamp:
            raise ValueError('Duplicate or unordered historical bars')
        bars.append(Bar(at, *values))
    return bars


def replay(strategy, datasets, now, cost_multiplier=1, out_of_sample=True, include_events=True,
           segment=None):
    if strategy in ('scalping', 'bitcoin'):
        return {'status': 'not_run', 'reason': 'Adequate tick/depth or BTC spot data unavailable'}
    spec = SPECS[strategy]
    selected = {d['symbol']: normalize(d, now) for d in datasets if d.get('strategy') == strategy}
    if not selected or any(len(bars) < spec.required_bars + 20 for bars in selected.values()):
        return {'status': 'not_run', 'reason': 'Insufficient closed historical bars'}
    if strategy == 'momentum' and set(selected) != {'SPY', 'QQQ', 'IWM', 'TLT', 'GLD'}:
        return {'status': 'not_run', 'reason': 'Complete point-in-time ETF universe required'}
    common = sorted(set.intersection(*(set(b.timestamp for b in bars) for bars in selected.values())))
    if segment is not None:
        if (not isinstance(segment, tuple) or len(segment) != 2
                or not all(isinstance(value, (int, float)) for value in segment)
                or not 0 <= segment[0] < segment[1] <= 1):
            raise ValueError('Invalid chronological segment')
        start = max(spec.required_bars, floor(len(common) * segment[0]))
        end = len(common) if segment[1] == 1 else floor(len(common) * segment[1])
    else:
        start = max(spec.required_bars, floor(len(common) * .7)) if out_of_sample else spec.required_bars
        end = len(common)
    if start >= end - 2:
        return {'status': 'not_run', 'reason': 'Insufficient holdout sample'}
    indexes = {symbol: {b.timestamp: index for index, b in enumerate(bars)} for symbol, bars in selected.items()}
    cash = 100000.0
    positions: dict[str, Any] = {}
    pending: dict[str, Any] = {}
    equity = []
    trades = []
    signals: Counter[str] = Counter()
    signal_events = []
    fees_total = 0.0
    cost_total = 0.0
    not_filled = 0
    peak = cash
    day_open = cash
    day = None
    daily_entries: Counter[str] = Counter()
    losses: Counter[str] = Counter()
    last_rebalance = None
    for at in common[start:end]:
        current = {s: selected[s][indexes[s][at]] for s in selected}
        date = datetime.fromtimestamp(at, NEW_YORK)
        day_key = date.date()
        if day_key != day:
            day, day_open = day_key, cash + sum(p['quantity'] * current[s].open for s, p in positions.items())
            daily_entries.clear()
        # Only proposals from a strictly earlier completed bar may execute here.
        for symbol, order in list(pending.items()):
            bar = current[symbol]
            is_buy = order['side'] == 'BUY'
            spread = .0003 * cost_multiplier
            impact = .001 * cost_multiplier
            price = bar.open * (1 + spread + impact if is_buy else 1 - spread - impact)
            qty = order['quantity']
            commission = max(1.0, qty * price * .001) * cost_multiplier
            crossing = price <= order['limit'] if is_buy else price >= order['limit']
            exposure = sum(p['quantity'] * current[s].open for s, p in positions.items())
            value = cash + exposure
            within_budget = (qty * price <= 2000 and exposure + qty * price <= min(10000, value * spec.max_weight)) if is_buy else True
            # All-or-none conservative bar model; do not invent partial fills from OHLC.
            if not crossing or qty > bar.volume * .001 or not within_budget or (is_buy and cash < qty * price + commission):
                not_filled += 1
                del pending[symbol]
                continue
            execution_cost = qty * abs(price - bar.open)
            if is_buy:
                cash -= qty * price + commission
                positions[symbol] = dict(quantity=qty, price=price, opened=at, high=max(price, bar.close),
                                         commission=commission, execution_cost=execution_cost)
                daily_entries[symbol] += 1
            elif symbol in positions:
                p = positions.pop(symbol)
                cash += qty * price - commission
                net = qty * (price - p['price']) - p['commission'] - commission
                trades.append({'symbol': symbol, 'opened': p['opened'], 'closed': at, 'net_pnl': net})
                losses[symbol] = losses[symbol] + 1 if net < 0 else 0
            fees_total += commission
            cost_total += execution_cost
            del pending[symbol]
        value = cash + sum(p['quantity'] * current[s].close for s, p in positions.items())
        peak = max(peak, value)
        equity.append((at, value))
        rebalance_key = (date.year, date.month)
        rebalance = last_rebalance != rebalance_key
        ranks = {}
        if strategy == 'momentum':
            scores = {s: current[s].close / selected[s][indexes[s][at] - 126].close - 1 for s in selected}
            ranks = {s: i + 1 for i, s in enumerate(sorted(scores, key=lambda s: (-scores[s], s)))}
        for symbol, bar in current.items():
            history = tuple(selected[symbol][max(0, indexes[symbol][at] - 200):indexes[symbol][at] + 1])
            position = positions.get(symbol)
            if position:
                position['high'] = max(position['high'], bar.close)
            position_state = Position(position['quantity'], position['price'], position['opened'], position['high']) if position else Position()
            # Synthetic quote and event-clear assumption for rule screening ONLY.
            # These cannot enter the broker or offline OMS and never pass quality gates.
            quote = Quote(at, bar.close * .9997, bar.close * 1.0003, max(1, bar.volume * .001),
                          max(1, bar.volume * .001), 0, 'modeled_from_bar_not_observed')
            seconds_to_close = max(0, (date.replace(hour=16, minute=0, second=0) - date).total_seconds())
            frame = MarketFrame(symbol, 'ETF' if strategy == 'momentum' else 'MEGA_CAP', 'USD', spec.timeframe,
                                history, quote, {'1m': 252 * 390, '5m': 252 * 78, '1d': 252}[spec.timeframe],
                                True, seconds_to_close if spec.timeframe != '1d' else 86400,
                                True, True, True, momentum_rank=ranks.get(symbol),
                                universe_size=len(selected) if ranks else None, rebalance_due=rebalance)
            context = StrategyContext(at, value, position_state, max(0, 1 - value / day_open), 0,
                                      max(0, 1 - value / peak), daily_entries[symbol], 0, losses[symbol], 0,
                                      True, True, True, estimated_roundtrip_bps=46 * cost_multiplier)
            result = evaluate(strategy, frame, context)
            signals[result.action + ':' + result.reason] += 1
            if include_events:
                signal_events.append({
                    'timestamp': at,
                    'symbol': symbol,
                    'action': result.action,
                    'reason': result.reason,
                    'price': bar.close,
                    'position_open': bool(position),
                })
            if result.action == 'ENTER' and not position and symbol not in pending:
                if result.limit_price is None:
                    raise ValueError('Entry without limit price')
                qty = floor(min(value * result.target_weight, 2000) / result.limit_price)
                if qty:
                    pending[symbol] = dict(side='BUY', quantity=qty, limit=result.limit_price)
            elif result.action == 'EXIT' and position and symbol not in pending:
                pending[symbol] = dict(side='SELL', quantity=position['quantity'], limit=result.limit_price)
        last_rebalance = rebalance_key
    high = 100000.0
    maximum_drawdown = 0.0
    for _, value in equity:
        high = max(high, value)
        maximum_drawdown = max(maximum_drawdown, 1 - value / high)
    history_observations = start
    test_observations = end - start
    return {'status': 'exploratory_only', 'source': 'ibkr_historical_bars_with_modeled_execution',
            'out_of_sample_holdout': out_of_sample, 'net_return': equity[-1][1] / 100000 - 1,
            'closed_trades': len(trades), 'net_realized_pnl': sum(t['net_pnl'] for t in trades),
            'expectancy_net': mean(t['net_pnl'] for t in trades) if trades else None,
            'maximum_drawdown': maximum_drawdown, 'commission': fees_total,
            'modeled_execution_cost': cost_total, 'unfilled': not_filled,
            'positions_open_at_end': len(positions), 'pending_at_end': len(pending),
            'start': common[start], 'end': common[end - 1], 'observations': len(equity),
            'sample_design': {
                'method': 'fixed_parameters_single_holdout' if out_of_sample else 'full_sample_diagnostic',
                'parameters_trained': False,
                'parameters_optimized': False,
                'separate_validation_segment': False,
                'total_common_observations': len(common),
                'history_observations': history_observations,
                'test_observations': test_observations,
                'history_fraction': history_observations / len(common),
                'test_fraction': test_observations / len(common),
                'requested_segment': list(segment) if segment is not None else ([.7, 1] if out_of_sample else [0, 1]),
                'required_warmup_bars': spec.required_bars,
                'test_start': common[start],
                'test_end': common[end - 1],
            },
            'signals': dict(signals), 'signal_events': signal_events,
            'paper_eligible': False, 'live_enabled': False,
            'limitations': ['Spread e slippage modellati; mancano bid/ask storici',
                            'Calendario eventi non applicato; corporate action non certificate',
                            'Fill da barre, non eseguiti IBKR; parametri non ottimizzati sul holdout',
                            'Posizioni residue valutate a close, non liquidate; nessuna prova di robustezza']}


def screen_all(datasets, now):
    results = []
    for strategy in SPECS:
        try:
            in_sample = replay(strategy, datasets, now, out_of_sample=False, segment=(0, .6))
            validation = replay(strategy, datasets, now, out_of_sample=False, segment=(.6, .8))
            out_of_sample = replay(strategy, datasets, now, out_of_sample=True, segment=(.8, 1))
            stress = replay(strategy, datasets, now, cost_multiplier=2, out_of_sample=True,
                            include_events=False, segment=(.8, 1))
            results.append({'strategy': strategy, 'baseline': out_of_sample,
                            'segments': {'in_sample': in_sample, 'validation': validation,
                                         'out_of_sample': out_of_sample},
                            'double_costs': stress,
                            'protocol': {'chronological_split': [60, 20, 20],
                                         'parameters_trained': False,
                                         'parameters_optimized': False,
                                         'selection_on_out_of_sample': False}})
        except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError) as error:
            results.append({'strategy': strategy, 'baseline': {'status': 'not_run', 'reason': str(error)},
                            'double_costs': {'status': 'not_run', 'reason': str(error)}})
    return results

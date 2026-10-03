"""Deterministic, offline research signals. No execution or promotion capability.

Input bars must be closed point-in-time observations; timestamps are Unix UTC.
All numbers are model inputs, never market data inferred by this module.
"""
from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from statistics import mean, pstdev
from typing import Optional, Tuple

NOTICE = ('Strategia con uno specifico profilo di rischio e potenziale rendimento, '
          'senza garanzia di risultato. Il capitale investito può subire perdite, anche rilevanti.')
BITCOIN_NOTICE = ('Bitcoin presenta elevata volatilità e può subire perdite rapide e rilevanti. '
                  'Questa strategia ha uno specifico profilo di rischio e un potenziale rendimento, '
                  'senza garanzia di risultato.')


@dataclass(frozen=True)
class StrategySpec:
    id: str
    name: str
    risk: str
    timeframe: str
    asset_types: Tuple[str, ...]
    max_weight: float
    target_vol: float
    risk_per_trade: float
    daily_loss_limit: float
    max_drawdown: float
    spread_bps: float
    max_age_seconds: float
    max_hold_seconds: float
    stop_atr: float
    max_entries: int
    required_bars: int


STRATEGIES = (
    StrategySpec('scalping', 'Micro-momentum controllato', 'alto operativo', 'tick',
                 ('ETF', 'LARGE_CAP', 'MEGA_CAP'), .03, .06, .0005, .002, .02, 3, 1, 120, 1.5, 10, 21),
    StrategySpec('mean_reversion', 'Ritorno alla media intraday', 'medio-alto', '1m',
                 ('ETF', 'LARGE_CAP', 'MEGA_CAP'), .10, .08, .001, .005, .05, 8, 5, 7200, 2, 3, 31),
    StrategySpec('breakout', 'Breakout di sessione', 'medio-alto', '5m',
                 ('ETF', 'LARGE_CAP', 'MEGA_CAP'), .10, .10, .0015, .005, .06, 8, 5, 23400, 2, 2, 21),
    StrategySpec('swing', 'Trend diversificato swing', 'medio', '1d',
                 ('ETF', 'LARGE_CAP', 'MEGA_CAP'), .20, .10, .002, .01, .10, 15, 30, 2592000, 3, 1, 61),
    StrategySpec('momentum', 'Momentum e riserva di liquidità', 'moderato', '1d',
                 ('ETF',), .25, .08, .002, .01, .10, 15, 30, 7776000, 3, 1, 127),
    StrategySpec('bitcoin', 'Bitcoin trend e regime', 'medio-alto/alto', '4h',
                 ('BTC_SPOT',), .05, .08, .001, .005, .08, 20, 5, 2419200, 3, 1, 61),
)
SPECS = {spec.id: spec for spec in STRATEGIES}


@dataclass(frozen=True)
class Bar:
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Quote:
    timestamp: float
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    latency_ms: float
    source: str  # 'tick_l2' required for microstructure; no OHLC proxy.


@dataclass(frozen=True)
class MarketFrame:
    symbol: str
    asset_type: str
    currency: str
    timeframe: str
    bars: Tuple[Bar, ...]
    quote: Quote
    annual_periods: float
    session_open: bool
    seconds_to_close: float
    data_complete: bool
    event_clear: bool
    risk_on: bool
    # Point-in-time daily trend for BTC, momentum ranking for ETF allocation.
    long_trend: Optional[bool] = None
    momentum_rank: Optional[int] = None
    universe_size: Optional[int] = None
    rebalance_due: bool = False
    micro_data_complete: bool = False


@dataclass(frozen=True)
class Position:
    quantity: float = 0
    entry_price: float = 0
    opened_at: float = 0
    high_water: float = 0


@dataclass(frozen=True)
class StrategyContext:
    now: float
    equity: float
    position: Position
    day_loss_fraction: float
    week_loss_fraction: float
    drawdown_fraction: float
    entries_this_session: int
    cancellations_this_session: int
    consecutive_losses: int
    cooldown_until: float
    connected: bool
    reconciled: bool
    enabled: bool
    bitcoin_permission: bool = False  # Separate local research consent, not broker permission.
    estimated_roundtrip_bps: float = 20


@dataclass(frozen=True)
class Signal:
    strategy_id: str
    symbol: str
    timestamp: float
    action: str
    reason: str
    target_weight: float = 0
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    validation_status: str = 'research_unvalidated'


def strategy_catalog():
    return [dict(asdict(spec), validation_status='research_unvalidated',
                 notice=NOTICE, bitcoin_notice=BITCOIN_NOTICE if spec.id == 'bitcoin' else None,
                 variants=['trend', 'breakout', 'multi_timeframe'] if spec.id == 'bitcoin' else [])
            for spec in STRATEGIES]


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _validate(frame, context, spec):
    q, p = frame.quote, context.position
    values = (context.now, context.equity, context.day_loss_fraction, context.week_loss_fraction,
              context.drawdown_fraction, context.cooldown_until, context.estimated_roundtrip_bps,
              p.quantity, p.entry_price, p.opened_at, p.high_water, frame.annual_periods,
              frame.seconds_to_close, q.timestamp, q.bid, q.ask, q.bid_size, q.ask_size, q.latency_ms)
    if not all(finite(v) and v >= 0 for v in values):
        return 'invalid_numeric_input'
    flags = (frame.session_open, frame.data_complete, frame.event_clear, frame.risk_on,
             frame.rebalance_due, frame.micro_data_complete, context.connected,
             context.reconciled, context.enabled, context.bitcoin_permission)
    if any(type(flag) is not bool for flag in flags):
        return 'invalid_boolean_input'
    if frame.long_trend is not None and type(frame.long_trend) is not bool:
        return 'invalid_trend_input'
    for count in (context.entries_this_session, context.cancellations_this_session, context.consecutive_losses):
        if type(count) is not int or count < 0:
            return 'invalid_count'
    if not frame.symbol or not frame.currency or frame.asset_type not in spec.asset_types:
        return 'instrument_not_allowed'
    if spec.id == 'bitcoin' and frame.symbol not in ('BTC', 'BTC/USD', 'BTC/EUR'):
        return 'bitcoin_spot_only'
    if spec.id != 'bitcoin' and frame.asset_type == 'BTC_SPOT':
        return 'bitcoin_requires_separate_strategy'
    if context.equity <= 0 or frame.annual_periods <= 0 or q.bid <= 0 or q.ask < q.bid:
        return 'invalid_market_state'
    if p.quantity > 0 and (p.entry_price <= 0 or p.high_water < p.entry_price or p.opened_at > context.now):
        return 'invalid_position_state'
    if not (context.connected and context.reconciled and frame.data_complete):
        return 'disconnected_incomplete_or_unreconciled'
    if not context.enabled:
        return 'strategy_paused'
    if frame.timeframe != spec.timeframe:
        return 'incorrect_timeframe'
    if q.timestamp > context.now or context.now - q.timestamp > spec.max_age_seconds:
        return 'stale_or_future_quote'
    if len(frame.bars) < spec.required_bars:
        return 'insufficient_history'
    previous = -1.0
    for bar in frame.bars:
        if not all(finite(v) for v in (bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume)):
            return 'invalid_bar'
        if not (previous < bar.timestamp <= context.now and bar.timestamp <= q.timestamp
                and 0 < bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
                and bar.volume >= 0):
            return 'invalid_or_future_bar'
        previous = bar.timestamp
    interval = {'tick': 1, '1m': 60, '5m': 300, '4h': 14400, '1d': 86400}[spec.timeframe]
    if context.now - frame.bars[-1].timestamp > interval * 4:
        return 'stale_history'
    if (q.ask - q.bid) / ((q.ask + q.bid) / 2) * 10000 > spec.spread_bps:
        return 'spread_limit'
    if min(q.bid_size, q.ask_size) * q.bid < 1000:
        return 'insufficient_displayed_liquidity'
    return None


def evaluate(strategy_id: str, frame: MarketFrame, context: StrategyContext,
             bitcoin_variant: str = 'trend') -> Signal:
    """Return a proposal only. BLOCKED never becomes an order, even for exits.

    Stop exits are instructions to a downstream risk-reviewed OMS; no guarantee of
    liquidation during outages, closed markets or unavailable quotes is implied.
    """
    spec = SPECS.get(strategy_id)
    if spec is None:
        raise ValueError('unknown_strategy')
    def signal(action, reason, weight=0, stop=None):
        return Signal(strategy_id, frame.symbol, context.now, action, reason, weight,
                      frame.quote.ask if action == 'ENTER' else frame.quote.bid if action == 'EXIT' else None,
                      stop)
    problem = _validate(frame, context, spec)
    if problem:
        return signal('BLOCKED', problem)
    if bitcoin_variant not in ('trend', 'breakout', 'multi_timeframe'):
        return signal('BLOCKED', 'unknown_bitcoin_variant')
    q, p, bars = frame.quote, context.position, frame.bars
    closes = [b.close for b in bars]
    price = closes[-1]
    returns = [closes[i] / closes[i-1] - 1 for i in range(1, len(closes))]
    vol = pstdev(returns[-20:]) * sqrt(frame.annual_periods)
    atr = mean(max(b.high-b.low, abs(b.high-a.close), abs(b.low-a.close))
               for a, b in zip(bars[-15:-1], bars[-14:]))
    stop_distance = max(spec.stop_atr * atr, price * .002)
    intraday = strategy_id in ('scalping', 'mean_reversion', 'breakout')
    loss_breach = (context.day_loss_fraction >= spec.daily_loss_limit
                   or context.drawdown_fraction >= spec.max_drawdown
                   or strategy_id == 'bitcoin' and context.week_loss_fraction >= .015)
    if p.quantity > 0:
        if loss_breach:
            return signal('EXIT', 'loss_limit_exit_proposal')
        if intraday and (not frame.session_open or frame.seconds_to_close <= 300):
            return signal('EXIT', 'session_end_exit_proposal')
        if context.now - p.opened_at >= spec.max_hold_seconds:
            return signal('EXIT', 'time_stop')
        if q.bid <= max(p.entry_price - stop_distance, p.high_water - stop_distance):
            return signal('EXIT', 'price_or_trailing_stop')
        if not frame.risk_on:
            return signal('EXIT', 'risk_off')
    if loss_breach:
        return signal('BLOCKED', 'loss_or_drawdown_limit')
    if not frame.session_open:
        return signal('BLOCKED', 'market_unavailable')
    if not frame.event_clear:
        return signal('BLOCKED', 'event_filter')
    if not frame.risk_on:
        return signal('HOLD', 'risk_off_cash')
    if intraday and frame.seconds_to_close <= 300:
        return signal('BLOCKED', 'no_entries_near_close')
    if not 0 < vol <= (1.0 if strategy_id == 'bitcoin' else .60):
        return signal('BLOCKED', 'volatility_missing_or_extreme')
    if context.cooldown_until > context.now or context.consecutive_losses >= 3:
        return signal('BLOCKED', 'cooldown_requires_review')
    enter, exit_condition = False, False
    if strategy_id == 'scalping':
        if q.source != 'tick_l2' or not frame.micro_data_complete:
            return signal('BLOCKED', 'tick_and_depth_required')
        if q.latency_ms > 100 or context.cancellations_this_session >= 20:
            return signal('BLOCKED', 'latency_or_cancellation_limit')
        imbalance = (q.bid_size-q.ask_size)/(q.bid_size+q.ask_size)
        momentum = price/closes[-6]-1
        enter = imbalance >= .30 and momentum * 10000 > context.estimated_roundtrip_bps * 2
        exit_condition = imbalance <= 0 or momentum <= 0
    elif strategy_id == 'mean_reversion':
        sample = bars[-31:-1]
        volume = sum(b.volume for b in sample)
        sd = pstdev([b.close for b in sample])
        if volume <= 0 or sd <= 0:
            return signal('BLOCKED', 'vwap_or_variance_unavailable')
        vwap = sum(b.close*b.volume for b in sample)/volume
        z = (price-vwap)/sd
        trend = abs(mean(closes[-6:-1])/mean(closes[-31:-1])-1)
        gap = abs(bars[-1].open/bars[-2].close-1)
        enter = z < -2 and trend < .003 and gap < .01 and bars[-1].volume >= mean(b.volume for b in sample)*.5
        exit_condition = z >= -.25
    elif strategy_id == 'breakout':
        # Explicit prior range prevents using the trigger's own high as the threshold.
        prior = bars[-21:-1]
        enter = (price > max(b.high for b in prior) + .1*atr
                 and bars[-1].volume > mean(b.volume for b in prior)*1.5
                 and bars[-1].high-bars[-1].low > atr)
        exit_condition = price < mean(closes[-6:-1])
    elif strategy_id == 'swing':
        fast, slow = mean(closes[-20:]), mean(closes[-60:])
        enter = price > fast > slow and price > max(b.high for b in bars[-21:-1])
        exit_condition = price < fast or fast <= slow
    elif strategy_id == 'momentum':
        if (type(frame.momentum_rank) is not int or type(frame.universe_size) is not int
                or not 1 <= frame.momentum_rank <= frame.universe_size):
            return signal('BLOCKED', 'point_in_time_universe_ranking_required')
        enter = (frame.rebalance_due and frame.momentum_rank <= min(3, frame.universe_size)
                 and price > mean(closes[-126:]) and price > closes[-127])
        exit_condition = frame.rebalance_due and (frame.momentum_rank > 3 or price < mean(closes[-126:]))
    else:
        if not context.bitcoin_permission:
            return signal('BLOCKED', 'separate_bitcoin_permission_required')
        if frame.long_trend is None:
            return signal('BLOCKED', 'point_in_time_daily_trend_required')
        trend = frame.long_trend and price > mean(closes[-60:])
        if bitcoin_variant == 'trend':
            enter = trend and mean(closes[-20:]) > mean(closes[-60:]) and price > closes[-21]
        elif bitcoin_variant == 'breakout':
            enter = trend and price > max(b.high for b in bars[-21:-1]) + .1*atr
        else:
            enter = trend and price > closes[-7] and price > closes[-43] and price > closes[-61]
        exit_condition = not trend or price < mean(closes[-20:])
    if p.quantity > 0:
        return signal('EXIT', 'signal_invalidated') if exit_condition else signal('HOLD', 'existing_position_no_averaging')
    if context.entries_this_session >= spec.max_entries:
        return signal('BLOCKED', 'entry_limit')
    if not enter:
        return signal('HOLD', 'entry_conditions_not_met')
    weight = min(spec.max_weight, spec.max_weight * spec.target_vol / vol,
                 spec.risk_per_trade / (stop_distance / price))
    return signal('ENTER', 'research_signal_requires_risk_review', weight, price-stop_distance)

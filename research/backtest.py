"""Offline execution research harness, not evidence of historical performance.

One instrument, long-only cash accounting; explicit point-in-time FX and costs.
Proposals can fill only on later observations after latency. Limit crossing is
necessary, never sufficient: volume, nonfill, outage and rejection scenarios apply.
No OHLC-only microstructure backtest is accepted.
"""
from dataclasses import dataclass
from math import sqrt
from random import Random
from statistics import mean, pstdev
from typing import Callable, Dict, Optional, Sequence, Tuple
from .strategies import finite


@dataclass(frozen=True)
class Observation:
    timestamp: float
    bid: float
    ask: float
    available_quantity: float
    fx_to_base: float
    available: bool = True
    reject: bool = False
    weekend: bool = False
    # Corporate actions must be normalized upstream; set False to reject unknown input.
    corporate_actions_normalized: bool = False


@dataclass(frozen=True)
class Proposal:
    id: str
    timestamp: float
    side: str
    quantity: float
    limit_price: float
    expires_at: float


@dataclass(frozen=True)
class Costs:
    commission_bps: float = 10
    minimum_commission: float = 1
    slippage_bps: float = 5
    impact_bps: float = 5
    latency_seconds: float = 1
    participation: float = .01
    nonfill_fraction: float = .25
    annual_cash_interest: float = 0
    annual_financing_rate: float = 0
    daily_data_cost: float = 0
    weekend_liquidity_multiplier: float = .5
    weekend_cost_multiplier: float = 2


@dataclass(frozen=True)
class Fill:
    proposal_id: str
    timestamp: float
    side: str
    quantity: float
    price: float
    fx_to_base: float
    commission: float
    slippage: float


@dataclass(frozen=True)
class BacktestResult:
    equity: Tuple[Tuple[float, float], ...]
    fills: Tuple[Fill, ...]
    statuses: Tuple[Tuple[str, str], ...]
    cash: float
    position: float
    costs: float
    provenance: str = 'synthetic_or_unvalidated_research_not_historical_performance'


def run(observations: Sequence[Observation], propose: Callable[[Tuple[Observation, ...]], Sequence[Proposal]],
        initial_cash: float, costs: Costs = Costs(), microstructure: bool = False,
        data_kind: str = 'quotes') -> BacktestResult:
    """Callback sees prefixes only; proposals must be stamped at that observation.

    Orders are DAY-like with caller's explicit expiry, no indefinite retries.
    Partial fills reserve no extra buying power: cash is checked at every fill.
    Research proposals are independent from broker-capable OMS messages.
    """
    if not finite(initial_cash) or initial_cash <= 0:
        raise ValueError('invalid_initial_cash')
    if microstructure and data_kind != 'tick_l2':
        raise ValueError('scalping_requires_tick_l2_not_ohlc')
    if data_kind not in ('quotes', 'tick_l2'):
        raise ValueError('quote_observations_required')
    if not all(finite(v) and v >= 0 for v in vars(costs).values()):
        raise ValueError('invalid_costs')
    if (not 0 < costs.participation <= 1 or not 0 <= costs.nonfill_fraction <= 1
            or not 0 <= costs.weekend_liquidity_multiplier <= 1 or costs.weekend_cost_multiplier < 1):
        raise ValueError('invalid_execution_constraints')
    previous = -1.0
    for obs in observations:
        values = (obs.timestamp, obs.bid, obs.ask, obs.available_quantity, obs.fx_to_base)
        if not all(finite(v) and v >= 0 for v in values):
            raise ValueError('invalid_observation')
        if obs.timestamp <= previous or obs.bid <= 0 or obs.ask < obs.bid or obs.fx_to_base <= 0:
            raise ValueError('unordered_or_invalid_quote')
        if any(type(v) is not bool for v in (obs.available, obs.reject, obs.weekend, obs.corporate_actions_normalized)):
            raise ValueError('invalid_observation_flags')
        if not obs.corporate_actions_normalized:
            raise ValueError('corporate_actions_unverified')
        previous = obs.timestamp
    cash, position, total_cost = initial_cash, 0.0, 0.0
    pending: Dict[str, Tuple[Proposal, float]] = {}
    seen, fills, statuses, equity = set(), [], [], []
    for index, obs in enumerate(observations):
        if index:
            days = (obs.timestamp-observations[index-1].timestamp)/86400
            fee = days*costs.daily_data_cost
            cash += max(0, cash)*costs.annual_cash_interest*days/365.25-fee
            total_cost += fee
        # A shared liquidity budget prevents multiple simultaneous orders each consuming the full book.
        remaining_liquidity = (obs.available_quantity * costs.participation * (1-costs.nonfill_fraction)
                               * (costs.weekend_liquidity_multiplier if obs.weekend else 1))
        for key, (order, remaining) in list(pending.items()):
            if obs.timestamp > order.expires_at:
                statuses.append((key, 'expired_unfilled' if remaining == order.quantity else 'expired_partial'))
                del pending[key]
                continue
            if obs.timestamp <= order.timestamp or obs.timestamp-order.timestamp < costs.latency_seconds:
                continue
            if not obs.available:
                continue
            if obs.reject:
                statuses.append((key, 'rejected_scenario'))
                del pending[key]
                continue
            multiplier = costs.weekend_cost_multiplier if obs.weekend else 1
            adverse = (costs.slippage_bps+costs.impact_bps)*multiplier/10000
            touch = obs.ask if order.side == 'BUY' else obs.bid
            price = touch*(1+adverse if order.side == 'BUY' else 1-adverse)
            if price <= 0 or (order.side == 'BUY' and price > order.limit_price) or (order.side == 'SELL' and price < order.limit_price):
                continue
            quantity = min(remaining, remaining_liquidity)
            unit_base = price*obs.fx_to_base
            if order.side == 'BUY':
                # Each partial fill conservatively incurs minimum commission.
                quantity = min(quantity, max(0, (cash-costs.minimum_commission)/(unit_base*(1+costs.commission_bps*multiplier/10000))))
            else:
                quantity = min(quantity, position)
            if quantity <= 1e-12:
                continue
            commission = max(costs.minimum_commission, quantity*unit_base*costs.commission_bps*multiplier/10000)
            if order.side == 'BUY':
                cash -= quantity*unit_base+commission
                position += quantity
            else:
                # No short positions or fee financing are permitted.
                if cash+quantity*unit_base < commission:
                    continue
                cash += quantity*unit_base-commission
                position -= quantity
            slippage = quantity*abs(price-touch)*obs.fx_to_base
            total_cost += commission+slippage
            fills.append(Fill(key, obs.timestamp, order.side, quantity, price, obs.fx_to_base, commission, slippage))
            remaining_liquidity -= quantity
            remaining -= quantity
            if remaining <= 1e-10:
                statuses.append((key, 'filled'))
                del pending[key]
            else:
                statuses.append((key, 'partial'))
                pending[key] = (order, remaining)
        proposals = propose(tuple(observations[:index+1]))
        for proposal in proposals:
            if not isinstance(proposal, Proposal):
                raise ValueError('invalid_proposal_type')
            if (not proposal.id or proposal.id in seen or proposal.side not in ('BUY', 'SELL')
                    or not all(finite(v) for v in (proposal.timestamp, proposal.quantity, proposal.limit_price, proposal.expires_at))
                    or proposal.quantity <= 0 or proposal.limit_price <= 0 or proposal.timestamp != obs.timestamp
                    or proposal.expires_at <= proposal.timestamp):
                raise ValueError('invalid_or_duplicate_proposal')
            seen.add(proposal.id)
            pending[proposal.id] = (proposal, proposal.quantity)
        # Liquidation mark at bid; no synthetic closing fill is inserted at the final point.
        equity.append((obs.timestamp, cash+position*obs.bid*obs.fx_to_base))
    statuses.extend((key, 'open_at_end') for key in pending)
    return BacktestResult(tuple(equity), tuple(fills), tuple(statuses), cash, position, total_cost)


def metrics(equity: Sequence[Tuple[float, float]], periods_per_year: float,
            roundtrip_pnl: Sequence[float] = (), turnover: Optional[float] = None,
            benchmark_returns: Optional[Sequence[float]] = None) -> Dict[str, Optional[float]]:
    """Ratios use zero risk-free/MAR; undefined statistics return None, never infinity.

    Equity must be uniformly sampled for volatility and ratios. CAGR uses elapsed UTC
    time. Realized round trips must include all trading/FX costs, supplied explicitly.
    """
    if not finite(periods_per_year) or periods_per_year <= 0:
        raise ValueError('invalid_annualization')
    if len(equity) < 2:
        raise ValueError('insufficient_equity')
    times, values = zip(*equity)
    if not all(finite(v) for v in times+values) or min(values) <= 0:
        raise ValueError('invalid_equity')
    steps = [b-a for a, b in zip(times, times[1:])]
    if min(steps) <= 0 or max(steps)-min(steps) > max(steps)*1e-6:
        raise ValueError('equity_requires_uniform_sampling')
    expected = 365.25*86400/periods_per_year
    # Trading-session daily sampling may exclude non-trading days, but callers must
    # resample explicitly: this harness uses elapsed uniformly spaced UTC intervals.
    if abs(mean(steps)-expected) > expected*.01:
        raise ValueError('annualization_does_not_match_timestamps')
    if not all(finite(v) for v in roundtrip_pnl):
        raise ValueError('invalid_roundtrip_pnl')
    if turnover is not None and (not finite(turnover) or turnover < 0):
        raise ValueError('invalid_turnover')
    returns = [b/a-1 for a, b in zip(values, values[1:])]
    volatility = pstdev(returns)*sqrt(periods_per_year)
    downside = sqrt(mean(min(0, r)**2 for r in returns))*sqrt(periods_per_year)
    annual_mean = mean(returns)*periods_per_year
    years = (times[-1]-times[0])/(365.25*86400)
    cagr = (values[-1]/values[0])**(1/years)-1 if years >= 1/365.25 else None
    high, max_dd, underwater_since, recovery = values[0], 0.0, None, 0.0
    high_timestamp = times[0]
    for timestamp, value in equity:
        if value >= high:
            if underwater_since is not None:
                recovery = max(recovery, timestamp-underwater_since)
            high, underwater_since = value, None
            high_timestamp = timestamp
        else:
            underwater_since = high_timestamp if underwater_since is None else underwater_since
            max_dd = max(max_dd, 1-value/high)
    wins, losses = [v for v in roundtrip_pnl if v > 0], [v for v in roundtrip_pnl if v < 0]
    benchmark_corr = None
    if benchmark_returns is not None:
        if len(benchmark_returns) != len(returns) or not all(finite(v) for v in benchmark_returns):
            raise ValueError('invalid_benchmark_alignment')
        denominator = pstdev(returns)*pstdev(benchmark_returns)
        if denominator:
            benchmark_corr = mean((a-mean(returns))*(b-mean(benchmark_returns))
                                  for a, b in zip(returns, benchmark_returns))/denominator
    return {
        'net_cagr': cagr, 'annualized_arithmetic_return': annual_mean,
        'annualized_volatility': volatility, 'sharpe_zero_rf': annual_mean/volatility if volatility else None,
        'sortino_zero_mar': annual_mean/downside if downside else None,
        'max_drawdown': max_dd, 'calmar': cagr/max_dd if max_dd and cagr is not None else None,
        'max_completed_recovery_seconds': recovery,
        'current_underwater_seconds': times[-1]-underwater_since if underwater_since is not None else 0,
        'profit_factor': sum(wins)/abs(sum(losses)) if losses else None,
        'expectancy': mean(roundtrip_pnl) if roundtrip_pnl else None,
        'win_rate': len(wins)/len(roundtrip_pnl) if roundtrip_pnl else None,
        'average_win_loss_ratio': mean(wins)/abs(mean(losses)) if wins and losses else None,
        'turnover': turnover, 'benchmark_correlation': benchmark_corr,
    }


def walk_forward_windows(size: int, train: int, validation: int, out_of_sample: int, embargo: int = 1):
    """Disjoint test folds with explicit embargo; no parameter selection on test folds."""
    if any(type(v) is not int or v < 1 for v in (size, train, validation, out_of_sample, embargo)):
        raise ValueError('invalid_window')
    result = []
    start = 0
    while start+train+validation+out_of_sample+2*embargo <= size:
        valid_start = start+train+embargo
        test_start = valid_start+validation+embargo
        result.append(((start, start+train), (valid_start, valid_start+validation),
                       (test_start, test_start+out_of_sample)))
        start += out_of_sample
    return result


def bootstrap_drawdowns(returns: Sequence[float], simulations: int = 100, block_size: int = 5, seed: int = 0):
    """Seeded moving-block scenarios, not a historical return estimate or guarantee."""
    if not returns or any(not finite(r) or r <= -1 for r in returns):
        raise ValueError('invalid_returns')
    if type(simulations) is not int or not 1 <= simulations <= 10000 or type(block_size) is not int or not 1 <= block_size <= len(returns):
        raise ValueError('invalid_bootstrap_size')
    rng, outcomes = Random(seed), []
    for _ in range(simulations):
        sample: list[float] = []
        while len(sample) < len(returns):
            start = rng.randrange(len(returns)-block_size+1)
            sample.extend(returns[start:start+block_size])
        value, high, drawdown = 1.0, 1.0, 0.0
        for r in sample[:len(returns)]:
            value *= 1+r
            high = max(high, value)
            drawdown = max(drawdown, 1-value/high)
        outcomes.append(drawdown)
    return tuple(outcomes)

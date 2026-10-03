"""Evidence quality and statistical diagnostics, never a live-trading permission.

Closed-trade P/L must already include execution costs. Bootstrap intervals describe
the supplied sample; they are not probabilities of future profitability.
"""
from dataclasses import dataclass
from math import sqrt
from random import Random
from statistics import mean
from typing import Tuple

from .strategies import SPECS, finite


@dataclass(frozen=True)
class TradeResult:
    id: str
    opened_at: float
    closed_at: float
    gross_pnl: float
    commission: float
    execution_cost: float

    @property
    def net(self):
        return self.gross_pnl - self.commission - self.execution_cost


@dataclass(frozen=True)
class Evidence:
    strategy: str
    source: str
    strategy_hash: str
    dataset_hash: str
    trades: Tuple[TradeResult, ...] = ()
    equity: Tuple[Tuple[float, float], ...] = ()
    # Trading sessions actually observed, not elapsed wall-clock days.
    observed_sessions: int = 0
    reconciliation_complete: bool = False
    costs_complete: bool = False
    data_quality_verified: bool = False
    independent_oos_passed: bool = False
    stress_tests_passed: bool = False


MINIMUMS = {
    'scalping': (200, 60), 'mean_reversion': (100, 60),
    'breakout': (100, 60), 'swing': (40, 126),
    'momentum': (24, 252), 'bitcoin': (60, 180),
}


def _validate(evidence):
    if evidence.strategy not in SPECS:
        raise ValueError('Unknown strategy')
    if evidence.source not in ('synthetic', 'historical_research', 'shadow', 'ibkr_paper'):
        raise ValueError('Unknown evidence source')
    for value in (evidence.strategy_hash, evidence.dataset_hash):
        if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('SHA256 provenance required')
    if type(evidence.observed_sessions) is not int or evidence.observed_sessions < 0:
        raise ValueError('Invalid session count')
    for flag in (evidence.reconciliation_complete, evidence.costs_complete,
                 evidence.data_quality_verified, evidence.independent_oos_passed,
                 evidence.stress_tests_passed):
        if type(flag) is not bool:
            raise ValueError('Boolean evidence flags required')
    ids = set()
    previous = -1.0
    for trade in evidence.trades:
        if not trade.id or trade.id in ids:
            raise ValueError('Duplicate or missing execution identity')
        ids.add(trade.id)
        values = (trade.opened_at, trade.closed_at, trade.gross_pnl, trade.commission, trade.execution_cost)
        if not all(finite(v) for v in values) or trade.opened_at < 0 or trade.closed_at <= trade.opened_at:
            raise ValueError('Invalid trade or time')
        if trade.commission < 0 or trade.execution_cost < 0 or trade.closed_at < previous:
            raise ValueError('Invalid costs or unordered trade history')
        previous = trade.closed_at
    previous = -1.0
    for at, value in evidence.equity:
        if not finite(at) or not finite(value) or at < 0 or at <= previous or value <= 0:
            raise ValueError('Invalid equity series')
        previous = at
    if evidence.equity and evidence.trades:
        if evidence.equity[0][0] > min(t.opened_at for t in evidence.trades) or evidence.equity[-1][0] < evidence.trades[-1].closed_at:
            raise ValueError('Equity does not cover trade sample')


def wilson_interval(wins, count):
    if not count:
        return None
    z = 1.959963984540054
    p = wins / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    width = z * sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / denominator
    return [max(0, center - width), min(1, center + width)]


def expectancy_interval(values):
    if len(values) < 20:
        return None
    # Circular block bootstrap retains some serial dependence; not IID win-rate inference.
    random = Random(419)
    size = max(2, int(sqrt(len(values))))
    means = []
    for _ in range(1000):
        sample: list[float] = []
        while len(sample) < len(values):
            start = random.randrange(len(values))
            sample.extend(values[(start + n) % len(values)] for n in range(size))
        means.append(mean(sample[:len(values)]))
    means.sort()
    return [means[24], means[974]]


def assess(evidence: Evidence):
    _validate(evidence)
    trades = evidence.trades
    net = [t.net for t in trades]
    positive = sum(max(0, value) for value in net)
    negative = -sum(min(0, value) for value in net)
    interval = expectancy_interval(net)
    drawdown = None
    if len(evidence.equity) >= 2:
        peak = evidence.equity[0][1]
        drawdown = 0.0
        for _, value in evidence.equity:
            peak = max(peak, value)
            drawdown = max(drawdown, (peak - value) / peak)
    minimum_trades, minimum_sessions = MINIMUMS[evidence.strategy]
    checks = {
        'broker_paper_observed': evidence.source == 'ibkr_paper',
        'sample_size': len(trades) >= minimum_trades,
        'observation_period': evidence.observed_sessions >= minimum_sessions,
        'costs_complete': evidence.costs_complete,
        'data_quality': evidence.data_quality_verified,
        'reconciliation': evidence.reconciliation_complete,
        'out_of_sample': evidence.independent_oos_passed,
        'stress_tests': evidence.stress_tests_passed,
        'net_positive': bool(net) and sum(net) > 0,
        'expectancy_lower_bound_positive': interval is not None and interval[0] > 0,
        'drawdown_within_limit': drawdown is not None and drawdown <= SPECS[evidence.strategy].max_drawdown,
        'double_costs_positive': bool(trades) and sum(t.gross_pnl - 2 * (t.commission + t.execution_cost) for t in trades) > 0,
        # One exceptional trade must not explain all profits.
        'profit_not_one_trade': len(net) > 1 and sum(net) - max(net) > 0,
    }
    return {
        'strategy': evidence.strategy, 'source': evidence.source,
        'status': 'ready_for_independent_review' if all(checks.values()) else 'insufficient_evidence',
        'live_enabled': False, 'automatic_promotion': False,
        'strategy_hash': evidence.strategy_hash, 'dataset_hash': evidence.dataset_hash,
        'closed_trades': len(trades), 'observed_sessions': evidence.observed_sessions,
        'minimum_trades': minimum_trades, 'minimum_sessions': minimum_sessions,
        'net_pnl': sum(net) if net else None,
        'expectancy_net': mean(net) if net else None,
        'expectancy_interval_95': interval,
        'win_rate': sum(v > 0 for v in net) / len(net) if net else None,
        'win_rate_interval_95': wilson_interval(sum(v > 0 for v in net), len(net)),
        'profit_factor': positive / negative if negative else None,
        'maximum_drawdown': drawdown,
        'checks': checks, 'blockers': [key for key, passed in checks.items() if not passed],
        'interpretation': 'Intervalli sul campione osservato, non probabilità di guadagno futuro. Soglie di ricerca, non certificazione.',
    }

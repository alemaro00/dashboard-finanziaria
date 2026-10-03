"""Unlevered research capital allocation; never authorizes an order.

A complete correlation matrix and explicit existing exposures are mandatory.
Unknown inputs reject the allocation rather than implying zero risk.
"""
from dataclasses import dataclass
from math import sqrt
from typing import Dict, Mapping, Sequence, Tuple
from .strategies import SPECS, finite


@dataclass(frozen=True)
class Profile:
    exposure: float
    target_volatility: float
    drawdown_limit: float
    max_strategies: int
    currency_cap: float
    sector_cap: float
    strategies: Tuple[str, ...]


PROFILES = {
    'conservative': Profile(.35, .05, .06, 2, .35, .25, ('momentum', 'swing')),
    'balanced': Profile(.60, .08, .10, 4, .50, .35, ('momentum', 'swing', 'mean_reversion', 'breakout')),
    'dynamic': Profile(.80, .12, .12, 6, .60, .40, tuple(SPECS)),
}


@dataclass(frozen=True)
class Candidate:
    strategy_id: str
    annual_volatility: float
    drawdown: float
    capacity: float  # Maximum research currency amount sustainable in the scenario.
    liquidity_capacity: float
    currency: str
    sector: str
    validated: bool = False
    risk_on: bool = False


@dataclass(frozen=True)
class Allocation:
    amounts: Dict[str, float]
    cash: float
    estimated_volatility: float
    status: str
    reason: str


def _psd(matrix):
    """LDL factorization also supports semidefinite perfect correlations."""
    n = len(matrix)
    lower = [[0.0] * n for _ in range(n)]
    diagonal = [0.0] * n
    for i in range(n):
        lower[i][i] = 1
        diagonal[i] = matrix[i][i] - sum(lower[i][k] ** 2 * diagonal[k] for k in range(i))
        if diagonal[i] < -1e-9:
            return False
        for j in range(i+1, n):
            residual = matrix[j][i] - sum(lower[j][k]*lower[i][k]*diagonal[k] for k in range(i))
            if abs(diagonal[i]) < 1e-9:
                if abs(residual) > 1e-8:
                    return False
            else:
                lower[j][i] = residual / diagonal[i]
    return True


def allocate(candidates: Sequence[Candidate], correlations: Mapping[Tuple[str, str], float],
             profile: str, capital: float, available_cash: float,
             existing_by_currency: Mapping[str, float], existing_by_sector: Mapping[str, float],
             existing_exposure: float = 0, account_drawdown: float = 0) -> Allocation:
    """Incremental proposal in account base currency, no FX conversion implicit.

    Unvalidated candidates receive zero. Scenario tests can explicitly mark
    synthetic candidate inputs validated; this is not a promotion gate.
    Existing holdings consume caps. The estimate includes worst-case existing
    volatility of 100% annualized, because no covariance of holdings is supplied.
    """
    def blocked(reason):
        return Allocation({}, available_cash if finite(available_cash) and available_cash >= 0 else 0,
                          0, 'blocked', reason)
    if profile not in PROFILES:
        return blocked('unknown_profile')
    cfg = PROFILES[profile]
    if not all(finite(v) and v >= 0 for v in (capital, available_cash, existing_exposure, account_drawdown)):
        return blocked('invalid_account_input')
    if capital <= 0 or available_cash > capital or existing_exposure + available_cash > capital + 1e-8:
        return blocked('inconsistent_account_equity')
    if existing_by_currency is None or existing_by_sector is None:
        return blocked('missing_exposure_breakdown')
    for breakdown in (existing_by_currency, existing_by_sector):
        if any(not k or not finite(v) or v < 0 for k, v in breakdown.items()):
            return blocked('invalid_exposure_breakdown')
        if abs(sum(breakdown.values()) - existing_exposure) > 1e-6:
            return blocked('incomplete_exposure_breakdown')
    if account_drawdown >= cfg.drawdown_limit or existing_exposure >= cfg.exposure*capital:
        return blocked('account_limit')
    ids = [item.strategy_id for item in candidates]
    if len(set(ids)) != len(ids) or any(key not in SPECS for key in ids):
        return blocked('unknown_or_duplicate_strategy')
    matrix = []
    for a in ids:
        row = []
        for b in ids:
            rho = correlations.get((a, b))
            if rho is None or not finite(rho) or not -1 <= rho <= 1:
                return blocked('missing_or_invalid_correlation')
            if (not finite(correlations.get((b, a))) or (a == b and abs(rho-1) > 1e-9)
                    or abs(rho-correlations[(b, a)]) > 1e-9):
                return blocked('inconsistent_correlation')
            row.append(rho)
        matrix.append(row)
    if not _psd(matrix):
        return blocked('correlation_not_positive_semidefinite')
    for item in candidates:
        if (not all(finite(v) and v >= 0 for v in (item.annual_volatility, item.drawdown, item.capacity, item.liquidity_capacity))
                or item.annual_volatility <= 0 or not item.currency or not item.sector
                or type(item.validated) is not bool or type(item.risk_on) is not bool):
            return blocked('invalid_candidate')
    eligible = [c for c in candidates if c.strategy_id in cfg.strategies and c.validated and c.risk_on
                and c.drawdown < min(cfg.drawdown_limit, SPECS[c.strategy_id].max_drawdown)]
    eligible.sort(key=lambda c: (c.annual_volatility, c.strategy_id))
    eligible = eligible[:cfg.max_strategies]
    if not eligible:
        return Allocation({}, available_cash, 0, 'cash', 'no_validated_eligible_strategies')
    budget = min(available_cash, cfg.exposure*capital - existing_exposure)
    inverse_sum = sum(1 / c.annual_volatility for c in eligible)
    amounts = {}
    currencies, sectors = dict(existing_by_currency), dict(existing_by_sector)
    for candidate in eligible:
        key = candidate.strategy_id
        amount = max(0, min(budget / candidate.annual_volatility / inverse_sum,
                            candidate.capacity, candidate.liquidity_capacity,
                            SPECS[key].max_weight*capital,
                            cfg.currency_cap*capital-currencies.get(candidate.currency, 0),
                            cfg.sector_cap*capital-sectors.get(candidate.sector, 0)))
        amounts[key] = amount
        currencies[candidate.currency] = currencies.get(candidate.currency, 0)+amount
        sectors[candidate.sector] = sectors.get(candidate.sector, 0)+amount
    # Ignore diversification benefit from negative correlations conservatively.
    variance = sum(amounts[a.strategy_id]/capital * amounts[b.strategy_id]/capital
                   * a.annual_volatility * b.annual_volatility
                   * max(0, correlations[(a.strategy_id, b.strategy_id)]) for a in eligible for b in eligible)
    risk_left = max(0, cfg.target_volatility-existing_exposure/capital)
    risk = sqrt(max(0, variance))
    scale = min(1, risk_left/risk) if risk > 0 else 0
    amounts = {key: value*scale for key, value in amounts.items()}
    return Allocation(amounts, available_cash-sum(amounts.values()),
                      risk*scale + existing_exposure/capital, 'research_proposal', 'requires_account_risk_review')

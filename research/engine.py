"""Transactional offline execution laboratory; deliberately no broker/network path.

Not a multi-tenant production OMS. Money uses Decimal; persisted figures use strings.
Every public order submission/fill is guarded and committed with its audit event.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
from .strategies import SPECS

TENANT = 'local-research'
STRATEGIES = ('scalping', 'mean_reversion', 'breakout', 'swing', 'momentum', 'bitcoin')
ASSETS = {'SPY': 'ETF', 'QQQ': 'ETF', 'IWM': 'ETF', 'TLT': 'ETF', 'GLD': 'ETF',
          'AAPL': 'STK', 'MSFT': 'STK', 'BTC': 'CRYPTO_SPOT'}
ACTIVE = ('accepted', 'partial')
WARNING = 'Strategia con uno specifico profilo di rischio e potenziale rendimento, senza garanzia di risultato. Il capitale investito può subire perdite, anche rilevanti.'


def decimal(value, positive=False):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a monetary value')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid decimal') from None
    if not result.is_finite() or result < 0 or (positive and result == 0) or result > Decimal('1e15'):
        raise ValueError('Expected finite nonnegative decimal in supported range')
    return result


def timestamp(value):
    result = float(value)
    if isinstance(value, bool) or not math.isfinite(result) or result < 0:
        raise ValueError('Invalid timestamp')
    return result


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, default=str)


@dataclass(frozen=True)
class Order:
    key: str
    strategy: str
    symbol: str
    side: str
    quantity: Decimal
    limit: Decimal
    currency: str = 'USD'
    account: str = TENANT

    def __post_init__(self):
        if not isinstance(self.key, str) or not 1 <= len(self.key) <= 100:
            raise ValueError('Idempotency key required')
        if self.strategy not in STRATEGIES or self.symbol not in ASSETS:
            raise ValueError('Strategy or instrument not allowlisted')
        if (self.symbol == 'BTC') != (self.strategy == 'bitcoin'):
            raise ValueError('Bitcoin requires its separate strategy; substitutions forbidden')
        if self.strategy == 'momentum' and ASSETS[self.symbol] != 'ETF':
            raise ValueError('Momentum strategy admits ETFs only')
        if self.side not in ('BUY', 'SELL') or self.account != TENANT or self.currency != 'USD':
            raise ValueError('Only local long-only USD simulation supported')
        object.__setattr__(self, 'quantity', decimal(self.quantity, True))
        object.__setattr__(self, 'limit', decimal(self.limit, True))
        precision = Decimal('0.00000001') if self.symbol == 'BTC' else Decimal('1')
        if self.quantity % precision:
            raise ValueError('Unsupported quantity precision')


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: Decimal
    ask: Decimal
    size: Decimal
    at: float
    latency_ms: Decimal = Decimal('0')
    reliable: bool = True
    event_blocked: bool = False
    available: bool = True

    def __post_init__(self):
        if self.symbol not in ASSETS:
            raise ValueError('Unknown quote')
        for name in ('bid', 'ask', 'size', 'latency_ms'):
            object.__setattr__(self, name, decimal(getattr(self, name), name in ('bid', 'ask')))
        object.__setattr__(self, 'at', timestamp(self.at))
        if self.bid > self.ask or any(type(getattr(self, k)) is not bool for k in ('reliable', 'event_blocked', 'available')):
            raise ValueError('Invalid quote flags or crossed market')


@dataclass(frozen=True)
class Limits:
    max_order: Decimal = Decimal('2000')
    max_account: Decimal = Decimal('50000')
    max_strategy: Decimal = Decimal('10000')
    max_symbol: Decimal = Decimal('10000')
    max_sector: Decimal = Decimal('25000')
    max_currency: Decimal = Decimal('50000')
    max_daily_notional: Decimal = Decimal('20000')
    max_daily_loss: Decimal = Decimal('1000')
    max_drawdown: Decimal = Decimal('0.08')
    max_concentration: Decimal = Decimal('0.20')
    max_turnover: Decimal = Decimal('0.5')
    max_spread_bps: Decimal = Decimal('15')
    max_slippage_bps: Decimal = Decimal('5')
    price_collar_bps: Decimal = Decimal('30')
    max_latency_ms: Decimal = Decimal('500')
    min_liquidity: Decimal = Decimal('100')
    max_orders: int = 30
    max_cancellations: int = 20
    max_age_seconds: int = 5
    commission: Decimal = Decimal('1')
    commission_rate: Decimal = Decimal('0.001')
    fill_delay_seconds: Decimal = Decimal('0.25')
    participation: Decimal = Decimal('0.10')

    def __post_init__(self):
        for name, value in asdict(self).items():
            if name in ('max_orders', 'max_cancellations', 'max_age_seconds'):
                if type(value) is not int or value <= 0:
                    raise ValueError('Positive integer limit required')
            else:
                object.__setattr__(self, name, decimal(value, True))
        for name in ('max_drawdown', 'max_concentration', 'max_turnover', 'participation', 'commission_rate'):
            if getattr(self, name) > 1:
                raise ValueError('Fractional limit exceeds one')


class ResearchEngine:
    """Single-user simulator. Never pass this object real-account values or credentials."""
    def __init__(self, path, limits=None):
        self.limits = limits or Limits()
        self._lock = threading.RLock()
        path = Path(path)
        parent_existed = path.parent.exists()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not parent_existed:
            path.parent.chmod(0o700)
        self._db = sqlite3.connect(str(path), timeout=10, check_same_thread=False, isolation_level=None)
        path.chmod(0o600)
        self._db.row_factory = sqlite3.Row
        version = self._db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            self._db.close()
            raise ValueError('Unsupported future research schema')
        self._db.execute('PRAGMA synchronous=FULL')
        self._db.executescript('''
          PRAGMA user_version=1;
          CREATE TABLE IF NOT EXISTS state(tenant TEXT PRIMARY KEY, data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS orders(tenant TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(tenant,id));
          CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL, body TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL);
          CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;
          CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;
        ''')
        with self._transaction():
            existing = self._db.execute('SELECT data FROM state WHERE tenant=?', (TENANT,)).fetchone()
            self._integrity = self.verify_audit()
            if existing:
                state = json.loads(existing['data'])
                if self._integrity:
                    state.update(paused=True, reconciled=False)
                    self._save(state)
                    self._audit('restart_paused', {})
            else:
                self._save(dict(cash='100000', initial_cash='100000', peak='100000', day_open='100000', day='', daily_notional='0', daily_orders=0, cancellations=0, costs='0', realized='0', paused=True, killed=False, reconciled=True, bitcoin_consent=False, paused_strategies=[], killed_strategies=[], positions={}, quotes={}, last_clock=0))
                self._audit('created', {'mode': 'synthetic research', 'cash': '100000', 'limits': asdict(self.limits)})

    @contextmanager
    def _transaction(self):
        with self._lock:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self._db.execute('COMMIT')
            except BaseException:
                self._db.execute('ROLLBACK')
                raise

    def close(self):
        with self._lock:
            self._db.close()

    def _state(self):
        return json.loads(self._db.execute('SELECT data FROM state WHERE tenant=?', (TENANT,)).fetchone()[0])

    def _save(self, state):
        self._db.execute('INSERT OR REPLACE INTO state VALUES (?,?)', (TENANT, encoded(state)))

    def _orders(self):
        return [json.loads(row[0]) for row in self._db.execute('SELECT data FROM orders WHERE tenant=? ORDER BY rowid', (TENANT,))]

    def _put_order(self, order):
        self._db.execute('INSERT OR REPLACE INTO orders VALUES (?,?,?)', (TENANT, order['id'], encoded(order)))

    def _audit(self, event, detail):
        row = self._db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone()
        previous = row[0] if row else '0' * 64
        body = encoded({'event': event, 'detail': detail, 'at': time.time(), 'ledger': self._ledger_digest()})
        digest = hashlib.sha256((previous + TENANT + body).encode()).hexdigest()
        self._db.execute('INSERT INTO audit(tenant,body,previous,hash) VALUES(?,?,?,?)', (TENANT, body, previous, digest))

    def _ledger_digest(self):
        rows = [list(row) for row in self._db.execute('SELECT tenant,data FROM state ORDER BY tenant')]
        rows += [list(row) for row in self._db.execute('SELECT tenant,id,data FROM orders ORDER BY tenant,id')]
        return hashlib.sha256(encoded(rows).encode()).hexdigest()

    def verify_audit(self):
        last_body = None
        previous = '0' * 64
        for row in self._db.execute('SELECT * FROM audit ORDER BY seq'):
            digest = hashlib.sha256((previous + row['tenant'] + row['body']).encode()).hexdigest()
            if row['tenant'] != TENANT or row['previous'] != previous or row['hash'] != digest:
                return False
            previous = row['hash']
            last_body = json.loads(row['body'])
        if last_body is None:
            return self._db.execute('SELECT COUNT(*) FROM state').fetchone()[0] == 0
        return last_body.get('ledger') == self._ledger_digest()

    def _quote_error(self, quote, now):
        if not quote.available or not quote.reliable or quote.event_blocked:
            return 'market_unavailable_or_event'
        if not 0 <= now - quote.at <= self.limits.max_age_seconds:
            return 'stale_or_future_quote'
        if quote.latency_ms > self.limits.max_latency_ms:
            return 'latency'
        if (quote.ask - quote.bid) / quote.bid * 10000 > self.limits.max_spread_bps:
            return 'spread'
        if quote.size < self.limits.min_liquidity:
            return 'liquidity'
        return None

    def _equity(self, state, now):
        value = decimal(state['cash'])
        for symbol, position in state['positions'].items():
            if not decimal(position['quantity']):
                continue
            raw = state['quotes'].get(symbol)
            if raw is None or self._quote_error(Quote(**raw), now):
                raise ValueError('stale_portfolio_marks')
            value += decimal(position['quantity']) * decimal(raw['bid'])
        return value

    def _risk(self, state, order, quote, now, execution=False):
        if not self._integrity or not self.verify_audit():
            return 'audit_integrity'
        if state['killed'] or order.strategy in state['killed_strategies']:
            return 'kill_switch'
        if not execution and (state['paused'] or order.strategy in state['paused_strategies']):
            return 'paused'
        if not state['reconciled']:
            return 'reconciliation_required'
        if now < state['last_clock']:
            return 'clock_reversal'
        error = self._quote_error(quote, now)
        if error:
            return error
        spec = SPECS[order.strategy]
        if now - quote.at > spec.max_age_seconds:
            return 'strategy_stale_quote'
        if (quote.ask - quote.bid) / quote.bid * 10000 > Decimal(str(spec.spread_bps)):
            return 'strategy_spread'
        if order.strategy == 'scalping' and quote.latency_ms > 100:
            return 'strategy_latency'
        if quote.symbol != order.symbol:
            return 'symbol_mismatch'
        if order.symbol == 'BTC' and not state['bitcoin_consent']:
            return 'bitcoin_consent_required'
        if abs(order.limit / ((quote.bid + quote.ask) / 2) - 1) * 10000 > self.limits.price_collar_bps:
            return 'price_collar'
        try:
            equity = self._equity(state, now)
        except ValueError as error:
            return str(error)
        day = time.strftime('%Y-%m-%d', time.gmtime(now))
        if state['day'] != day:
            carried = [o for o in self._orders() if o['status'] in ACTIVE]
            carried_notional = sum((decimal(o['remaining']) * decimal(o['order']['limit']) for o in carried), Decimal('0'))
            state.update(day=day, day_open=str(equity), daily_notional=str(carried_notional), daily_orders=len(carried), cancellations=0)
        week = time.strftime('%Y-%W', time.gmtime(now))
        if state.get('week') != week:
            state.update(week=week, week_open=str(equity))
        if order.strategy == 'bitcoin' and decimal(state['week_open']) - equity >= equity * Decimal('0.015'):
            return 'bitcoin_week_loss'
        if equity <= 0 or decimal(state['day_open']) - equity >= min(self.limits.max_daily_loss, equity * Decimal(str(spec.daily_loss_limit))):
            return 'daily_loss'
        peak = max(decimal(state['peak']), equity)
        state['peak'] = str(peak)
        if (peak - equity) / peak >= min(self.limits.max_drawdown, Decimal(str(spec.max_drawdown))):
            return 'drawdown'
        notional = order.quantity * order.limit
        if notional > self.limits.max_order:
            return 'order_limit'
        if not execution and state['cancellations'] >= self.limits.max_cancellations:
            return 'cancellation_budget'
        if not execution and state['daily_orders'] >= self.limits.max_orders:
            return 'order_count'
        turnover = decimal(state['daily_notional']) + (Decimal('0') if execution else notional)
        if turnover > self.limits.max_daily_notional or turnover / equity > self.limits.max_turnover:
            return 'daily_notional_or_turnover'
        active = [o for o in self._orders() if o['status'] in ACTIVE and (not execution or o['id'] != order.key)]
        if order.side == 'SELL':
            position = state['positions'].get(order.symbol, {})
            owned = decimal(position.get('strategy_quantities', {}).get(order.strategy, '0'))
            reserved = sum((decimal(o['remaining']) for o in active if o['order']['symbol'] == order.symbol and o['order']['strategy'] == order.strategy and o['order']['side'] == 'SELL'), Decimal('0'))
            if order.quantity + reserved > owned:
                return 'short_selling_blocked'
        else:
            pending = [o for o in active if o['order']['side'] == 'BUY']
            cash_reserved = sum((decimal(o['remaining']) * decimal(o['order']['limit']) + decimal(o['reserve_cost']) for o in pending), Decimal('0'))
            # Reserve a conservative commission for every possible smallest fill.
            fee = self._reserve_cost(order)
            if notional + fee + cash_reserved > decimal(state['cash']):
                return 'buying_power'
            exposure = {}
            strategy_exposure = Decimal('0')
            for symbol, pos in state['positions'].items():
                exposure[symbol] = decimal(pos['quantity']) * decimal(state['quotes'].get(symbol, {'ask': pos['average']})['ask'])
                strategy_exposure += decimal(pos.get('strategy_quantities', {}).get(order.strategy, '0')) * decimal(state['quotes'][symbol]['ask'])
            for prior in pending:
                symbol = prior['order']['symbol']
                value = decimal(prior['remaining']) * decimal(prior['order']['limit'])
                exposure[symbol] = exposure.get(symbol, Decimal('0')) + value
                if prior['order']['strategy'] == order.strategy:
                    strategy_exposure += value
            exposure[order.symbol] = exposure.get(order.symbol, Decimal('0')) + notional
            total = sum(exposure.values())
            if total > min(self.limits.max_account, self.limits.max_currency):
                return 'account_or_currency_exposure'
            if exposure[order.symbol] > self.limits.max_symbol or exposure[order.symbol] / equity > self.limits.max_concentration:
                return 'symbol_concentration'
            # Conservative shared unknown-sector bucket; no invented ETF look-through.
            if total > self.limits.max_sector:
                return 'sector_exposure'
            if strategy_exposure + notional > min(self.limits.max_strategy, equity * Decimal(str(spec.max_weight))):
                return 'strategy_exposure'
        return None

    def _reserve_cost(self, order):
        max_fills = Decimal('20') if order.symbol == 'BTC' else min(Decimal('20'), order.quantity)
        return max_fills * self.limits.commission + order.quantity * order.limit * self.limits.commission_rate

    def submit(self, order, quote, now=None):
        """Only public submission route. Idempotency applies across crashes/restarts."""
        if not isinstance(order, Order) or not isinstance(quote, Quote):
            raise ValueError('Validated Order and Quote required')
        now = timestamp(time.time() if now is None else now)
        with self._transaction():
            if not self._integrity or not self.verify_audit():
                self._integrity = False
                raise ValueError('audit_integrity')
            existing = self._db.execute('SELECT data FROM orders WHERE tenant=? AND id=?', (TENANT, order.key)).fetchone()
            if existing:
                prior = json.loads(existing[0])
                if encoded(prior['order']) != encoded(asdict(order)):
                    raise ValueError('idempotency_conflict')
                return prior
            state = self._state()
            # Invalid quote cannot poison the portfolio marks used by later requests.
            if not self._quote_error(quote, now):
                state['quotes'][quote.symbol] = asdict(quote)
            reason = self._risk(state, order, quote, now)
            item = dict(id=order.key, order=asdict(order), status='blocked' if reason else 'accepted', reason=reason, remaining=str(order.quantity), filled='0', fees='0', submitted=now, last_quote=None, fill_events=0, reserve_cost=str(self._reserve_cost(order)))
            if not reason:
                state['daily_orders'] += 1
                state['daily_notional'] = str(decimal(state['daily_notional']) + order.quantity * order.limit)
                state['last_clock'] = now
            self._put_order(item)
            self._save(state)
            self._audit('order_' + item['status'], {'id': order.key, 'reason': reason})
            return json.loads(encoded(item))

    def process(self, key, quote, now=None):
        """Conservative synthetic partial fill; never calls any broker adapter."""
        if not isinstance(quote, Quote):
            raise ValueError('Validated Quote required')
        now = timestamp(time.time() if now is None else now)
        with self._transaction():
            row = self._db.execute('SELECT data FROM orders WHERE tenant=? AND id=?', (TENANT, key)).fetchone()
            if row is None:
                raise ValueError('Unknown order')
            item = json.loads(row[0])
            if not self._integrity or not self.verify_audit():
                self._integrity = False
                raise ValueError('audit_integrity')
            if item['status'] not in ACTIVE:
                return item
            state = self._state()
            order = Order(**item['order'])
            if not self.verify_audit() or not self._integrity or (order.symbol == 'BTC' and not state['bitcoin_consent']) or state['killed'] or order.strategy in state['killed_strategies'] or not state['reconciled']:
                raise ValueError('execution_blocked')
            error = self._quote_error(quote, now)
            if error or quote.symbol != order.symbol or now < state['last_clock']:
                raise ValueError(error or 'quote_or_clock_mismatch')
            if now - item['submitted'] < float(self.limits.fill_delay_seconds) or quote.at <= item['submitted'] or (item['last_quote'] is not None and quote.at <= item['last_quote']):
                return item
            if item.get('fill_events', 0) >= 20:
                item.update(status='cancelled', reason='synthetic_fill_budget')
                self._put_order(item)
                self._audit('fill_budget_cancelled', {'id': key})
                return item
            state['quotes'][quote.symbol] = asdict(quote)
            liquidity_key = quote.symbol + ':' + str(quote.at)
            used_liquidity = decimal(state.get('liquidity_used', {}).get(liquidity_key, '0'))
            remaining_order = Order(**dict(item['order'], quantity=item['remaining']))
            risk_error = self._risk(state, remaining_order, quote, now, execution=True)
            if risk_error:
                raise ValueError('execution_' + risk_error)
            equity = self._equity(state, now)
            peak = max(decimal(state['peak']), equity)
            if decimal(state['day_open']) - equity >= self.limits.max_daily_loss or (peak - equity) / peak >= self.limits.max_drawdown:
                raise ValueError('loss_limit_execution_blocked')
            slippage = self.limits.max_slippage_bps / 10000
            price = quote.ask * (1 + slippage) if order.side == 'BUY' else quote.bid * (1 - slippage)
            if (order.side == 'BUY' and price > order.limit) or (order.side == 'SELL' and price < order.limit):
                return item
            quantity = min(decimal(item['remaining']), max(Decimal('0'), quote.size * self.limits.participation - used_liquidity))
            step = Decimal('0.00000001') if order.symbol == 'BTC' else Decimal('1')
            quantity = (quantity // step) * step
            if not quantity:
                return item
            cost = quantity * price
            fee = self.limits.commission + cost * self.limits.commission_rate
            pos = state['positions'].setdefault(order.symbol, dict(quantity='0', average='0', strategy_quantities={}))
            owned = decimal(pos['quantity'])
            average = decimal(pos['average'])
            assigned = pos['strategy_quantities']
            if order.side == 'BUY':
                if cost + fee > decimal(state['cash']):
                    raise ValueError('insufficient_cash_at_fill')
                state['cash'] = str(decimal(state['cash']) - cost - fee)
                pos['average'] = str((owned * average + cost + fee) / (owned + quantity))
                pos['quantity'] = str(owned + quantity)
                assigned[order.strategy] = str(decimal(assigned.get(order.strategy, '0')) + quantity)
            else:
                if quantity > owned or quantity > decimal(assigned.get(order.strategy, '0')):
                    raise ValueError('strategy_does_not_own_position')
                if decimal(state['cash']) + cost < fee:
                    raise ValueError('fees_exceed_cash')
                state['cash'] = str(decimal(state['cash']) + cost - fee)
                state['realized'] = str(Decimal(state['realized']) + quantity * (price - average) - fee)
                pos['quantity'] = str(owned - quantity)
                assigned[order.strategy] = str(decimal(assigned[order.strategy]) - quantity)
            state.setdefault('liquidity_used', {})[liquidity_key] = str(used_liquidity + quantity)
            # Keep only current/recent depth samples; older ones are rejected by last_clock.
            state['liquidity_used'] = {k: v for k, v in state['liquidity_used'].items() if float(k.rsplit(':', 1)[1]) >= now - self.limits.max_age_seconds}
            state['costs'] = str(decimal(state['costs']) + fee)
            state['peak'] = str(peak)
            state['last_clock'] = now
            item['remaining'] = str(decimal(item['remaining']) - quantity)
            item['filled'] = str(decimal(item['filled']) + quantity)
            item['fees'] = str(decimal(item['fees']) + fee)
            item['status'] = 'partial' if decimal(item['remaining']) else 'filled'
            item['last_quote'] = quote.at
            item['fill_events'] = item.get('fill_events', 0) + 1
            self._put_order(item)
            self._save(state)
            self._audit('synthetic_fill', {'id': key, 'quantity': str(quantity), 'price': str(price), 'commission': str(fee)})
            return item

    def record_signal(self, signal):
        from .strategies import Signal
        if not isinstance(signal, Signal) or signal.strategy_id not in STRATEGIES:
            raise ValueError('Validated signal required')
        with self._transaction():
            if not self._integrity or not self.verify_audit():
                raise ValueError('audit_integrity')
            self._audit('research_signal', asdict(signal))

    def control(self, action, strategy=None):
        if strategy is not None and strategy not in STRATEGIES:
            raise ValueError('Unknown strategy')
        if action not in ('pause', 'resume', 'kill', 'cancel_pending', 'reconcile', 'consent_bitcoin', 'revoke_bitcoin'):
            raise ValueError('Unsupported control; liquidations and live activation absent')
        with self._transaction():
            state = self._state()
            if not self.verify_audit() or not self._integrity:
                raise ValueError('audit_integrity')
            if action in ('pause', 'resume', 'kill'):
                if action == 'resume' and (state['killed'] or not state['reconciled'] or strategy in state['killed_strategies']):
                    raise ValueError('Cannot resume killed or unreconciled simulator')
                if strategy:
                    values = set(state['paused_strategies'])
                    values.discard(strategy) if action == 'resume' else values.add(strategy)
                    state['paused_strategies'] = sorted(values)
                    if action == 'kill':
                        state['killed_strategies'] = sorted(set(state['killed_strategies']) | {strategy})
                else:
                    state['paused'] = action != 'resume'
                    if action == 'kill':
                        state['killed'] = True
            elif action == 'cancel_pending':
                candidates = [o for o in self._orders() if o['status'] in ACTIVE and (strategy is None or o['order']['strategy'] == strategy)]
                # Emergency local cancellation remains available even above the normal cancel budget.
                for item in candidates:
                    item.update(status='cancelled', reason='explicit_cancellation')
                    self._put_order(item)
                state['cancellations'] += len(candidates)
            elif action == 'reconcile':
                # Offline ledger: transactional writes preclude unacknowledged remote fills.
                valid = decimal(state['cash']) >= 0 and all(decimal(p['quantity']) == sum((decimal(x) for x in p['strategy_quantities'].values()), Decimal('0')) for p in state['positions'].values())
                if not valid:
                    raise ValueError('ledger_mismatch')
                state['reconciled'] = True
            else:
                state['bitcoin_consent'] = action == 'consent_bitcoin'
                if action == 'revoke_bitcoin':
                    for item in self._orders():
                        if item['status'] in ACTIVE and item['order']['symbol'] == 'BTC':
                            item.update(status='cancelled', reason='consent_revoked')
                            self._put_order(item)
            self._save(state)
            self._audit(action, {'strategy': strategy})
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            state = self._state()
            orders = self._orders()
            intact = self._integrity and self.verify_audit()
            self._integrity = intact
            status = 'audit_error' if not intact else 'killed' if state['killed'] else 'reconciliation_required' if not state['reconciled'] else 'paused' if state['paused'] else 'research_only'
            signals = {}
            for row in self._db.execute('SELECT body FROM audit WHERE tenant=? ORDER BY seq', (TENANT,)):
                event = json.loads(row[0])
                if event.get('event') == 'research_signal':
                    signals[event['detail']['strategy_id']] = event
            bots = []
            for strategy in STRATEGIES:
                selected = [o for o in orders if o['order']['strategy'] == strategy]
                observed = signals.get(strategy, {})
                bots.append(dict(id=strategy, name=SPECS[strategy].name, horizon=SPECS[strategy].timeframe, risk=SPECS[strategy].risk, status='killed' if strategy in state['killed_strategies'] else 'paused' if strategy in state['paused_strategies'] else status, validation='not_validated', heartbeat=observed.get("at"), capital=None, exposure=None, realized_pnl=None, unrealized_pnl=None, drawdown=None, costs=str(sum((decimal(o['fees']) for o in selected), Decimal('0'))), last_signal=observed.get('detail', {}).get('reason'), proposed=len(selected), blocked=sum(o['status']=='blocked' for o in selected), submitted=sum(o['status']!='blocked' for o in selected), fills=sum(decimal(o['filled'])>0 for o in selected), errors=[], performance=None))
            audit = [dict(seq=r['seq'], **json.loads(r['body']), hash=r['hash']) for r in self._db.execute('SELECT * FROM audit WHERE tenant=? ORDER BY seq DESC LIMIT 30', (TENANT,))]
            return dict(mode='research_simulator', live_enabled=False, status=status, currency='USD', synthetic=True, cash=state['cash'], costs=state['costs'], realized_pnl=state['realized'], bots=bots, orders=orders[-50:], positions=state['positions'], audit=audit, audit_valid=intact, limits=json.loads(encoded(asdict(self.limits))), performance=None, bitcoin_consent=state['bitcoin_consent'], warning=WARNING)

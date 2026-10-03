"""Signal-to-risk path for local fixtures; never accepts a live broker adapter."""
from dataclasses import dataclass
from decimal import Decimal
from .engine import Order, Quote, ResearchEngine
from .strategies import MarketFrame, StrategyContext, Signal, evaluate


@dataclass(frozen=True)
class PipelineResult:
    signal: Signal
    order: object


def step(engine: ResearchEngine, strategy_id: str, frame: MarketFrame,
         context: StrategyContext, key: str, bitcoin_variant: str = 'trend') -> PipelineResult:
    if type(engine) is not ResearchEngine:
        raise ValueError('Only the offline simulator is supported')
    signal = evaluate(strategy_id, frame, context, bitcoin_variant)
    engine.record_signal(signal)
    if signal.action not in ('ENTER', 'EXIT'):
        return PipelineResult(signal, None)
    if signal.limit_price is None:
        raise ValueError('No validated limit price')
    quantity = (Decimal(str(context.equity)) * Decimal(str(signal.target_weight)) /
                Decimal(str(signal.limit_price))) if signal.action == 'ENTER' else Decimal(str(context.position.quantity))
    precision = Decimal('0.00000001') if strategy_id == 'bitcoin' else Decimal('1')
    quantity = (quantity // precision) * precision
    if quantity <= 0:
        return PipelineResult(signal, None)
    order = Order(key, strategy_id, frame.symbol, 'BUY' if signal.action == 'ENTER' else 'SELL',
                  quantity, Decimal(str(signal.limit_price)), currency=frame.currency)
    quote = Quote(frame.symbol, Decimal(str(frame.quote.bid)), Decimal(str(frame.quote.ask)),
                  Decimal(str(min(frame.quote.ask_size,frame.quote.bid_size))), frame.quote.timestamp,
                  latency_ms=Decimal(str(frame.quote.latency_ms)), reliable=frame.data_complete,
                  event_blocked=not frame.event_clear, available=frame.session_open)
    return PipelineResult(signal, engine.submit(order, quote, now=context.now))

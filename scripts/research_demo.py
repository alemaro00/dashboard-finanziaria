"""Temporary synthetic signal -> risk -> simulator exercise, not a performance run."""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.engine import ResearchEngine, Quote as ExecutionQuote
from research.strategies import STRATEGIES, Bar, Quote, MarketFrame, Position, StrategyContext, NOTICE
from research.pipeline import step


def fixture(strategy):
    interval={'tick':1,'1m':60,'5m':300,'4h':14400,'1d':86400}[strategy.timeframe]
    now=2_000_000_000.0
    bars=tuple(Bar(now-(strategy.required_bars-1-i)*interval,100+i*.03,
        100.02+i*.03+(i%2)*.01,99.98+i*.03,100+i*.03+(i%2)*.005,10000)
        for i in range(strategy.required_bars))
    quote=Quote(now,bars[-1].close-.005,bars[-1].close+.005,10000,1000,10,'tick_l2')
    frame=MarketFrame('BTC' if strategy.id=='bitcoin' else 'SPY',
        'BTC_SPOT' if strategy.id=='bitcoin' else 'ETF','USD',strategy.timeframe,bars,quote,
        365.25*86400/interval,True,10000,True,True,True,True,1,5,True,True)
    ctx=StrategyContext(now,10000,Position(),0,0,0,0,0,0,0,True,True,True,True,1)
    return frame,ctx


def main():
    results=[]
    with tempfile.TemporaryDirectory(prefix='dashboard-synthetic-') as root:
        for spec in STRATEGIES:
            engine=ResearchEngine(Path(root)/(spec.id+'.sqlite3'))
            try:
                engine.control('resume')  # Simulator only; default constructor remains paused.
                if spec.id=='bitcoin':engine.control('consent_bitcoin')
                frame,ctx=fixture(spec)
                result=step(engine,spec.id,frame,ctx,'synthetic-'+spec.id)
                status=result.order['status'] if result.order else 'no_order'
                if result.order and status=='accepted':
                    # Hypothetical later lower ask; does not purport to be market history.
                    q=ExecutionQuote(frame.symbol,frame.quote.bid-.1,frame.quote.ask-.1,100,ctx.now+1)
                    filled=engine.process(result.order['id'],q,now=ctx.now+1)
                    status=filled['status']
                results.append({'strategy':spec.id,'signal':result.signal.action,'reason':result.signal.reason,
                                'synthetic_order_status':status,'risk_reason':result.order.get('reason') if result.order else None,'audit_valid':engine.snapshot()['audit_valid']})
            finally:engine.close()
    print(json.dumps({'notice':NOTICE,'mode':'synthetic software test; no market performance',
                      'live_enabled':False,'results':results},ensure_ascii=False,indent=2))

if __name__=='__main__':main()

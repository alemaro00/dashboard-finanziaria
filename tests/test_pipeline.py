import unittest
from dataclasses import replace
from pathlib import Path
import tempfile
from research.engine import ResearchEngine
from research.pipeline import step
from research.strategies import SPECS
from scripts.research_demo import fixture

class PipelineTests(unittest.TestCase):
    def test_signal_never_bypasses_paused_risk_and_is_audited(self):
        with tempfile.TemporaryDirectory() as root:
            engine=ResearchEngine(Path(root)/'ledger.sqlite3')
            try:
                frame,ctx=fixture(SPECS['momentum'])
                ctx=replace(ctx,equity=5000)
                result=step(engine,'momentum',frame,ctx,'entry')
                self.assertEqual(result.signal.action,'ENTER')
                self.assertEqual(result.order['reason'],'paused')
                self.assertEqual(engine.snapshot()['positions'],{})
                self.assertTrue(any(x['event']=='research_signal' for x in engine.snapshot()['audit']))
                engine.control('resume')
                result=step(engine,'momentum',frame,ctx,'entry-enabled')
                self.assertEqual(result.order['status'],'accepted')
            finally:engine.close()

    def test_bad_data_has_no_order_and_no_adapters(self):
        with tempfile.TemporaryDirectory() as root:
            engine=ResearchEngine(Path(root)/'ledger.sqlite3')
            try:
                frame,ctx=fixture(SPECS['swing'])
                result=step(engine,'swing',frame,replace(ctx,reconciled=False),'blocked')
                self.assertEqual(result.signal.action,'BLOCKED')
                self.assertIsNone(result.order)
                with self.assertRaises(ValueError):step(object(),'swing',frame,ctx,'bad-adapter')
            finally:engine.close()

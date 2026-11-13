"""Bounded retry slots use the real queue, without rediscovery or acquisition."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import preparation_pipeline as pipeline
import prepared_article_readings as prepared
import comprehensive_readings as reader
from test_prepared_article_readings import packet, FRIDAY, MONDAY, WINDOW, document, result_for


class RollingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'data/weekly-preparation' / WINDOW['from']
        self.folder.mkdir(parents=True)
        self.packet = packet()
        self.doc = document()
        self.state = prepared.acquire(self.packet, now=FRIDAY, known_sources_only=True,
            attempt=lambda *args: result_for(self.doc), clock=lambda: 0)
        self.bundle = prepared.reconcile(self.packet, self.state, now=FRIDAY)
        self.save()

    def save(self):
        prepared.sealed(self.bundle)
        for name, value in [('packet.json', self.packet), ('acquisition.json', self.state), ('readings.json', self.bundle)]:
            pipeline.atomic_save(self.folder / name, value)

    def test_matches_real_queue_before_and_after_due_time(self):
        record = next(iter(self.bundle['records'].values()))['record']
        record['complete_reading_attempt'] = {'status':'model_schema_invalid', 'stage':'synthesis',
            'last_at':'2026-11-13','next_at':'2026-11-15','provider_diagnostics':[],
            'format_failures':1,'retry_after':(FRIDAY+timedelta(minutes=15)).isoformat()}
        self.save()
        self.assertFalse(pipeline.rolling_retry_plan(self.root, FRIDAY)['ready'])
        due = FRIDAY+timedelta(minutes=15)
        plan = pipeline.rolling_retry_plan(self.root, due)
        self.assertTrue(plan['ready'])
        candidates = prepared.acquired_reading_records(self.bundle, self.state)
        _, selection = reader.reading_candidates(candidates, due.date().isoformat(), due)
        self.assertEqual(plan['selection'], selection)
        self.assertEqual(plan['status'], 'rolling_readings_due')

    def test_missing_closed_stale_or_wrong_week_never_starts_inference(self):
        self.assertFalse(pipeline.rolling_retry_plan(self.root, MONDAY)['ready'])
        with self.assertRaisesRegex(ValueError, 'scope_changed'):
            pipeline.rolling_retry_plan(self.root, MONDAY, expected_week=WINDOW['from'])
        (self.folder/'readings.json').unlink()
        self.assertEqual(pipeline.rolling_retry_plan(self.root, FRIDAY)['status'], 'awaiting_acquired_readings')
        self.save()
        self.bundle['packet_sha256'] = '0'*64
        self.save()
        with self.assertRaises(pipeline.ReadingInputsChanged):
            pipeline.rolling_retry_plan(self.root, FRIDAY)

    def test_zero_acquisition_budget_makes_no_provider_attempt(self):
        fetch = Mock(side_effect=AssertionError('unexpected source acquisition'))
        # Include an unacquired queue too, not only a completed source.
        for state in (None, self.state):
            result = prepared.acquire(self.packet, state, now=FRIDAY, limit=0,
                                      known_sources_only=True, attempt=fetch)
            self.assertEqual(result['run']['attempted_records'], 0)
        fetch.assert_not_called()

    def test_retry_execution_keeps_real_stage_receipts_and_hard_limits(self):
        acquire = prepared.acquire(self.packet, self.state, now=FRIDAY, limit=0, known_sources_only=True)
        reports = {'acquire':acquire['run'], 'review':{
            'attempted':1,'summaries_completed':0,'failed':1,'skipped_no_model':False,
            'selection':{'considered':1,'eligible':1,'deferred_by_limit':0,'skipped':{}}}}
        runner = Mock(side_effect=lambda args, **kw: subprocess.CompletedProcess(args, 0, json.dumps(reports[args[2]])))
        real_utc = pipeline.utc
        with patch.object(pipeline, 'utc', lambda value=None: real_utc(value or FRIDAY)):
            result = pipeline.run_readings(self.root, now=FRIDAY, phase='preparing',
                retry_only=True, expected_week=WINDOW['from'], runner=runner)
        self.assertEqual([(c.args[0][2], c.args[0][-1]) for c in runner.call_args_list], [('acquire','0'),('review','2')])
        pipeline.validate_reading_receipt(result,'preparation_reading_run',FRIDAY)
        with self.assertRaisesRegex(ValueError,'retry_only_requires'):
            pipeline.run_readings(self.root, now=FRIDAY, phase='closed',retry_only=True,runner=Mock())

    def test_workflow_has_bounded_non_dispatching_recovery_slots(self):
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/prepare-weekly-readings.yml').read_text()
        self.assertIn("cron: '17 8,10,20,22 * * *'",text)
        self.assertIn("if: env.RETRY_ONLY != 'true'",text)
        self.assertIn('rolling-retry-plan --expected-week',text)
        self.assertIn('args+=(--retry-only)',text)
        self.assertNotIn('actions: write',text)
        self.assertNotIn('/dispatches',text)
        self.assertIn("env.RETRY_ONLY != 'true' || steps.worker.outputs.claimed == 'true'",text)

if __name__=='__main__':unittest.main()

"""Offline scheduling, execution receipts and input-bound edition readiness."""
from copy import deepcopy
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import preparation_pipeline as pipeline
import weekly_preparation as prep
import prepared_article_readings as readings
import collect_weekly_sources as queue

NOW = dt.datetime(2026, 11, 9, 10, 0, tzinfo=dt.timezone.utc)
WINDOW = {'from': '2026-11-02', 'to': '2026-11-08', 'timezone': 'UTC'}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'data/weekly-preparation/2026-11-02'
        self.folder.mkdir(parents=True)
        self.packet = {'schema_version': 1, 'kind': 'weekly_preparation', 'observation_at': NOW.isoformat(),
            'target_publication_window': WINDOW, 'phase': 'closed', 'status': 'partial',
            'date_eligibility': 'verified_original_publication_date_only', 'public_eligible': False,
            'source_checked': False, 'approved': False, 'run': {'date': NOW.date().isoformat(),
                'mode': 'preparation', 'publication_window': WINDOW}, 'items': [], 'quarantine': [],
            'coverage': {'closeout_required': False, 'closeout_started_at': '2026-11-09T00:30:00+00:00',
                'closeout_pass': 'late_index', 'configured_query_status': 'partial', 'errors': [],
                'closeout_passes': {'initial': {'started_at': '2026-11-09T00:30:00+00:00'},
                                   'late_index': {'started_at': '2026-11-09T06:30:00+00:00'}},
                'publisher_snapshots': {'sources': [{'status': 'unavailable'}]}}}
        self.save_packet()
        self.save('weekly.json', prep.closed_packet(self.packet, NOW))
        self.save('library.json', [])
        # Empty bounded acquisition/reconciliation is fully offline.
        self.state = queue._run_window(self.packet, None, window=WINDOW, now=NOW, limit=0, time_budget=1)
        self.bundle = readings.reconcile(self.packet, self.state, now=NOW)
        prep.atomic_save(self.folder / 'acquisition.json', self.state)
        prep.atomic_save(self.folder / 'readings.json', self.bundle)
        self.reports = {'acquire': self.state['run'],
            'review': {'attempted': 2, 'summaries_completed': 1, 'failed': 1, 'skipped_no_model': False},
            'revalidate': {'attempted': 0, 'source_text_saved': False, 'approved': False},
            'apply': {'machine_checked_readings_applied': 0, 'approved': False}}

    def save(self, name, value): prep.atomic_save(self.root / 'data' / name, value)
    def save_packet(self): prep.atomic_save(self.folder / 'packet.json', self.packet)

    def receipt(self):
        runner = Mock(side_effect=lambda args, **kw: subprocess.CompletedProcess(args, 0, json.dumps(self.reports[args[2]])))
        real_utc = pipeline.utc
        with patch.object(pipeline, 'utc', lambda value=None: real_utc(value or NOW)):
            result = pipeline.run_readings(self.root, now=NOW, runner=runner)
        self.assertEqual([call.args[0][2] for call in runner.call_args_list], ['acquire', 'review', 'revalidate', 'apply'])
        self.assertEqual(runner.call_args_list[1].args[0][-1], '2')
        return result

    def test_initial_and_single_late_pass_do_not_wait_for_complete_queries(self):
        self.packet['coverage']['closeout_passes'].pop('late_index')
        self.packet['coverage']['closeout_pass'] = 'initial'
        self.save_packet()
        self.assertEqual(pipeline.closeout_plan(self.root, NOW)['closeout_pass'], 'late_index')
        early = NOW.replace(hour=5)
        self.packet['observation_at'] = early.isoformat(); self.save_packet()
        self.assertEqual(pipeline.closeout_plan(self.root, early)['closeout_pass'], 'initial')
        self.assertEqual(pipeline.closeout_plan(self.root, early)['status'], 'resume_partial_closeout')
        self.packet['coverage']['closeout_passes']['late_index'] = {'started_at': NOW.isoformat()}
        self.packet['observation_at'] = NOW.isoformat(); self.save_packet()
        plan = pipeline.closeout_plan(self.root, NOW)
        self.assertEqual(plan['closeout_pass'], 'late_index')
        self.assertTrue(plan['needed'])

    def test_complete_late_generation_does_not_replay_searches(self):
        self.packet['coverage'].update(configured_query_status='complete_for_configured_queries', publisher_snapshots={'sources': []})
        self.save_packet()
        self.assertFalse(pipeline.closeout_plan(self.root, NOW)['needed'])
        with patch.object(prep, 'prepare') as collect, patch.object(prep, 'adopt_to_canonical') as adopt:
            pipeline.run_closeout(self.root, NOW)
        collect.assert_not_called(); adopt.assert_called_once()

    def test_absent_initial_and_calendar_rollover_target_actual_weeks(self):
        (self.folder / 'packet.json').unlink()
        self.assertEqual(pipeline.closeout_plan(self.root, NOW)['status'], 'initial_closeout_required')
        self.assertEqual(pipeline.closeout_plan(self.root, NOW + dt.timedelta(days=7))['week'], '2026-11-09')
        self.assertEqual(pipeline.folder_for(self.root, NOW.replace(hour=0), 'preparing').name, '2026-11-09')

    def test_final_reading_requires_actual_late_index_packet(self):
        self.packet['coverage']['closeout_passes'].pop('late_index'); self.save_packet()
        self.assertFalse(pipeline.reading_plan(self.root, NOW)['ready'])
        with self.assertRaisesRegex(ValueError, 'awaiting_late_index'):
            pipeline.run_readings(self.root, NOW, runner=Mock())

    def test_failed_readings_are_reported_separately_not_independently_approved(self):
        self.receipt()
        final = pipeline.finalize(self.root, NOW)
        self.assertEqual(final['status'], 'completed_with_review_failures')
        self.assertEqual(final['coverage']['review_failed_this_run'], 1)
        self.assertEqual(final['coverage']['review_completed_this_run'], 1)
        self.assertEqual(final['coverage']['independent_approvals_granted_by_pipeline'], 0)
        self.assertFalse(final['approved'])
        self.assertTrue(pipeline.edition_ready(self.root, NOW)['ready'])

    def test_missing_model_and_failed_cli_never_create_reading_receipts(self):
        self.reports['review'] = {'status': 'model_unavailable', 'approved': False}
        with self.assertRaisesRegex(ValueError, 'reading_stage_not_executed'):
            self.receipt()
        self.assertFalse((self.folder / 'reading-run.json').exists())
        with self.assertRaises(subprocess.CalledProcessError):
            pipeline.run_readings(self.root, NOW, runner=Mock(side_effect=subprocess.CalledProcessError(1, 'review')))
        self.assertFalse((self.folder / 'reading-run.json').exists())

    def test_every_exact_final_input_change_invalidates_readiness(self):
        self.receipt(); pipeline.finalize(self.root, NOW)
        for name in ('packet.json', 'acquisition.json', 'readings.json', 'library.json', 'weekly.json'):
            path = (self.root / 'data' if name in ('library.json', 'weekly.json') else self.folder) / name
            before = path.read_text(); value = json.loads(before)
            if name == 'library.json': value.append({'title': 'Changed metadata'})
            elif name == 'packet.json': value['status'] = 'prepared'
            elif name == 'weekly.json': value['run']['changed'] = True
            elif name == 'acquisition.json': value['run']['stop_reason'] = 'changed'
            else: value['observation_at'] = (NOW - dt.timedelta(seconds=1)).isoformat()
            prep.atomic_save(path, value)
            try:
                with self.subTest(name=name):
                    try: ready = pipeline.edition_ready(self.root, NOW)['ready']
                    except ValueError: ready = False
                    self.assertFalse(ready)
            finally: path.write_text(before)

    def test_old_finalization_cannot_survive_new_reading_run_or_new_week(self):
        self.receipt(); pipeline.finalize(self.root, NOW)
        receipt = pipeline.read(self.folder / 'reading-run.json'); receipt['stages']['review']['failed'] += 1
        prep.atomic_save(self.folder / 'reading-run.json', receipt)
        self.assertFalse(pipeline.edition_ready(self.root, NOW)['ready'])
        self.assertFalse(pipeline.edition_ready(self.root, NOW + dt.timedelta(days=7))['ready'])

    def test_checkpoint_allowlist_excludes_raw_sources_and_reconstructs_status(self):
        prep.atomic_save(self.folder / 'status.json', {'raw_source': 'Never retain arbitrary status fields'})
        prep.atomic_save(self.folder / 'raw-source.json', {'body': 'Never retain a source body'})
        prep.atomic_save(self.folder / 'snapshots/observed.json', self.packet)
        destination = self.root / 'recovery'
        result = pipeline.checkpoint(self.root, destination, NOW)
        self.assertTrue(result['valid'])
        saved = destination / self.folder.relative_to(self.root)
        self.assertFalse((saved / 'raw-source.json').exists())
        self.assertFalse((saved / 'reading-run.json').exists())
        self.assertNotIn('raw_source', pipeline.read(saved / 'status.json'))
        self.assertEqual(pipeline.read(saved / 'acquisition.json'), self.state)
        self.assertTrue((saved / 'snapshots/observed.json').exists())

    def test_shared_provider_checkpoint_survives_missing_packet_after_early_failure(self):
        from academic_state import DiscoveryState
        (self.folder / 'packet.json').unlink()
        (self.folder / 'readings.json').unlink()
        path = self.root / 'data/academic-discovery-state.json'
        state = DiscoveryState(path, mode='closeout', window={k: WINDOW[k] for k in ('from', 'to')})
        state.save()
        destination = self.root / 'recovery'
        result = pipeline.checkpoint(self.root, destination, NOW)
        self.assertTrue(result['valid'])
        self.assertTrue((destination / 'data/academic-discovery-state.json').exists())
        self.assertFalse((destination / self.folder.relative_to(self.root) / 'packet.json').exists())

    def test_invalid_packet_does_not_discard_valid_provider_state(self):
        from academic_state import DiscoveryState
        path = self.root / 'data/academic-discovery-state.json'
        DiscoveryState(path, mode='closeout', window={k: WINDOW[k] for k in ('from', 'to')}).save()
        self.packet['approved'] = True; self.save_packet()
        destination = self.root / 'recovery'
        result = pipeline.checkpoint(self.root, destination, NOW)
        self.assertTrue(result['valid']); self.assertFalse(result['complete'])
        self.assertIn('data/weekly-preparation/2026-11-02/packet.json', result['invalid_files'])
        self.assertTrue((destination / 'data/academic-discovery-state.json').exists())
        self.assertFalse((destination / self.folder.relative_to(self.root) / 'packet.json').exists())

    def test_checkpoint_preserves_captured_week_across_calendar_rollover(self):
        observed = dt.datetime(2026, 11, 8, 23, 59, tzinfo=dt.timezone.utc)
        self.packet.update(phase='preparing', observation_at=observed.isoformat())
        self.packet['run']['date'] = observed.date().isoformat()
        self.packet['coverage'].update(closeout_required=True, closeout_started_at=None)
        self.save_packet()
        destination = self.root / 'rolling-recovery'
        result = pipeline.checkpoint(self.root, destination, NOW, phase='preparing', week=WINDOW['from'])
        self.assertTrue(result['valid']); self.assertTrue(result['complete'])
        saved = pipeline.read(destination / self.folder.relative_to(self.root) / 'packet.json')
        self.assertEqual(saved['phase'], 'preparing')
        self.assertEqual(saved['observation_at'], observed.isoformat())
        self.assertFalse(saved['public_eligible'])
        # A closed job can cross the next Monday without losing its old namespace.
        self.packet.update(phase='closed', observation_at=NOW.isoformat())
        self.packet['run']['date'] = NOW.date().isoformat()
        self.packet['coverage'].update(closeout_required=False, closeout_started_at=NOW.isoformat())
        self.save_packet()
        result = pipeline.checkpoint(self.root, self.root / 'closed-recovery', NOW + dt.timedelta(days=7),
                                     week=WINDOW['from'])
        self.assertTrue(result['valid']); self.assertTrue(result['complete'])
        self.assertFalse(pipeline.edition_ready(self.root, NOW + dt.timedelta(days=7))['ready'])

    def test_complete_saved_closeout_repairs_adoption_without_network_replay(self):
        self.packet['coverage'].update(configured_query_status='complete_for_configured_queries', publisher_snapshots={'sources': []})
        self.save_packet(); (self.root / 'data/weekly.json').unlink()
        plan = pipeline.closeout_plan(self.root, NOW)
        self.assertTrue(plan['needed']); self.assertFalse(plan['collect_needed'])
        self.assertEqual(plan['status'], 'canonical_adoption_required')
        with patch.object(prep, 'prepare') as collect, patch.object(prep, 'adopt_to_canonical') as adopt:
            pipeline.run_closeout(self.root, NOW)
        collect.assert_not_called(); adopt.assert_called_once()

    def test_failure_checkpoint_commit_uses_clean_worktree_and_preserves_dirty_outputs(self):
        # All Git operations are local; no remote, fetch, push or external call.
        def git(*args, cwd=self.root):
            return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True)
        git('init', '-b', 'main')
        git('config', 'user.name', 'Offline fixture'); git('config', 'user.email', 'fixture@example.test')
        git('add', 'data/library.json'); git('commit', '-m', 'Baseline fixture')
        library = self.root / 'data/library.json'
        library.write_text('[{"unvalidated": "Keep original dirty output untouched"}]')
        stray = self.root / 'data/failed-build.json'; stray.write_text('{"unvalidated": true}')
        destination = self.root / 'recovery'
        pipeline.checkpoint(self.root, destination, NOW)
        worktree = self.root / 'save-worktree'
        result = pipeline.checkpoint_commit(self.root, destination, worktree)
        self.assertTrue(result['committed'])
        self.assertIn('Keep original dirty output', library.read_text())
        self.assertTrue(stray.exists())
        self.assertEqual(git('status', '--porcelain', cwd=worktree).stdout, '')
        git('rebase', 'main', cwd=worktree)
        self.assertEqual(pipeline.read(worktree / 'data/library.json'), [])
        self.assertFalse((worktree / 'data/failed-build.json').exists())
        self.assertTrue((worktree / self.folder.relative_to(self.root) / 'acquisition.json').exists())
        self.assertNotIn('library.json', git('show', '--format=', '--name-only', 'HEAD', cwd=worktree).stdout)

    def test_writing_stages_reject_interstep_rollover_before_external_work(self):
        monday = dt.datetime(2026, 11, 9, 0, 0, 1, tzinfo=dt.timezone.utc)
        runner = Mock()
        with patch.object(prep, 'prepare') as collect, patch.object(prep, 'adopt_to_canonical') as adopt:
            for phase, expected, operation in (
                    ('preparing', '2026-11-02', pipeline.run_preparation),
                    ('closed', '2026-10-26', pipeline.run_closeout)):
                with self.subTest(phase=phase), self.assertRaisesRegex(ValueError, 'scope_changed'):
                    operation(self.root, monday, expected_week=expected)
                with self.assertRaisesRegex(ValueError, 'scope_changed'):
                    pipeline.run_readings(self.root, monday, phase=phase, runner=runner, expected_week=expected)
            with self.assertRaisesRegex(ValueError, 'scope_changed'):
                pipeline.finalize(self.root, monday, expected_week='2026-10-26')
        collect.assert_not_called(); adopt.assert_not_called(); runner.assert_not_called()

    def test_actual_guard_instant_is_passed_unchanged_into_metadata_collection(self):
        sunday = dt.datetime(2026, 11, 8, 23, 59, 59, tzinfo=dt.timezone.utc)
        with patch.object(prep, 'prepare', return_value=self.packet) as collect:
            pipeline.run_preparation(self.root, sunday, expected_week='2026-11-02', max_requests=1)
        self.assertEqual(collect.call_args.kwargs['now'], sunday)
        self.assertEqual(collect.call_args.kwargs['max_requests'], 1)

    def test_checkpoint_strict_packet_and_snapshot_boundary_rejects_source_bodies(self):
        self.packet['raw_source'] = 'An arbitrary complete source body must never be retained.'
        self.save_packet()
        prep.atomic_save(self.folder / 'snapshots/unsafe.json', self.packet)
        destination = self.root / 'recovery'
        result = pipeline.checkpoint(self.root, destination, NOW)
        self.assertTrue(result['valid']); self.assertFalse(result['complete'])
        self.assertEqual(len(result['invalid_files']), 2)
        saved = destination / self.folder.relative_to(self.root)
        self.assertFalse((saved / 'packet.json').exists())
        self.assertFalse((saved / 'snapshots/unsafe.json').exists())
        self.assertTrue((saved / 'acquisition.json').exists())

    def test_lead_time_does_not_invent_review_throughput(self):
        report = pipeline.lead_time()
        self.assertEqual(report['known_downstream_minutes_excluding_review'], [253, 499])
        self.assertIsNone(report['full_review_completion_estimate'])
        self.assertEqual(report['full_review_throughput'], 'not_verified')


class WorkflowContractTests(unittest.TestCase):
    def test_all_shared_writers_are_serialized(self):
        for name in ('refresh', 'resume-weekly-discovery', 'weekly-source-acquisition', 'editorial-feed-snapshots',
                     'prepare-weekly-readings', 'finalize-weekly-readings'):
            text = (ROOT / '.github/workflows' / (name + '.yml')).read_text()
            self.assertIn('observatory-index', text)
            self.assertIn('queue: max', text)
            self.assertIn('cancel-in-progress: false', text)

    def test_final_chain_and_daily_staging_boundaries(self):
        daily = (ROOT / '.github/workflows/prepare-weekly-readings.yml').read_text()
        final = (ROOT / '.github/workflows/finalize-weekly-readings.yml').read_text()
        edition = (ROOT / '.github/workflows/weekly-edition.yml').read_text()
        self.assertNotIn('build_public.py', daily)
        self.assertNotIn('--closeout', daily)
        self.assertIn('preparation_pipeline.py prepare --expected-week', daily)
        self.assertNotIn('scripts/compose_issue.py', daily + final)
        self.assertIn('preparation_pipeline.py finalize', final)
        self.assertIn("':!data/weekly-preparation/**'", final)
        self.assertIn('["Finalize weekly source readings"]', edition)
        self.assertNotIn('Catch up full-text research backlog', edition)
        self.assertIn('steps.final_reading.outputs.ready', edition)
        for text in (daily, final):
            self.assertIn('timeout-minutes: 80', text)
            self.assertIn('if: always() && steps.checkpoint.outputs.valid', text)
            self.assertIn('validated-preparation/', text)
            self.assertIn('persist-credentials: false', text)

    def test_weekly_refresh_uses_one_closeout_and_keeps_other_modes(self):
        text = (ROOT / '.github/workflows/refresh.yml').read_text()
        start = text.index('      - name: Collect historical metadata')
        stop = text.index('      - name: Verify nominated', start)
        stage = text[start:stop]
        self.assertIn("if: env.MODE == 'backfill'", stage)
        self.assertIn('run: python scripts/update.py', stage)
        self.assertIn("if: env.MODE == 'weekly'", stage)
        self.assertIn('preparation_pipeline.py closeout', stage)
        self.assertIn("cron: '23 0 * * 1'", text)
        self.assertIn("cron: '37 6 * * 1'", text)


if __name__ == '__main__': unittest.main()

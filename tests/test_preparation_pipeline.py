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
            'review': {'attempted': 2, 'summaries_completed': 1, 'failed': 1, 'skipped_no_model': False,
                       'selection': {'considered': 2, 'eligible': 2, 'deferred_by_limit': 0, 'skipped': {}}},
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
        receipt = pipeline.read(self.folder / 'reading-run.json')
        receipt['stages']['review']['failed'] += 1; receipt['stages']['review']['attempted'] += 1
        receipt['stages']['review']['selection']['considered'] += 1
        receipt['stages']['review']['selection']['eligible'] += 1
        prep.atomic_save(self.folder / 'reading-run.json', receipt)
        self.assertFalse(pipeline.edition_ready(self.root, NOW)['ready'])
        self.assertFalse(pipeline.edition_ready(self.root, NOW + dt.timedelta(days=7))['ready'])

    def test_valid_stale_packet_is_a_read_only_hold_not_a_validation_bypass(self):
        self.receipt(); pipeline.finalize(self.root, NOW)
        self.packet['status'] = 'prepared'; self.save_packet()
        before = {p: p.read_bytes() for p in self.root.rglob('*.json')}
        with patch.object(pipeline.subprocess, 'run') as execute:
            result = pipeline.edition_ready(self.root, NOW)
        self.assertFalse(result['ready'])
        self.assertEqual(result['status'], 'reading_inputs_changed')
        self.assertEqual(result['changed_inputs'], ['packet.json'])
        self.assertEqual(result['next_action'], 'readings')
        execute.assert_not_called()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*.json')})
        with self.assertRaisesRegex(pipeline.ReadingInputsChanged, 'reading_inputs_changed'):
            pipeline.finalize(self.root, NOW)

    def test_stale_state_recovery_requires_the_actual_bounded_stage_sequence(self):
        self.receipt(); pipeline.finalize(self.root, NOW)
        self.state['provider_pauses']['provider:CORE'] = (NOW + dt.timedelta(hours=1)).isoformat()
        self.state['run']['active_provider_pauses'] = deepcopy(self.state['provider_pauses'])
        queue.seal_state(self.state)
        prep.atomic_save(self.folder / 'acquisition.json', self.state)
        result = pipeline.edition_ready(self.root, NOW)
        self.assertEqual(result['changed_inputs'], ['acquisition.json'])
        with self.assertRaises(pipeline.ReadingInputsChanged):
            pipeline.finalize(self.root, NOW)
        calls = []
        def stage(args, **kwargs):
            name = args[2]; calls.append((name, int(args[-1])))
            if name == 'review':
                bundle = readings.reconcile(self.packet, self.state, self.bundle, now=NOW)
                prep.atomic_save(self.folder / 'readings.json', bundle)
            return subprocess.CompletedProcess(args, 0, json.dumps(self.reports[name]))
        real_utc = pipeline.utc
        with patch.object(pipeline, 'utc', lambda value=None: real_utc(value or NOW)):
            pipeline.run_readings(self.root, NOW, runner=stage)
        self.assertEqual(calls, [('acquire', 12), ('review', 2), ('revalidate', 12), ('apply', 2)])
        self.assertFalse(pipeline.edition_ready(self.root, NOW)['ready'])
        pipeline.finalize(self.root, NOW)
        self.assertTrue(pipeline.edition_ready(self.root, NOW)['ready'])
        saved = pipeline.read(self.folder / 'acquisition.json')
        self.assertEqual(saved['provider_pauses'], self.state['provider_pauses'])

    def test_unchanged_finalization_is_idempotent_and_has_no_external_work(self):
        self.receipt(); pipeline.finalize(self.root, NOW)
        before = {p: p.read_bytes() for p in self.root.rglob('*.json')}
        with patch.object(pipeline.subprocess, 'run') as execute:
            first = pipeline.edition_ready(self.root, NOW)
            second = pipeline.edition_ready(self.root, NOW + dt.timedelta(hours=1))
        self.assertTrue(first['ready']); self.assertEqual(first, second)
        execute.assert_not_called()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*.json')})

    def test_new_packet_item_recovers_through_real_offline_reading_stages(self):
        from test_weekly_source_acquisition import item, document, result_for
        from test_prepared_article_readings import claim
        import comprehensive_readings
        self.receipt(); pipeline.finalize(self.root, NOW)
        moment = NOW + dt.timedelta(minutes=1)
        self.packet['observation_at'] = moment.isoformat()
        self.packet['items'] = [item(published='2026-11-04', kind='nonacademic')]
        self.save_packet()
        adoption = prep.adopt_closed_packet(self.packet, [], now=moment)
        library, weekly = adoption['library'], adoption['weekly']
        self.save('library.json', library); self.save('weekly.json', weekly)
        self.assertEqual(pipeline.edition_ready(self.root, moment)['status'], 'reading_inputs_changed')
        source = document(); calls = []
        state_path, bundle_path = self.folder / 'acquisition.json', self.folder / 'readings.json'
        def execute(args, **kwargs):
            stage = args[2]; limit = int(args[-1]); calls.append(stage)
            state, bundle = pipeline.read(state_path), pipeline.read(bundle_path)
            if stage == 'acquire':
                state = readings.acquire(self.packet, state, now=moment, limit=limit, known_sources_only=True,
                    attempt=lambda *args: result_for(source), clock=lambda: 0)
                prep.atomic_save(state_path, state); report = state['run']
            elif stage == 'review':
                with patch.object(comprehensive_readings, 'read_chunk', side_effect=claim):
                    bundle = readings.review(self.packet, state, bundle, model=Mock(), now=moment, limit=limit,
                        retriever=lambda record: (deepcopy(source), []))
                prep.atomic_save(bundle_path, bundle); report = bundle['review_run']
            elif stage == 'revalidate':
                bundle = readings.revalidate(self.packet, state, bundle, now=moment, limit=limit,
                    retriever=lambda record: (deepcopy(source), []))
                prep.atomic_save(bundle_path, bundle); report = bundle['revalidation_run']
            else:
                library, report = readings.apply_closed(self.packet, state, bundle,
                    pipeline.read(self.root / 'data/library.json'), weekly, now=moment)
                self.save('library.json', library)
            return subprocess.CompletedProcess(args, 0, json.dumps(report))
        real_utc = pipeline.utc
        with patch.object(pipeline, 'utc', lambda value=None: real_utc(value or moment)):
            run = pipeline.run_readings(self.root, moment, runner=execute)
        self.assertEqual(calls, ['acquire', 'review', 'revalidate', 'apply'])
        self.assertEqual(run['stages']['review']['summaries_completed'], 1)
        self.assertEqual(run['stages']['apply']['machine_checked_readings_applied'], 1)
        self.assertFalse(pipeline.edition_ready(self.root, moment)['ready'])
        final = pipeline.finalize(self.root, moment)
        self.assertEqual(final['coverage']['machine_checked_full_readings'], 1)
        self.assertFalse(final['approved'])
        with patch.object(pipeline.subprocess, 'run') as execute_again:
            self.assertTrue(pipeline.edition_ready(self.root, moment)['ready'])
            self.assertTrue(pipeline.edition_ready(self.root, moment + dt.timedelta(minutes=1))['ready'])
        execute_again.assert_not_called()

    def test_missing_receipts_are_distinct_from_stale_and_malformed_receipts(self):
        self.assertEqual(pipeline.edition_ready(self.root, NOW)['status'], 'awaiting_final_reading')
        self.receipt(); pipeline.finalize(self.root, NOW)
        run_path = self.folder / 'reading-run.json'; saved = run_path.read_bytes()
        run_path.unlink()
        result = pipeline.edition_ready(self.root, NOW)
        self.assertFalse(result['ready']); self.assertEqual(result['status'], 'awaiting_final_reading_run')
        self.assertEqual(result['next_action'], 'readings')
        run_path.write_bytes(saved)
        run = pipeline.read(run_path); run['stages']['review']['failed'] += 1; run['stages']['review']['attempted'] += 1
        run['stages']['review']['selection']['considered'] += 1
        run['stages']['review']['selection']['eligible'] += 1
        prep.atomic_save(run_path, run)
        self.assertEqual(pipeline.edition_ready(self.root, NOW)['status'], 'final_reading_inputs_changed')
        (self.folder / 'final-reading.json').unlink()
        run_path.write_text('{')
        with self.assertRaises(ValueError): pipeline.edition_ready(self.root, NOW)

    def test_malformed_receipts_fail_closed_even_when_other_inputs_are_stale(self):
        self.receipt(); pipeline.finalize(self.root, NOW)
        self.packet['status'] = 'prepared'; self.save_packet()
        for name in ('reading-run.json', 'final-reading.json'):
            path = self.folder / name; before = path.read_bytes()
            original = pipeline.read(path)
            variants = [[], {}, dict(original, schema_version=True), dict(original, approved=True),
                        dict(original, source_text_saved=True), dict(original, raw_source='Unsafe prose'),
                        dict(original, bindings={}), dict(original, publication_window={})]
            if name == 'reading-run.json':
                for bad in (True, -1, '1', None):
                    altered = deepcopy(original); altered['stages']['review']['attempted'] = bad
                    variants.append(altered)
                altered = deepcopy(original); altered['stages']['apply']['approved'] = True
                variants.append(altered)
                altered = deepcopy(original)
                altered['stages']['acquire']['checked_at'] = (NOW + dt.timedelta(minutes=1)).isoformat()
                variants.append(altered)
                variants.append(dict(original, finished_at='2099-01-01T00:00:00+00:00'))
            else:
                variants.extend([dict(original, status=True), dict(original, coverage=[]),
                                 dict(original, reading_run_sha256='invalid')])
            for value in variants:
                with self.subTest(name=name, value=value):
                    prep.atomic_save(path, value)
                    with self.assertRaisesRegex(ValueError, 'invalid_.*_receipt'):
                        pipeline.edition_ready(self.root, NOW)
            path.write_bytes(before)

    def test_receipts_cannot_add_nested_approvals_source_text_or_fabricated_coverage(self):
        self.receipt(); pipeline.finalize(self.root, NOW)
        run_path, final_path = self.folder / 'reading-run.json', self.folder / 'final-reading.json'
        run, final = pipeline.read(run_path), pipeline.read(final_path)
        for stage in ('acquire', 'review', 'revalidate', 'apply'):
            bad_run = deepcopy(run); bad_run['stages'][stage]['raw_source'] = 'Unsafe source body'
            bad_final = deepcopy(final); bad_final['reading_run_sha256'] = pipeline.digest(bad_run)
            prep.atomic_save(run_path, bad_run); prep.atomic_save(final_path, bad_final)
            with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, 'invalid_preparation_reading_run_receipt'):
                pipeline.edition_ready(self.root, NOW)
            with self.assertRaisesRegex(ValueError, 'invalid_preparation_reading_run_receipt'):
                pipeline.finalize(self.root, NOW)
        prep.atomic_save(run_path, run)
        for key, value in (('independent_approvals_granted_by_pipeline', 5),
                           ('expert_review_verified_by_pipeline', True), ('unknown', 'Unsafe source body'),
                           ('machine_checked_full_readings', 999)):
            bad = deepcopy(final); bad['coverage'][key] = value; prep.atomic_save(final_path, bad)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'invalid_weekly_final_reading_.*receipt'):
                pipeline.edition_ready(self.root, NOW)

    def test_missing_receipt_never_masks_invalid_present_staging(self):
        for name in ('acquisition.json', 'readings.json'):
            path = self.folder / name; before = path.read_bytes()
            for invalid in (None, {}, {'unknown': 'Unsafe source body'}):
                prep.atomic_save(path, invalid)
                with self.subTest(name=name, invalid=invalid), self.assertRaises(ValueError):
                    pipeline.edition_ready(self.root, NOW)
            path.write_bytes(before)
        (self.folder / 'acquisition.json').unlink(); (self.folder / 'readings.json').unlink()
        result = pipeline.edition_ready(self.root, NOW)
        self.assertFalse(result['ready']); self.assertEqual(result['status'], 'awaiting_final_reading')

    def test_invalid_staging_is_never_misclassified_as_recoverable_staleness(self):
        self.receipt(); pipeline.finalize(self.root, NOW)
        self.packet['status'] = 'prepared'; self.save_packet()
        for name in ('packet.json', 'acquisition.json', 'readings.json'):
            path = self.folder / name; before = path.read_bytes(); value = pipeline.read(path)
            if name == 'packet.json': value['approved'] = True
            elif name == 'acquisition.json': value['state_sha256'] = '0' * 64
            else: value['metadata_sha256'] = '0' * 64
            prep.atomic_save(path, value)
            with self.subTest(name=name), self.assertRaises(ValueError) as error:
                pipeline.edition_ready(self.root, NOW)
            self.assertNotIsInstance(error.exception, pipeline.ReadingInputsChanged)
            path.write_bytes(before)
        self.state['publication_window'] = {'from': '2026-10-26', 'to': '2026-11-01', 'timezone': 'UTC'}
        queue.seal_state(self.state); prep.atomic_save(self.folder / 'acquisition.json', self.state)
        with self.assertRaisesRegex(ValueError, 'reading_acquisition_window_mismatch'):
            pipeline.edition_ready(self.root, NOW)

    def test_other_canonical_writers_invalidate_receipt_without_recopying_staged_notes(self):
        self.receipt(); pipeline.finalize(self.root, NOW)
        for name, value in (('library.json', [{'title': 'New independently written library metadata'}]),
                            ('weekly.json', dict(pipeline.read(self.root / 'data/weekly.json'), extra='New snapshot'))):
            path = self.root / 'data' / name; before = path.read_bytes()
            prep.atomic_save(path, value)
            result = pipeline.edition_ready(self.root, NOW)
            self.assertFalse(result['ready']); self.assertEqual(result['status'], 'final_reading_inputs_changed')
            self.assertEqual(result['changed_inputs'], [name])
            self.assertEqual(pipeline.read(path), value)
            with self.assertRaisesRegex(ValueError, 'current_final_reading_run_required'):
                pipeline.finalize(self.root, NOW)
            path.write_bytes(before)
        # Unchanged local projections can still be finalized idempotently.
        self.assertEqual(pipeline.finalize(self.root, NOW), pipeline.read(self.folder / 'final-reading.json'))

    def test_changed_source_receipts_hold_finalization_and_discard_stale_notes(self):
        from test_weekly_source_acquisition import item, document, result_for
        from test_prepared_article_readings import claim
        import comprehensive_readings
        self.packet['items'] = [item(published='2026-11-04', kind='nonacademic')]; self.save_packet()
        self.save('weekly.json', prep.closed_packet(self.packet, NOW))
        original_document = document(); original_document.source_bytes = b'%PDF-original'
        state = readings.acquire(self.packet, now=NOW, known_sources_only=True,
            attempt=lambda *args: result_for(original_document), clock=lambda: 0)
        with patch.object(comprehensive_readings, 'read_chunk', side_effect=claim):
            bundle = readings.review(self.packet, state, model=Mock(), now=NOW,
                retriever=lambda record: (deepcopy(original_document), []))
        bundle = readings.revalidate(self.packet, state, bundle, now=NOW,
            retriever=lambda record: (deepcopy(original_document), []))
        self.assertEqual(next(iter(bundle['records'].values()))['revalidation']['status'], 'source_revalidated')
        prep.atomic_save(self.folder / 'acquisition.json', state)
        prep.atomic_save(self.folder / 'readings.json', bundle)
        self.receipt(); pipeline.finalize(self.root, NOW)
        for kind in ('source_url', 'version', 'text', 'bytes'):
            changed = deepcopy(original_document)
            if kind == 'source_url': changed.url = 'https://www.econstor.eu/changed.pdf'
            elif kind == 'version': changed.version = 'acceptedVersion'
            elif kind == 'text': changed.units[0]['text'] += ' Changed source content.'
            else: changed.source_bytes = b'%PDF-changed'
            replacement = readings.acquire(self.packet, now=NOW, known_sources_only=True,
                attempt=lambda *args: result_for(changed), clock=lambda: 0)
            prep.atomic_save(self.folder / 'acquisition.json', replacement)
            with self.subTest(kind=kind):
                result = pipeline.edition_ready(self.root, NOW)
                self.assertEqual(result['changed_inputs'], ['acquisition.json'])
                self.assertFalse(result['ready'])
                with self.assertRaises(pipeline.ReadingInputsChanged): pipeline.finalize(self.root, NOW)
                reconciled = readings.reconcile(self.packet, replacement, bundle, now=NOW)
                staged = next(iter(reconciled['records'].values()))
                self.assertNotIn('deep_analysis', staged['record']); self.assertNotIn('revalidation', staged)
                output, report = readings.apply_closed(self.packet, replacement, bundle,
                    self.packet['items'], prep.closed_packet(self.packet, NOW), now=NOW)
                self.assertEqual(report['machine_checked_readings_applied'], 0)
                self.assertNotIn('deep_analysis', output[0])

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

    def test_valid_final_receipt_does_not_hide_more_due_readings(self):
        self.receipt(); pipeline.finalize(self.root, NOW)
        self.assertTrue(pipeline.edition_ready(self.root,NOW)['ready'])
        with patch('comprehensive_readings.reading_candidates',return_value=([{'id':'pending'}],{'eligible':1})):
            plan=pipeline.worker_plan(self.root,NOW)
        self.assertFalse(plan['ready'])
        self.assertEqual(plan['status'],'more_readings_due')
        self.assertTrue(pipeline.edition_ready(self.root,NOW)['ready'])

    def test_publication_waits_for_due_readings_rather_than_freezing_early(self):
        self.receipt(); pipeline.finalize(self.root,NOW)
        with patch('comprehensive_readings.reading_candidates',return_value=([{'id':'pending'}],{'eligible':1})):
            self.assertFalse(pipeline.edition_ready(self.root,NOW)['ready'])

    def test_cutoff_releases_only_current_checked_subset_and_does_not_stop_readers(self):
        self.receipt(); pipeline.finalize(self.root,NOW)
        late = NOW.replace(hour=17)
        with patch('comprehensive_readings.reading_candidates',return_value=([{'id':'pending'}],{'eligible':1})):
            self.assertFalse(pipeline.edition_ready(self.root,NOW,allow_partial=True)['ready'])
            result = pipeline.edition_ready(self.root,late,allow_partial=True)
            self.assertTrue(result['ready'])
            self.assertEqual(result['status'],'checked_subset_at_cutoff')
            self.assertEqual(result['pending_readings'],1)
            self.assertFalse(pipeline.worker_plan(self.root,late)['ready'])
            # A missing final receipt remains a blocker even after the cutoff.
            (self.folder/'final-reading.json').unlink()
            self.assertFalse(pipeline.edition_ready(self.root,late,allow_partial=True)['ready'])


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
        self.assertIn("cron: '7 0,2,6,10 * * 1'", text)
        self.assertIn('timezone: America/New_York',text)

    def test_reading_runs_require_a_lease_and_a_successful_cloud_save(self):
        for name in ('prepare-weekly-readings','finalize-weekly-readings'):
            text=(ROOT/'.github/workflows'/f'{name}.yml').read_text()
            self.assertIn('worker_run.py begin',text)
            self.assertIn("if: steps.worker.outputs.claimed == 'true'",text)
            self.assertIn("steps.saved.outcome == 'success'",text)
            self.assertIn('worker_run.py finish',text)
            self.assertIn('timezone: America/New_York',text)
        final=(ROOT/'.github/workflows/finalize-weekly-readings.yml').read_text()
        self.assertIn('preparation_pipeline.py worker-plan',final)
        self.assertIn('[run-readings]',final)


if __name__ == '__main__': unittest.main()

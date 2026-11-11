"""Offline canonical-scope and opt-in Git evidence tests. No source/model calls."""
from copy import deepcopy
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import preparation_pipeline as pipeline
import reading_receipt_reconciliation as reconciliation
import test_preparation_pipeline as fixture
from test_weekly_source_acquisition import item

NOW = fixture.NOW


class CanonicalBindingTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.PipelineTests()
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root, self.folder = self.f.root, self.f.folder
        self.current = item(published='2026-11-05', reading={'level': 'abstract'}, abstract_text='Unchanged evidence')
        self.historical = item(2, published='2024-01-01', reading={'level': 'abstract'})
        self.f.save('library.json', [self.current, self.historical])
        hints = pipeline.ROOT / 'data/fulltext-source-hints.json'
        if hints.exists():
            self.f.save('fulltext-source-hints.json', pipeline.read(hints))

    def finalize(self, legacy=False):
        self.f.receipt()
        result = pipeline.finalize(self.root, NOW)
        if legacy:
            # Offline fixture for the old producer, not a production migration.
            result.pop('binding_policy_version')
            result['bindings'] = pipeline.bindings(self.root, self.folder, canonical=True, binding_policy_version=1)
            fixture.prep.atomic_save(self.folder / 'final-reading.json', result)
        return result

    def hold(self, **kwargs):
        result = pipeline.edition_ready(self.root, NOW, **kwargs)
        self.assertFalse(result['ready']); self.assertEqual(result['status'], 'final_reading_inputs_changed')
        with self.assertRaisesRegex(ValueError, 'current_final_reading_run_required'):
            pipeline.finalize(self.root, NOW)
        return result

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def repository(self):
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Offline fixture')
        self.git('config', 'user.email', 'fixture@example.test')
        self.commit('Exact finalized baseline')
        return self.git('rev-parse', 'HEAD')

    def commit(self, message):
        self.git('add', 'data'); self.git('commit', '-m', message)

    def test_future_historical_backfill_does_not_rebind_or_restart_readings(self):
        receipt = self.finalize()
        old_receipt = (self.folder / 'final-reading.json').read_bytes()
        historical = dict(self.historical, analysis={'results': 'New historical reading'}, fulltext_attempt={'next_at': '2027-01-01'})
        self.f.save('library.json', [item(3, published='2025-01-01'), self.current, historical])
        before = {p: p.read_bytes() for p in self.root.rglob('*.json')}
        with patch.object(pipeline.subprocess, 'run') as execute:
            for moment in (NOW, NOW + dt.timedelta(hours=1)):
                self.assertTrue(pipeline.edition_ready(self.root, moment)['ready'])
                self.assertEqual(pipeline.finalize(self.root, moment), receipt)
        execute.assert_not_called()
        self.assertEqual((self.folder / 'final-reading.json').read_bytes(), old_receipt)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*.json')})
        self.f.save('library.json', [self.current])
        self.assertTrue(pipeline.edition_ready(self.root, NOW)['ready'])

    def test_same_week_entire_record_and_ineligible_candidates_remain_bound(self):
        self.current.update(source_quality={'decision': 'hold'}, historical_backfill=True)
        self.f.save('library.json', [self.current, self.historical]); self.finalize()
        for key, value in (
            ('title', 'Changed title'), ('abstract_text', 'Changed source text'),
            ('open_access_url', 'https://example.test/new-source'), ('url', 'https://example.test/new-identity'),
            ('analysis', {'results': 'Changed findings'}), ('license', 'CC BY-ND'),
            ('document_version', 'acceptedVersion'), ('source_review', {'approved': True}),
            ('original_reading', {'approval': {'status': 'revoked'}}), ('published', '2026-10-30'),
            ('publication_date_provenance', {'status': 'conflict'}),
            ('fulltext_attempt', {'next_at': '2027-01-01'})):
            with self.subTest(key=key):
                self.f.save('library.json', [dict(self.current, **{key: value}), self.historical])
                self.assertEqual(self.hold()['changed_inputs'], ['library.json'])
        self.f.save('library.json', [self.current, self.historical, item(3, published='2026-11-03')])
        self.hold()
        self.f.save('library.json', [self.historical]); self.hold()

    def test_policy_and_approval_registry_changes_hold(self):
        self.finalize()
        for name in pipeline.CANONICAL_POLICY_INPUTS:
            path = self.root / 'data' / name
            previous = path.read_bytes() if path.exists() else None
            with self.subTest(name=name):
                self.f.save(name, {'entries': [], 'policy_changed': True})
                self.hold()
                if previous is None: path.unlink()
                else: path.write_bytes(previous)

    def test_correction_and_lineage_identity_closure_binds_raw_historical_rows(self):
        raw = item(3, kind='nonacademic', published='2024-01-01', doi='', url='https://example.test/old')
        correction = {'entries': [{'match_title': raw['title'], 'canonical_title': 'Corrected',
            'canonical_url': 'https://example.test/current', 'published': '2026-11-04'}]}
        self.f.save('editorial-corrections.json', correction)
        self.f.save('library.json', [raw]); self.finalize()
        self.f.save('library.json', [dict(raw, authors=['Changed'])]); self.hold()
        # Existing current-week identity can also depend on an older linked row.
        self.f.save('library.json', [raw])
        final = self.folder / 'final-reading.json'; final.unlink()
        self.f.save('editorial-corrections.json', {'entries': []})
        current = dict(self.current, companion_to=self.historical['doi'])
        self.f.save('library.json', [current, self.historical]); self.finalize()
        self.f.save('library.json', [current, dict(self.historical, abstract_text='Changed linked source')]); self.hold()

    def test_malformed_library_and_duplicate_identity_fail_closed(self):
        self.finalize()
        for value in (None, {}, [None], [self.current, self.current]):
            with self.subTest(value=value):
                self.f.save('library.json', value)
                with self.assertRaises(ValueError): pipeline.edition_ready(self.root, NOW)

    def test_unknown_binding_policy_and_policy_downgrade_cannot_bypass_gate(self):
        saved = self.finalize()
        path = self.folder / 'final-reading.json'
        for version in (0, 3, True, '2'):
            fixture.prep.atomic_save(path, dict(saved, binding_policy_version=version))
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'invalid_weekly_final_reading_receipt'):
                pipeline.edition_ready(self.root, NOW)
        downgraded = deepcopy(saved); downgraded.pop('binding_policy_version')
        fixture.prep.atomic_save(path, downgraded); self.hold()

    def test_legacy_receipt_stays_legacy_until_real_new_execution(self):
        old = self.finalize(legacy=True)
        self.assertTrue(pipeline.edition_ready(self.root, NOW)['ready'])
        self.assertEqual(pipeline.finalize(self.root, NOW), old)
        self.f.save('library.json', [self.current, dict(self.historical, title='Historical edit')])
        self.hold()
        self.assertEqual(pipeline.read(self.folder / 'final-reading.json'), old)
        # A fresh execution, not a receipt rewrite, may use the new binding policy.
        moment = NOW + dt.timedelta(minutes=1)
        real_utc = pipeline.utc
        runner = fixture.Mock(side_effect=lambda args, **kw: subprocess.CompletedProcess(
            args, 0, json.dumps(dict(self.f.reports[args[2]], **(
                {'checked_at': moment.isoformat()} if args[2] == 'acquire' else {})))))
        with patch.object(pipeline, 'utc', lambda value=None: real_utc(value or moment)):
            pipeline.run_readings(self.root, moment, runner=runner)
        self.assertEqual(pipeline.finalize(self.root, moment)['binding_policy_version'], 2)

    def test_optional_history_proof_is_read_only_and_default_still_holds(self):
        self.finalize(legacy=True); baseline = self.repository()
        self.f.save('library.json', [self.current, dict(self.historical, title='Historical edit')])
        self.commit('Unrelated historical backfill')
        before = {p: p.read_bytes() for p in self.root.rglob('*.json')}
        self.hold()
        with patch('full_document_access.request') as source, patch('comprehensive_readings.read_chunk') as model:
            for _ in range(2):
                result = pipeline.edition_ready(self.root, NOW, reconcile_legacy=True)
                self.assertTrue(result['ready'])
                self.assertEqual(result['reconciliation']['baseline_commit'], baseline)
        source.assert_not_called(); model.assert_not_called()
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*.json')})

    def test_missing_shallow_ambiguous_or_unbound_history_holds(self):
        receipt = self.finalize(legacy=True)
        self.f.save('library.json', [self.current, dict(self.historical, title='Changed')])
        self.hold(reconcile_legacy=True)  # No Git repository.
        self.repository()  # Receipt is present, but its bound library is not.
        self.hold(reconcile_legacy=True)
        self.f.save('library.json', [self.current, self.historical]); self.commit('Restore exact library')
        # Receipt-path history still only points to the inconsistent first commit.
        self.f.save('library.json', [self.current]); self.hold(reconcile_legacy=True)
        path = self.folder / 'final-reading.json'
        changed = dict(receipt, completed_at=(NOW - dt.timedelta(seconds=1)).isoformat())
        fixture.prep.atomic_save(path, changed); self.commit('Different historical receipt')
        fixture.prep.atomic_save(path, receipt)
        self.f.save('library.json', [self.current, self.historical]); self.commit('Restore receipt')
        self.f.save('library.json', [self.current]); self.hold(reconcile_legacy=True)  # Two matching receipts.
        (self.root / '.git/shallow').write_text(self.git('rev-parse', 'HEAD') + '\n')
        self.hold(reconcile_legacy=True)

    def test_promisor_clone_evidence_holds_before_any_lazy_fetch(self):
        self.finalize(legacy=True); self.repository()
        self.f.save('library.json', [self.current, dict(self.historical, title='Historical edit')])
        self.assertTrue(pipeline.edition_ready(self.root, NOW, reconcile_legacy=True)['ready'])
        self.git('config', 'remote.origin.promisor', 'true')
        self.hold(reconcile_legacy=True)

    def test_equivalent_complete_baselines_are_one_content_proof(self):
        receipt = self.finalize(legacy=True); self.repository()
        # Different serialization makes another receipt-path commit but carries
        # exactly the same receipt and all bound inputs/policy content.
        (self.folder / 'final-reading.json').write_text(json.dumps(receipt, sort_keys=True))
        self.commit('Equivalent exact baseline')
        self.f.save('library.json', [self.current, dict(self.historical, title='Historical edit')])
        self.assertTrue(pipeline.edition_ready(self.root, NOW, reconcile_legacy=True)['ready'])

    def test_history_proof_rejects_meaningful_input_and_receipt_changes(self):
        saved = self.finalize(legacy=True); self.repository()
        self.f.save('library.json', [self.current, dict(self.historical, title='Changed')])
        for key, value in (('abstract_text', 'New text'), ('license', 'CC BY'),
                           ('document_version', 'v2'), ('source_review', {'approved': True}),
                           ('published', '2024-01-01'), ('open_access_url', 'https://example.test/new')):
            with self.subTest(key=key):
                self.f.save('library.json', [dict(self.current, **{key: value}), self.historical])
                self.hold(reconcile_legacy=True)
        self.f.save('library.json', [self.current, dict(self.historical, title='Changed')])
        for name in pipeline.CANONICAL_POLICY_INPUTS:
            path = self.root / 'data' / name; old = path.read_bytes() if path.exists() else None
            self.f.save(name, {'changed': True}); self.hold(reconcile_legacy=True)
            if old is None: path.unlink()
            else: path.write_bytes(old)
        tampered = deepcopy(saved); tampered['coverage']['machine_checked_full_readings'] = 999
        fixture.prep.atomic_save(self.folder / 'final-reading.json', tampered)
        self.hold(reconcile_legacy=True)  # Exact saved receipt no longer in history.
        fixture.prep.atomic_save(self.folder / 'final-reading.json', saved)
        weekly = pipeline.read(self.root / 'data/weekly.json')
        self.f.save('weekly.json', dict(weekly, changed=True)); self.hold(reconcile_legacy=True)

    def test_optional_mode_never_hides_malformed_receipts_or_old_reading_policy(self):
        saved = self.finalize(legacy=True); self.repository()
        self.f.save('library.json', [self.current, dict(self.historical, title='Historical edit')])
        path = self.folder / 'final-reading.json'
        fixture.prep.atomic_save(path, dict(saved, approved=True))
        with self.assertRaisesRegex(ValueError, 'invalid_weekly_final_reading_receipt'):
            pipeline.edition_ready(self.root, NOW, reconcile_legacy=True)
        fixture.prep.atomic_save(path, saved)
        run_path = self.folder / 'reading-run.json'
        run = pipeline.read(run_path); run['reading_policy_version'] = 1
        fixture.prep.atomic_save(run_path, run)
        result = pipeline.edition_ready(self.root, NOW, reconcile_legacy=True)
        self.assertFalse(result['ready']); self.assertEqual(result['status'], 'final_reading_policy_changed')

    def test_only_edition_precheck_explicitly_opts_in_with_full_history(self):
        root = Path(__file__).resolve().parents[1]
        edition = (root / '.github/workflows/weekly-edition.yml').read_text()
        finalizer = (root / '.github/workflows/finalize-weekly-readings.yml').read_text()
        self.assertIn('preparation_pipeline.py edition-check --reconcile-legacy-library', edition)
        self.assertIn('fetch-depth: 0', edition)
        self.assertNotIn('--reconcile-legacy-library', finalizer)
        result = subprocess.run([sys.executable, str(root / 'scripts/preparation_pipeline.py'),
            'finalize', '--reconcile-legacy-library'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('only supported for edition-check', result.stderr)

    def arxiv(self):
        from test_weekly_source_acquisition import arxiv_item
        record = arxiv_item(published='2026-11-05', reading={'level': 'abstract'})
        record['publication_date_provenance']['value'] = '2026-11-05'
        record['publication_date_provenance']['raw'] = '2026-11-05T10:00:00Z'
        return record

    def retry(self, record):
        result = deepcopy(record)
        result['fulltext_attempt'] = {'attempts': 1, 'last_at': NOW.isoformat(), 'pipeline_version': 3,
            'status': 'waiting_for_license', 'next_at': (NOW + dt.timedelta(days=14)).isoformat()}
        result['open_access_url'] = 'https://arxiv.org/abs/2610.12345'
        return result

    def test_exact_known_arxiv_alias_and_license_wait_reconcile_without_rewriting(self):
        record = self.arxiv(); self.f.save('library.json', [record, self.historical])
        saved = self.finalize(legacy=True); self.repository()
        after = self.retry(record)
        self.f.save('library.json', [after, dict(self.historical, analysis={'new': 'Historical'})])
        result = pipeline.edition_ready(self.root, NOW, reconcile_legacy=True)
        self.assertTrue(result['ready'])
        self.assertEqual(pipeline.read(self.folder / 'final-reading.json'), saved)
        self.assertEqual(pipeline.read(self.root / 'data/library.json')[0]['fulltext_attempt'], after['fulltext_attempt'])
        self.hold()  # Default and finalization never reinterpret the old receipt.

    def test_redundant_route_test_does_not_accept_wrong_urls_or_malformed_retries(self):
        record = self.arxiv(); self.f.save('library.json', [record]); self.finalize(legacy=True); self.repository()
        after = self.retry(record)
        for url in ('https://example.test/wrong', 'https://arxiv.org/abs/2610.12345v2',
                    'https://arxiv.org/abs/2610.12345?token=x', 'https://user@arxiv.org/abs/2610.12345',
                    'https://arxiv.org/abs/2610.99999'):
            with self.subTest(url=url):
                self.f.save('library.json', [dict(after, open_access_url=url)])
                self.hold(reconcile_legacy=True)
        for key, value in (('attempts', True), ('attempts', 0), ('unknown', 'Untrusted body'),
                           ('status', 'source_unavailable'), ('status', 'success'), ('pipeline_version', 4),
                           ('last_at', (NOW + dt.timedelta(seconds=1)).isoformat()), ('next_at', NOW.isoformat())):
            with self.subTest(key=key, value=value):
                bad = deepcopy(after); bad['fulltext_attempt'][key] = value
                self.f.save('library.json', [bad]); self.hold(reconcile_legacy=True)

    def test_license_wait_cannot_clear_existing_cooldown_or_mask_reviewed_source(self):
        record = self.arxiv(); after = self.retry(record)
        old = deepcopy(after); old.pop('open_access_url')
        self.assertTrue(reconciliation._same_record(old, after, fixture.WINDOW, NOW, self.root))
        for key, value in (('attempts', 0), ('next_at', (NOW + dt.timedelta(days=1)).isoformat()),
                           ('last_at', (NOW - dt.timedelta(days=1)).isoformat())):
            bad = deepcopy(after); bad['fulltext_attempt'][key] = value
            try: same = reconciliation._same_record(old, bad, fixture.WINDOW, NOW, self.root)
            except ValueError: same = False
            self.assertFalse(same)
        bad = deepcopy(after); bad.pop('fulltext_attempt')
        self.assertFalse(reconciliation._same_record(old, bad, fixture.WINDOW, NOW, self.root))
        for key in ('analysis', 'deep_analysis', 'source_review', 'original_reading', 'approved',
                    'approval', 'original_summary', 'source_checked', 'review_status', 'digest'):
            before = dict(record, **{key: {'reviewed': True}})
            changed = self.retry(before)
            self.assertFalse(reconciliation._same_record(before, changed, fixture.WINDOW, NOW, self.root))
        for key in ('original_summary', 'approved', 'approval', 'review_status', 'digest', 'status'):
            before = deepcopy(record); before['reading'][key] = 'Accepted summary'
            self.assertFalse(reconciliation._same_record(before, self.retry(before), fixture.WINDOW, NOW, self.root))


if __name__ == '__main__': unittest.main()

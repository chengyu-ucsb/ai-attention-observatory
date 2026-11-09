"""Canonical reader recovery uses local Git only; no sources or models run."""
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_weekly_source_acquisition import queue, item, document, result_for, weekly, NOW
import acquisition_handoff as handoff
import source_access_controls as controls
import reading_checkpoint as checkpoint

ROOT = Path(__file__).resolve().parents[1]


class ReadingCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'; self.root.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Offline fixture'); self.git('config', 'user.email', 'fixture@example.test')
        self.record = item(kind='nonacademic')
        self.doc = document(); self.doc.url = self.record['url']; self.doc.version = 'unspecified'
        self.state = queue.run(weekly(self.record), now=NOW, known_sources_only=True,
            attempt=lambda *args: result_for(self.doc), clock=lambda: 0)
        self.save(checkpoint.LIBRARY, [self.record]); self.save(checkpoint.ACQUISITION, self.state)
        self.git('add', 'data'); self.git('commit', '-m', 'Baseline')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.destination = Path(self.tmp.name) / 'snapshot'
        self.worktree = Path(self.tmp.name) / 'save-tree'

    def git(self, *args, cwd=None):
        return subprocess.run(['git', *args], cwd=cwd or self.root, check=True,
                              capture_output=True, text=True).stdout

    def save(self, relative, value):
        target = self.root / relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2) + '\n')

    def request_refresh(self):
        changed = deepcopy(self.doc); changed.units[0]['text'] += ' New evidence.'
        key = queue.record_key(self.record)
        note = handoff.receipt_change_note(self.record, self.state['records'][key], changed, queue)
        self.state = controls.merge_diagnostics_into_state(self.state, [note], now=NOW)
        self.save(checkpoint.ACQUISITION, self.state)

    def valid_failure_library(self):
        record = deepcopy(self.record)
        record['complete_reading_attempt'] = {'status': 'acquisition_receipt_content_changed',
            'stage': 'retrieval', 'last_at': NOW.date().isoformat(),
            'next_at': (NOW + timedelta(days=2)).date().isoformat(), 'provider_diagnostics': []}
        return [record]

    def test_failed_reading_saves_only_valid_source_metadata_in_clean_worktree(self):
        self.request_refresh()
        library = self.root / checkpoint.LIBRARY
        library.write_text('TRUNCATED invalid library output')
        self.save('data/stray-source.json', {'source_text': 'DO_NOT_SAVE'})
        result = checkpoint.snapshot(self.root, self.destination, now=NOW)
        self.assertEqual(result['validated_files'], [checkpoint.ACQUISITION])
        with patch.object(queue.access, 'retrieve', side_effect=AssertionError('never retrieve')), \
             patch('comprehensive_readings.process', side_effect=AssertionError('never read')):
            committed = checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        self.assertTrue(committed['committed'])
        self.assertEqual(self.git('status', '--porcelain', cwd=self.worktree), '')
        self.assertEqual(library.read_text(), 'TRUNCATED invalid library output')
        self.assertTrue((self.root / 'data/stray-source.json').exists())
        self.assertFalse((self.worktree / 'data/stray-source.json').exists())
        self.assertEqual(json.loads((self.worktree / checkpoint.LIBRARY).read_text()), [self.record])
        saved = json.loads((self.worktree / checkpoint.ACQUISITION).read_text()); queue.validate_state(saved)
        self.assertEqual(saved, self.state)
        self.assertEqual(self.git('show', '--format=', '--name-only', 'HEAD', cwd=self.worktree).strip(), checkpoint.ACQUISITION)
        self.assertNotIn('PRIVATE_SOURCE_SENTINEL', json.dumps(saved))

    def test_successful_reader_validates_notes_and_receipts_before_clean_commit(self):
        self.request_refresh(); library = self.valid_failure_library(); self.save(checkpoint.LIBRARY, library)
        result = checkpoint.snapshot(self.root, self.destination, include_library=True, now=NOW)
        self.assertEqual(result['validated_files'], [checkpoint.LIBRARY, checkpoint.ACQUISITION])
        checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        self.assertEqual(json.loads((self.worktree / checkpoint.LIBRARY).read_text()), library)
        self.assertEqual(set(self.git('show', '--format=', '--name-only', 'HEAD', cwd=self.worktree).split()),
                         {checkpoint.LIBRARY, checkpoint.ACQUISITION})
        self.assertEqual(json.loads((self.root / checkpoint.LIBRARY).read_text()), library)
        self.assertEqual(self.git('rev-parse', 'HEAD').strip(), self.base)

    def test_new_full_and_partial_machine_notes_pass_the_same_closed_schema(self):
        from test_prepared_article_readings import reading, claim
        for complete in (True, False):
            library = [deepcopy(self.record)]
            doc = deepcopy(self.doc)
            if not complete:
                doc.coverage['evidence_status'] = 'partial_full_text'
            with patch.object(reading, 'read_chunk', side_effect=claim):
                stats = reading.process(library, Mock(), retriever=lambda _: (doc, []), run_date=NOW.date())
            self.assertEqual(stats['summaries_completed'], 1)
            self.save(checkpoint.LIBRARY, library)
            target = Path(self.tmp.name) / ('full' if complete else 'partial')
            result = checkpoint.snapshot(self.root, target, include_library=True, now=NOW)
            self.assertTrue(result['complete'])
            self.assertIn(checkpoint.LIBRARY, result['validated_files'])
            self.assertNotIn(self.doc.units[0]['text'], (target / checkpoint.LIBRARY).read_text())
            checkpoint.commit(self.root, target, Path(self.tmp.name) / ('full-save' if complete else 'partial-save'), now=NOW)

    def test_invalid_new_library_does_not_erase_independently_valid_acquisition(self):
        self.request_refresh()
        for number, mutate in enumerate((
                lambda r: r.update(raw_source='DO_NOT_SAVE'),
                lambda r: r.update(approved=True),
                lambda r: r.update(title='Changed identity'),
                lambda r: r['complete_reading_attempt'].update(raw_source='DO_NOT_SAVE'),
                lambda r: r['complete_reading_attempt'].update(status='summarized', stage='synthesis'))):
            library = self.valid_failure_library(); mutate(library[0]); self.save(checkpoint.LIBRARY, library)
            target = Path(self.tmp.name) / f'invalid-{number}'
            result = checkpoint.snapshot(self.root, target, include_library=True, now=NOW)
            self.assertTrue(result['valid']); self.assertFalse(result['complete'])
            self.assertEqual(result['invalid_files'], [checkpoint.LIBRARY])
            self.assertFalse((target / checkpoint.LIBRARY).exists())
            self.assertTrue((target / checkpoint.ACQUISITION).exists())
            checkpoint.commit(self.root, target, Path(self.tmp.name) / f'saved-{number}', now=NOW)

    def test_changed_legacy_analysis_is_not_granted_approval_by_delta_validation(self):
        old = deepcopy(self.record); old['deep_analysis'] = {'version': 2, 'legacy': 'unchanged'}
        new = self.valid_failure_library()[0]; new['deep_analysis'] = deepcopy(old['deep_analysis'])
        checkpoint.validate_library([new], [old], NOW)
        new['deep_analysis']['approved'] = True
        with self.assertRaises(ValueError): checkpoint.validate_library([new], [old], NOW)

    def test_invalid_acquisition_is_never_saved_even_if_library_validates(self):
        bad = deepcopy(self.state); bad['raw_source'] = 'DO_NOT_SAVE'; self.save(checkpoint.ACQUISITION, bad)
        self.save(checkpoint.LIBRARY, self.valid_failure_library())
        result = checkpoint.snapshot(self.root, self.destination, include_library=True, now=NOW)
        self.assertFalse(result['valid']); self.assertEqual(result['invalid_files'], [checkpoint.ACQUISITION])
        self.assertFalse((self.destination / checkpoint.LIBRARY).exists())
        with self.assertRaises(ValueError): checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        self.assertFalse(self.worktree.exists())

    def test_absent_acquisition_still_allows_valid_ordinary_reading_changes(self):
        (self.root / checkpoint.ACQUISITION).unlink()
        self.git('add', checkpoint.ACQUISITION); self.git('commit', '-m', 'Fixture without acquisition')
        self.save(checkpoint.LIBRARY, self.valid_failure_library())
        result = checkpoint.snapshot(self.root, self.destination, include_library=True, now=NOW)
        self.assertEqual(result['validated_files'], [checkpoint.LIBRARY])
        checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        self.assertFalse((self.worktree / checkpoint.ACQUISITION).exists())
        checkpoint.verify_rebased(self.root, self.destination, self.worktree, now=NOW)
        (self.worktree / checkpoint.ACQUISITION).write_text(json.dumps(self.state))
        self.git('add', checkpoint.ACQUISITION, cwd=self.worktree)
        self.git('commit', '-m', 'New acquisition arrived', cwd=self.worktree)
        with self.assertRaisesRegex(ValueError, 'rebased_reading_checkpoint_changed'):
            checkpoint.verify_rebased(self.root, self.destination, self.worktree, now=NOW)

    def test_snapshot_checksum_schema_extra_files_and_symlinks_are_rechecked(self):
        self.request_refresh()
        checkpoint.snapshot(self.root, self.destination, now=NOW)
        source = self.destination / checkpoint.ACQUISITION
        original = source.read_bytes()
        source.write_bytes(original + b' ')
        with self.assertRaises(ValueError): checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        source.write_bytes(original)
        stray = self.destination / 'data/body.pdf'; stray.write_bytes(b'PRIVATE')
        with self.assertRaises(ValueError): checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        stray.unlink(); stray.symlink_to(source)
        with self.assertRaises(ValueError): checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        self.assertFalse(self.worktree.exists())
        with self.assertRaises(FileExistsError): checkpoint.snapshot(self.root, self.destination, now=NOW)

    def test_failed_push_race_rebases_saved_commit_without_repeating_external_work(self):
        remote = Path(self.tmp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        self.git('remote', 'add', 'origin', str(remote)); self.git('push', 'origin', 'main')
        other = Path(self.tmp.name) / 'other'
        subprocess.run(['git', 'clone', '--branch', 'main', str(remote), str(other)], check=True, capture_output=True)
        self.git('config', 'user.name', 'Other', cwd=other); self.git('config', 'user.email', 'other@example.test', cwd=other)
        self.request_refresh(); self.save(checkpoint.LIBRARY, self.valid_failure_library())
        checkpoint.snapshot(self.root, self.destination, include_library=True, now=NOW)
        checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        (other / 'unrelated.txt').write_text('concurrent change')
        self.git('add', 'unrelated.txt', cwd=other); self.git('commit', '-m', 'Concurrent unrelated change', cwd=other)
        self.git('push', 'origin', 'main', cwd=other)
        with self.assertRaises(subprocess.CalledProcessError): self.git('push', 'origin', 'HEAD:main', cwd=self.worktree)
        with patch.object(queue.access, 'retrieve', side_effect=AssertionError('never retrieve')), \
             patch('comprehensive_readings.process', side_effect=AssertionError('never read')):
            self.git('fetch', 'origin', 'main', cwd=self.worktree)
            self.git('rebase', 'origin/main', cwd=self.worktree)
            checkpoint.verify_rebased(self.root, self.destination, self.worktree, now=NOW)
            self.git('push', 'origin', 'HEAD:main', cwd=self.worktree)
        self.assertEqual((self.worktree / 'unrelated.txt').read_text(), 'concurrent change')
        self.assertEqual(json.loads((self.worktree / checkpoint.ACQUISITION).read_text()), self.state)
        self.assertEqual(self.git('rev-parse', 'HEAD').strip(), self.base)
        self.assertEqual(self.git('status', '--porcelain', cwd=self.worktree), '')

    def test_clean_json_merge_cannot_attach_old_notes_to_corrected_identity(self):
        # Pretty JSON matches production: distant title and enrichment lines can
        # merge cleanly, unlike compact one-line fixtures that always conflict.
        remote = Path(self.tmp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        self.git('remote', 'add', 'origin', str(remote)); self.git('push', 'origin', 'main')
        other = Path(self.tmp.name) / 'other'
        subprocess.run(['git', 'clone', '--branch', 'main', str(remote), str(other)], check=True, capture_output=True)
        self.git('config', 'user.name', 'Other', cwd=other); self.git('config', 'user.email', 'other@example.test', cwd=other)
        from test_prepared_article_readings import reading, claim
        library = [deepcopy(self.record)]
        with patch.object(reading, 'read_chunk', side_effect=claim):
            reading.process(library, Mock(), retriever=lambda _: (deepcopy(self.doc), []), run_date=NOW.date())
        self.save(checkpoint.LIBRARY, library)
        checkpoint.snapshot(self.root, self.destination, include_library=True, now=NOW)
        checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        corrected = [deepcopy(self.record)]; corrected[0]['title'] = 'Corrected publication identity'
        (other / checkpoint.LIBRARY).write_text(json.dumps(corrected, indent=2) + '\n')
        self.git('add', checkpoint.LIBRARY, cwd=other); self.git('commit', '-m', 'Correct identity', cwd=other)
        self.git('push', 'origin', 'main', cwd=other)
        self.git('fetch', 'origin', 'main', cwd=self.worktree)
        self.git('rebase', 'origin/main', cwd=self.worktree)
        merged = json.loads((self.worktree / checkpoint.LIBRARY).read_text())
        self.assertEqual(merged[0]['title'], corrected[0]['title'])
        self.assertEqual(merged[0]['deep_analysis'], library[0]['deep_analysis'])
        with self.assertRaisesRegex(ValueError, 'rebased_reading_checkpoint_changed'):
            checkpoint.verify_rebased(self.root, self.destination, self.worktree, now=NOW)
        # The corrected remote stays free of the rejected old-source notes.
        self.assertEqual(json.loads(self.git('show', 'origin/main:' + checkpoint.LIBRARY)), corrected)
        self.assertEqual(json.loads((self.destination / checkpoint.LIBRARY).read_text()), library)

    def test_clean_rebase_cannot_combine_old_notes_with_new_pending_source_hold(self):
        remote = Path(self.tmp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        self.git('remote', 'add', 'origin', str(remote)); self.git('push', 'origin', 'main')
        other = Path(self.tmp.name) / 'other'
        subprocess.run(['git', 'clone', '--branch', 'main', str(remote), str(other)], check=True, capture_output=True)
        self.git('config', 'user.name', 'Other', cwd=other); self.git('config', 'user.email', 'other@example.test', cwd=other)
        from test_prepared_article_readings import reading, claim
        library = [deepcopy(self.record)]
        with patch.object(reading, 'read_chunk', side_effect=claim):
            reading.process(library, Mock(), retriever=lambda _: (deepcopy(self.doc), []), run_date=NOW.date())
        self.save(checkpoint.LIBRARY, library)
        checkpoint.snapshot(self.root, self.destination, include_library=True, now=NOW)
        checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        unchanged_receipt = deepcopy(self.state['records'][queue.record_key(self.record)]['document'])
        self.request_refresh()
        self.assertEqual(self.state['records'][queue.record_key(self.record)]['document'], unchanged_receipt)
        (other / checkpoint.ACQUISITION).write_text(json.dumps(self.state, indent=2) + '\n')
        self.git('add', checkpoint.ACQUISITION, cwd=other); self.git('commit', '-m', 'Observe changed source', cwd=other)
        self.git('push', 'origin', 'main', cwd=other)
        self.git('fetch', 'origin', 'main', cwd=self.worktree)
        self.git('rebase', 'origin/main', cwd=self.worktree)
        queue.validate_state(json.loads((self.worktree / checkpoint.ACQUISITION).read_text()))
        self.assertEqual(json.loads((self.worktree / checkpoint.LIBRARY).read_text()), library)
        with self.assertRaisesRegex(ValueError, 'rebased_reading_checkpoint_changed'):
            checkpoint.verify_rebased(self.root, self.destination, self.worktree, now=NOW)
        self.assertNotIn('deep_analysis', json.loads(self.git('show', 'origin/main:' + checkpoint.LIBRARY))[0])

    def test_conflicting_rebase_stops_with_snapshot_and_dirty_runner_preserved(self):
        remote = Path(self.tmp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        self.git('remote', 'add', 'origin', str(remote)); self.git('push', 'origin', 'main')
        other = Path(self.tmp.name) / 'other'
        subprocess.run(['git', 'clone', '--branch', 'main', str(remote), str(other)], check=True, capture_output=True)
        self.git('config', 'user.name', 'Other', cwd=other); self.git('config', 'user.email', 'other@example.test', cwd=other)
        self.request_refresh(); checkpoint.snapshot(self.root, self.destination, now=NOW)
        committed = checkpoint.commit(self.root, self.destination, self.worktree, now=NOW)
        changed = controls.merge_diagnostics_into_state(self.state, [{'stage': 'article',
            'status': 'article_http_403', 'url': self.record['url'], 'retryable': False}], now=NOW)
        (other / checkpoint.ACQUISITION).write_text(json.dumps(changed) + '\n')
        self.git('add', checkpoint.ACQUISITION, cwd=other); self.git('commit', '-m', 'Concurrent source denial', cwd=other)
        self.git('push', 'origin', 'main', cwd=other)
        self.git('fetch', 'origin', 'main', cwd=self.worktree)
        with self.assertRaises(subprocess.CalledProcessError): self.git('rebase', 'origin/main', cwd=self.worktree)
        self.git('rebase', '--abort', cwd=self.worktree)
        self.assertEqual(self.git('rev-parse', 'HEAD', cwd=self.worktree).strip(), committed['commit'])
        self.assertEqual(json.loads((self.destination / checkpoint.ACQUISITION).read_text()), self.state)
        self.assertEqual(json.loads((self.root / checkpoint.ACQUISITION).read_text()), self.state)
        self.assertEqual(self.git('rev-parse', 'HEAD').strip(), self.base)

    def test_cli_exposes_valid_recovery_even_when_library_validation_fails(self):
        self.request_refresh(); self.save(checkpoint.LIBRARY, [{'invalid': 'DO_NOT_SAVE'}])
        output = Path(self.tmp.name) / 'outputs'
        result = subprocess.run(['python', str(ROOT / 'scripts/reading_checkpoint.py'), 'snapshot',
            '--root', str(self.root), '--destination', str(self.destination), '--include-library'],
            env={**os.environ, 'GITHUB_OUTPUT': str(output)}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(output.read_text(), 'valid=true\n')
        self.assertTrue((self.destination / checkpoint.ACQUISITION).exists())
        self.assertFalse((self.destination / checkpoint.LIBRARY).exists())

    def test_workflow_reserves_save_time_and_keeps_prs_offline(self):
        text = (ROOT / '.github/workflows/deepen-readings.yml').read_text()
        self.assertIn('timeout-minutes: 95', text)
        reading = text.split('      - name: Read complete retrieved text')[1].split('      - name:')[0]
        self.assertIn('timeout-minutes: 50', reading)
        self.assertIn("if: github.event_name != 'pull_request'", reading)
        checkpoint_step = text.split('      - name: Preserve independently')[1].split('      - name:')[0]
        self.assertIn("if: always() && github.event_name != 'pull_request'", checkpoint_step)
        self.assertIn("steps.readings.outcome == 'failure'", checkpoint_step)
        self.assertIn("steps.readings.outcome == 'success' && steps.validation.outcome == 'success'", checkpoint_step)
        save = text.split('      - name: Save exact validated')[1].split('      - name:')[0]
        self.assertIn('reading_checkpoint.py commit', save)
        self.assertIn('cd "$save_tree"', save)
        self.assertIn('git rebase origin/main', save)
        self.assertLess(save.index('reading_checkpoint.py" verify'), save.index('git push origin HEAD:main'))
        self.assertIn('--root "$GITHUB_WORKSPACE"', save)
        self.assertNotIn('comprehensive_readings.py', save)
        self.assertNotIn('git add data', text)
        self.assertIn('queue: max', text); self.assertIn('cancel-in-progress: false', text)
        for action in ('checkout@v7.0.1', 'setup-python@v7.1.0', 'upload-artifact@v7.0.2'):
            self.assertIn('actions/' + action, text)
        self.assertEqual(text.count('secrets.'), 1)
        self.assertIn('contents: write', text)


if __name__ == '__main__':
    unittest.main()

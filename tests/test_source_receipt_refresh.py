"""Offline retained-state mismatch → acquisition → fresh review/closeout."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_prepared_article_readings import prepared, reading, packet, claim, FRIDAY, MONDAY
from test_weekly_source_acquisition import queue, access, document, result_for, arxiv_item, weekly, NOW
import acquisition_handoff as handoff
import source_access_controls as controls
import source_receipt_refresh as refresh


class SourceReceiptRefreshTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.packet = packet()
        self.record = self.packet['items'][0]
        self.doc = document(); self.doc.url = self.record['url']; self.doc.version = 'unspecified'; self.doc.source_bytes = b'%PDF-private-old-body'
        self.key = queue.record_key(self.record)
        self.state = self.acquire(doc=self.doc)
        self.old = deepcopy(self.state['records'][self.key])
        self.changed = deepcopy(self.doc)
        self.changed.units[0]['text'] += ' Changed article passage with new evidence.'
        self.changed.source_bytes = b'%PDF-private-new-body'

    def acquire(self, state=None, doc=None, now=FRIDAY, **kwargs):
        with patch.object(access, 'fetch_candidate', return_value=deepcopy(doc or self.changed)) as fetch:
            result = prepared.acquire(self.packet, state, now=now, known_sources_only=True,
                attempt=lambda record, plan, count, timeout: queue.perform_stage(record, plan, count),
                clock=lambda: 0, **kwargs)
        self.fetch = fetch
        return result

    def review(self, state, previous=None, doc=None, now=FRIDAY):
        with patch.object(access, 'fetch_candidate', return_value=deepcopy(doc or self.changed)), \
             patch.object(access, 'default_providers', return_value=[]), \
             patch.object(reading, 'read_chunk', side_effect=claim):
            return prepared.review(self.packet, state, previous, model=Mock(), now=now,
                                   data_dir=self.folder.name)

    def observe(self, state, doc=None, now=FRIDAY):
        with patch.object(access, 'fetch_candidate', return_value=deepcopy(doc or self.changed)), \
             patch.object(access, 'default_providers', return_value=[]):
            try:
                doc, _ = handoff.retrieve_for_reading(self.record, state=state, payload=self.packet, now=now,
                    shared_controls=controls.empty_controls(), diagnostic_observer=lambda diagnostics:
                        prepared.observe_retrieval(state, diagnostics, now))
                self.assertIsNone(doc)  # A saved pause can hold before the mismatch fetch.
            except ValueError as exc:
                self.assertIn(str(exc), handoff.HANDOFF_HOLDS)
        return state

    def close(self, state, bundle, doc, now=MONDAY):
        closing = packet(True); closing['items'] = deepcopy(self.packet['items'])
        self.packet = closing
        with patch.object(access, 'fetch_candidate', return_value=deepcopy(doc)), \
             patch.object(access, 'default_providers', return_value=[]):
            checked = prepared.revalidate(closing, state, bundle, now=now, data_dir=self.folder.name)
        canonical = {'run': {'publication_window': closing['target_publication_window']}, 'items': closing['items']}
        output, report = prepared.apply_closed(closing, state, checked, closing['items'], canonical, now=now)
        return checked, output, report

    def test_retained_receipt_mismatch_refresh_and_fresh_review_without_approval(self):
        stale = self.review(self.state)
        self.assertEqual(stale['review_run']['failure_reasons'], {'acquisition_receipt_content_changed': 1})
        event = self.state['records'][self.key]['source_refreshes'][0]
        self.assertEqual(event['status'], 'pending')
        self.assertEqual(event['receipt']['document'], self.old['document'])
        saves = []
        new = self.acquire(json.loads(json.dumps(self.state)), save=lambda value: saves.append(deepcopy(value)))
        self.assertEqual(self.fetch.call_count, 1)
        row = new['records'][self.key]
        self.assertEqual(row['document'], queue.document_metadata(self.changed))
        self.assertEqual(row['source_refreshes'][0]['receipt']['document_evidence'], self.old['document_evidence'])
        for field in ('cursor', 'tried_sources', 'fingerprint', 'plan', 'complete', 'status'):
            self.assertEqual(row[field], self.old[field])
        for saved in saves:
            queue.validate_state(saved)
        self.assertEqual(saves[0]['records'][self.key]['source_refreshes'][0]['reason'], 'interrupted_attempt')
        # New receipt invalidates the failed receipt's two-day reading cooldown.
        fresh = self.review(new, stale, now=FRIDAY + timedelta(hours=1))
        self.assertEqual(fresh['review_run']['summaries_completed'], 1)
        checked, output, report = self.close(new, fresh, self.changed)
        self.assertEqual(report['machine_checked_readings_applied'], 1)
        self.assertFalse(checked['approved'])
        self.assertFalse(output[0]['deep_analysis']['preparation_provenance']['independently_approved'])
        self.assertEqual(output[0]['deep_analysis']['source_hash'], self.changed.manifest()['source_sha256'])
        serialized = json.dumps(new)
        self.assertNotIn('PRIVATE_SOURCE_SENTINEL', serialized)
        self.assertNotIn('private-new-body', serialized)
        self.assertNotIn('Changed article passage', serialized)
        again = self.acquire(new, now=MONDAY)
        self.fetch.assert_not_called()
        self.assertEqual(again['records'], new['records'])

    def test_prior_review_and_closeout_are_invalidated_by_byte_only_change(self):
        old_bundle = self.review(self.state, doc=self.doc)
        old_closed, _, _ = self.close(self.state, old_bundle, self.doc)
        changed = deepcopy(self.doc); changed.source_bytes += b'changed-figure-only'
        self.observe(self.state, changed, now=MONDAY)
        new = self.acquire(self.state, doc=changed, now=MONDAY)
        reconciled = prepared.reconcile(self.packet, new, old_closed, now=MONDAY)
        entry = reconciled['records'][self.key]
        self.assertNotIn('deep_analysis', entry['record']); self.assertNotIn('revalidation', entry)
        _, _, report = self.close(new, old_closed, changed)
        self.assertEqual(report['machine_checked_readings_applied'], 0)
        fresh = self.review(new, old_closed, changed, now=MONDAY)
        self.assertEqual(fresh['review_run']['summaries_completed'], 1)
        _, _, report = self.close(new, fresh, changed)
        self.assertEqual(report['machine_checked_readings_applied'], 1)
        # Old v1 bundles without the optional receipt digest also invalidate bytes.
        legacy = deepcopy(old_closed); legacy['records'][self.key].pop('acquisition_receipt_sha256')
        prepared.sealed(legacy)
        self.assertNotIn('deep_analysis', prepared.reconcile(self.packet, new, legacy, now=MONDAY)['records'][self.key]['record'])

    def test_known_mismatch_invalidates_older_cached_closeout_before_refresh(self):
        reviewed = self.review(self.state, doc=self.doc)
        cached, _, _ = self.close(self.state, reviewed, self.doc)
        for version in ('unspecified', 'acceptedVersion'):
            state = deepcopy(self.state)
            changed = deepcopy(self.changed); changed.version = version
            self.observe(state, changed, now=MONDAY)
            canonical = {'run': {'publication_window': self.packet['target_publication_window']},
                         'items': self.packet['items']}
            _, report = prepared.apply_closed(self.packet, state, cached, self.packet['items'], canonical, now=MONDAY)
            self.assertEqual(report['machine_checked_readings_applied'], 0)
            self.assertNotIn('revalidation', prepared.reconcile(self.packet, state, cached, now=MONDAY)['records'][self.key])

    def test_closeout_observation_requests_recovery_after_previous_successful_reading(self):
        reviewed = self.review(self.state, doc=self.doc)
        held, _, report = self.close(self.state, reviewed, self.changed)
        self.assertEqual(report['machine_checked_readings_applied'], 0)
        self.assertEqual(held['records'][self.key]['revalidation']['status'], 'held')
        # Retain a held check's timestamp so repeated closeout remains fair.
        self.assertEqual(prepared.reconcile(self.packet, self.state, held, now=MONDAY)['records'][self.key]['revalidation'],
                         held['records'][self.key]['revalidation'])
        self.assertEqual(self.state['records'][self.key]['source_refreshes'][0]['status'], 'pending')
        new = self.acquire(self.state, now=MONDAY)
        fresh = self.review(new, held, now=MONDAY)
        _, _, report = self.close(new, fresh, self.changed)
        self.assertEqual(report['machine_checked_readings_applied'], 1)

    def test_paused_or_denied_source_does_not_consume_refresh_or_reset_controls(self):
        requested = self.observe(deepcopy(self.state))
        for restriction in ('denied_hosts', 'blocked_urls', 'host_pause', 'provider_pause', 'denied_providers'):
            state = deepcopy(requested)
            shared = controls.empty_controls()
            if restriction == 'denied_hosts': shared[restriction] = ['www.econstor.eu']
            elif restriction == 'blocked_urls': shared[restriction] = [self.record['url']]
            elif restriction == 'denied_providers': shared[restriction] = ['original_article']
            else:
                target = 'host:www.econstor.eu' if restriction == 'host_pause' else 'provider:CORE'
                shared['provider_pauses'][target] = (FRIDAY + timedelta(hours=3)).isoformat()
                if restriction == 'provider_pause':
                    # Verify that a route attributable to a paused locator remains paused.
                    with patch.object(access, 'registry_candidates', return_value=[
                            {'url': self.record['url'], 'provider': 'CORE'}]):
                        state = self.acquire(doc=self.doc)
                        self.observe(state)
                        new = self.acquire(state, shared_controls=shared)
                    self.fetch.assert_not_called()
                    self.assertEqual(new['records'][self.key]['source_refreshes'][0]['attempts'], [])
                    continue
            new = self.acquire(state, shared_controls=shared)
            self.fetch.assert_not_called()
            self.assertEqual(new['records'][self.key]['source_refreshes'][0]['attempts'], [])
            self.assertEqual(new['records'][self.key]['document'], self.old['document'])
            self.assertEqual(new['access_controls'], shared)
            if restriction == 'host_pause':
                later = self.acquire(new, now=FRIDAY + timedelta(hours=4))
                self.assertEqual(self.fetch.call_count, 1)
                self.assertEqual(later['provider_pauses'], shared['provider_pauses'])

    def test_retry_cooldown_is_retained_and_capped_per_receipt(self):
        requested = self.observe(self.state)
        failed = {'diagnostics': [{'stage': 'article', 'url': self.record['url'],
            'status': 'article_http_429', 'retryable': True, 'retry_after_seconds': 7200}]}
        calls = Mock(return_value=failed)
        def run(state, now):
            return prepared.acquire(self.packet, state, now=now, known_sources_only=True, attempt=calls, clock=lambda: 0)
        once = run(requested, FRIDAY)
        original_deadline = once['provider_pauses']['host:www.econstor.eu']
        for minute in (1, 30, 60):
            self.observe(once, now=FRIDAY + timedelta(minutes=minute))
            once = run(json.loads(json.dumps(once)), FRIDAY + timedelta(minutes=minute))
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(once['provider_pauses']['host:www.econstor.eu'], original_deadline)
        twice = run(once, FRIDAY + timedelta(hours=3))
        held = twice['records'][self.key]['source_refreshes'][0]
        self.assertEqual(len(held['attempts']), refresh.MAX_ATTEMPTS)
        self.assertEqual(held['status'], 'held')
        self.observe(twice, now=FRIDAY + timedelta(hours=6))
        run(twice, FRIDAY + timedelta(hours=7))
        self.assertEqual(calls.call_count, 2)
        self.assertEqual(twice['records'][self.key]['document'], self.old['document'])

    def test_failure_and_interruption_preserve_old_receipt_and_never_replay(self):
        for mode in ('denied', 'interrupted', 'moving_source', 'version_changed'):
            state = self.observe(deepcopy(self.state))
            saves = []
            if mode == 'denied':
                attempt = Mock(return_value={'diagnostics': [{'stage': 'article', 'url': self.record['url'],
                    'status': 'article_http_403', 'retryable': False}]})
            else:
                doc = deepcopy(self.changed)
                if mode == 'moving_source': doc.units[0]['text'] += ' Another change.'
                if mode == 'version_changed': doc.version = 'acceptedVersion'
                attempt = Mock(return_value=result_for(doc))
            result = prepared.acquire(self.packet, state, now=FRIDAY, known_sources_only=True,
                attempt=attempt, clock=lambda: 0, save=lambda value: saves.append(deepcopy(value)))
            if mode == 'interrupted': result = saves[0]
            row = result['records'][self.key]
            self.assertEqual(row['document'], self.old['document'])
            self.assertEqual(row['source_refreshes'][0]['status'], 'held')
            again = self.acquire(result, now=FRIDAY + timedelta(hours=6))
            self.fetch.assert_not_called()
            self.assertEqual(again['records'][self.key]['source_refreshes'], row['source_refreshes'])

    def test_version_mismatch_and_unknown_scholarly_version_never_refresh(self):
        changed = deepcopy(self.changed); changed.version = 'acceptedVersion'
        state = self.observe(deepcopy(self.state), changed)
        self.assertEqual(state['records'][self.key]['source_refreshes'][0]['reason'], 'source_version_unverified')
        self.acquire(state); self.fetch.assert_not_called()
        # An observed contrary version also revokes an existing pending request.
        state = self.observe(deepcopy(self.state))
        self.observe(state, changed)
        self.acquire(state); self.fetch.assert_not_called()
        # Same unknown scholarly version is not verified by an unchanged token.
        scholarly = deepcopy(self.packet); scholarly['items'][0]['kind'] = 'scholarly'
        old = deepcopy(self.doc); old.version = 'unspecified'
        changed = deepcopy(self.changed); changed.version = 'unspecified'
        with patch.object(self, 'packet', scholarly), patch.object(self, 'record', scholarly['items'][0]):
            state = self.acquire(doc=old)
            self.observe(state, changed)
            self.acquire(state, doc=changed); self.fetch.assert_not_called()

    def test_unknown_returned_version_cannot_normalize_into_an_accepted_refresh(self):
        state = self.observe(deepcopy(self.state))
        changed = deepcopy(self.changed); changed.version = 'unrecognized_remote_edition'
        new = self.acquire(state, doc=changed)
        self.assertEqual(new['records'][self.key]['document'], self.old['document'])
        self.assertEqual(new['records'][self.key]['source_refreshes'][0]['reason'], 'source_version_unverified')
        observed = self.observe(deepcopy(self.state), changed)
        self.assertEqual(observed['records'][self.key]['source_refreshes'][0]['reason'], 'source_version_unverified')

    def test_unknown_version_only_change_holds_even_when_normalized_hashes_match(self):
        reviewed = self.review(self.state, doc=self.doc)
        cached, _, _ = self.close(self.state, reviewed, self.doc)
        changed = deepcopy(self.doc); changed.version = 'unrecognized_remote_edition'
        self.observe(self.state, changed, now=MONDAY)
        hold = self.state['records'][self.key]['source_refresh_hold']
        self.assertEqual(hold['reason'], 'source_version_unverified')
        self.assertEqual(hold['observed_document'], self.old['document'])
        canonical = {'run': {'publication_window': self.packet['target_publication_window']},
                     'items': self.packet['items']}
        _, report = prepared.apply_closed(self.packet, self.state, cached, self.packet['items'], canonical, now=MONDAY)
        self.assertEqual(report['machine_checked_readings_applied'], 0)
        new = self.acquire(self.state, now=MONDAY)
        self.fetch.assert_not_called()
        self.assertEqual(new['records'][self.key]['source_refresh_hold'], hold)

    def test_receipt_request_cannot_reset_other_rows_or_bind_changed_inputs(self):
        source = deepcopy(self.packet)
        other = deepcopy(self.record); other.update(doi='10.5555/other', url='https://www.econstor.eu/other.pdf')
        source['items'].append(other)
        with patch.object(self, 'packet', source):
            state = self.acquire(doc=self.doc)
            other_key = queue.record_key(other); prior = deepcopy(state['records'][other_key])
            self.observe(state)
            new = self.acquire(state)
            self.assertEqual(new['records'][other_key], prior)
            self.assertEqual(new['records'][self.key]['fingerprint'], state['records'][self.key]['fingerprint'])
            changed_input = deepcopy(source); changed_input['items'][0]['title'] = 'A materially different article title'
            with patch.object(self, 'packet', changed_input):
                replacement = prepared.acquire(self.packet, state, now=FRIDAY, known_sources_only=True, limit=0)
            self.assertNotIn('source_refreshes', replacement['records'][self.key])
            self.assertEqual(replacement['dispositions'][-1]['record'], state['records'][self.key])

    def test_canonical_reader_persists_bound_request_without_a_preparation_wrapper(self):
        state_path = Path(self.folder.name) / 'acquisition.json'
        weekly_path = Path(self.folder.name) / 'weekly.json'
        queue.atomic_save(state_path, self.state)
        weekly_path.write_text(json.dumps(self.packet))
        with patch.object(access, 'fetch_candidate', return_value=deepcopy(self.changed)), \
             patch.object(access, 'default_providers', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'acquisition_receipt_content_changed'):
                handoff.retrieve_for_reading(self.record, state_path=state_path, weekly_path=weekly_path,
                    now=FRIDAY, shared_controls=controls.empty_controls())
        saved = json.loads(state_path.read_text()); queue.validate_state(saved)
        self.assertEqual(saved['records'][self.key]['source_refreshes'][0]['status'], 'pending')
        self.assertEqual(saved['records'][self.key]['document'], self.old['document'])

    def html(self, suffix=''):
        text = 'Synthetic article about attention with evidence and qualifications. ' * 5
        html = '<title>' + self.record['title'] + '</title><main><article>' + ''.join(
            '<p>' + text + suffix + '</p>' for _ in range(10)) + '</article></main>'
        return access.document_from_html(html.encode(), self.record, self.record['url'])

    def test_current_parser_html_refreshes_but_stays_partial_and_unapproved(self):
        old = self.html(); changed = self.html('Additional observation.')
        state = self.acquire(doc=old)
        reviewed = self.review(state, doc=old)
        self.observe(state, changed)
        new = self.acquire(state, doc=changed)
        self.assertEqual(new['records'][self.key]['document']['html_extraction_version'], queue.HTML_EXTRACTION_VERSION)
        fresh = self.review(new, reviewed, changed)
        self.assertEqual(fresh['review_run']['summaries_completed'], 1)
        self.assertEqual(fresh['review_run']['partial_inputs'], 1)
        checked, _, report = self.close(new, fresh, changed)
        self.assertEqual(checked['revalidation_run']['attempted'], 0)
        self.assertEqual(report['machine_checked_readings_applied'], 0)
        self.assertNotIn('Synthetic article', json.dumps(new))

    def test_content_refresh_preserves_prior_parser_migration_history(self):
        old = self.html(); current = self.html('Parser revision.')
        state = self.acquire(doc=old)
        state['records'][self.key]['document'].pop('html_extraction_version')
        queue.seal_state(state)
        migrated = self.acquire(state, doc=current)
        self.assertIn('html_refresh', migrated['records'][self.key])
        parser_history = deepcopy(migrated['records'][self.key]['previous_documents'])
        changed = self.html('Changed source on the current parser.')
        self.observe(migrated, changed, now=FRIDAY + timedelta(minutes=1))
        new = self.acquire(migrated, doc=changed, now=FRIDAY + timedelta(minutes=2))
        queue.validate_state(new)
        self.assertEqual(new['records'][self.key]['previous_documents'], parser_history)
        self.assertEqual(new['records'][self.key]['source_refreshes'][0]['status'], 'refreshed')

    def test_refresh_history_cap_and_repeated_observations_do_not_restart_receipts(self):
        state = deepcopy(self.state)
        for number in range(refresh.MAX_REQUESTS):
            changed = deepcopy(self.changed); changed.units[0]['text'] += str(number)
            self.observe(state, changed, now=FRIDAY + timedelta(minutes=number))
            before = deepcopy(state['records'][self.key]['source_refreshes'])
            self.observe(state, changed, now=FRIDAY + timedelta(minutes=number, seconds=1))
            self.assertEqual(state['records'][self.key]['source_refreshes'], before)
            state = self.acquire(state, doc=changed, now=FRIDAY + timedelta(minutes=number, seconds=2))
        original = deepcopy(state['records'][self.key])
        self.observe(state, self.changed, now=FRIDAY + timedelta(hours=1))
        state = self.acquire(state, now=FRIDAY + timedelta(hours=2))
        self.fetch.assert_not_called()
        self.assertEqual(len(state['records'][self.key]['source_refreshes']), refresh.MAX_REQUESTS)
        held = deepcopy(state['records'][self.key]); held.pop('source_refresh_hold')
        self.assertEqual(held, original)
        self.assertEqual(state['records'][self.key]['source_refresh_hold']['reason'], 'receipt_refresh_limit')

    def test_exhausted_or_cyclic_history_still_invalidates_cached_closeout(self):
        for mode in ('cap', 'cycle'):
            state = deepcopy(self.state)
            self.packet = packet()
            count = refresh.MAX_REQUESTS if mode == 'cap' else 2
            for number in range(count):
                changed = deepcopy(self.changed); changed.units[0]['text'] += str(number)
                if mode == 'cycle' and number == 1:
                    changed = deepcopy(self.doc)
                self.observe(state, changed, now=FRIDAY + timedelta(minutes=number))
                state = self.acquire(state, doc=changed, now=FRIDAY + timedelta(minutes=number, seconds=1))
            reviewed = self.review(state, doc=changed, now=FRIDAY + timedelta(hours=1))
            cached, _, report = self.close(state, reviewed, changed)
            self.assertEqual(report['machine_checked_readings_applied'], 1)
            self.observe(state, self.changed, now=MONDAY)
            self.assertIn('source_refresh_hold', state['records'][self.key])
            canonical = {'run': {'publication_window': self.packet['target_publication_window']},
                         'items': self.packet['items']}
            _, report = prepared.apply_closed(self.packet, state, cached, self.packet['items'], canonical, now=MONDAY)
            self.assertEqual(report['machine_checked_readings_applied'], 0)
            again = self.acquire(state, now=MONDAY)
            self.fetch.assert_not_called()
            self.assertEqual(len(again['records'][self.key]['source_refreshes']), count)
            self.assertEqual(again['records'][self.key]['source_refresh_hold'], state['records'][self.key]['source_refresh_hold'])

    def test_normal_robots_and_rights_failures_hold_refresh_without_source_replacement(self):
        for reason in ('robots_disallow_or_unavailable', 'structured_reuse_license_unverified'):
            state = self.observe(deepcopy(self.state))
            with patch.object(access, 'fetch_candidate', side_effect=ValueError(reason)) as fetch:
                new = prepared.acquire(self.packet, state, now=FRIDAY, known_sources_only=True,
                    attempt=lambda r, p, n, t: queue.perform_stage(r, p, n), clock=lambda: 0)
            fetch.assert_called_once()
            row = new['records'][self.key]
            self.assertEqual(row['document'], self.old['document'])
            self.assertEqual(row['source_refreshes'][0]['reason'], reason)
            self.acquire(new, now=FRIDAY + timedelta(hours=1)); self.fetch.assert_not_called()

    def test_stale_or_wrong_input_observation_cannot_request_another_refresh(self):
        note = handoff.receipt_change_note(self.record, self.old, self.changed, queue)
        for field in ('input_fingerprint', 'receipt_sha256'):
            wrong = deepcopy(note); wrong['receipt_observation'][field] = '0' * 64
            updated = controls.merge_diagnostics_into_state(self.state, [wrong], now=FRIDAY)
            self.assertEqual(updated['records'], self.state['records'])
        requested = controls.merge_diagnostics_into_state(self.state, [note], now=FRIDAY)
        new = self.acquire(requested)
        updated = controls.merge_diagnostics_into_state(new, [note], now=FRIDAY + timedelta(hours=1))
        self.assertEqual(updated['records'], new['records'])
        self.acquire(updated, now=FRIDAY + timedelta(hours=2)); self.fetch.assert_not_called()

    def test_schema_rejects_unbound_history_prose_and_approval(self):
        requested = self.observe(self.state)
        mutations = [lambda e: e.update(source_body='PRIVATE'), lambda e: e.update(approved=True),
            lambda e: e['receipt']['document'].update(source_sha256='0' * 64),
            lambda e: e.update(status='refreshed', replacement_sha256='0' * 64),
            lambda e: e['observed_document'].update(source_url='https://www.econstor.eu/other.pdf'),
            lambda e: e['attempts'].extend([{'attempted_at': FRIDAY.isoformat(), 'outcome': 'TimeoutError'}] * 3)]
        for mutate in mutations:
            bad = deepcopy(requested); mutate(bad['records'][self.key]['source_refreshes'][0])
            with self.assertRaises(ValueError): queue.seal_state(bad)

    def test_arxiv_v1_cannot_be_relabelled_from_a_contrary_returned_version(self):
        record = arxiv_item(); source = weekly(record)
        doc = document(); doc.url = 'https://arxiv.org/pdf/2610.12345v1'; doc.version = 'arxiv_preprint_v1'
        with patch.object(access, 'fetch_candidate', return_value=deepcopy(doc)):
            state = queue.run(source, now=NOW, known_sources_only=True,
                attempt=lambda r, p, n, t: queue.perform_stage(r, p, n), clock=lambda: 0)
        changed = deepcopy(doc); changed.units[0]['text'] += ' New source passage.'
        with self.assertRaises(ValueError):
            handoff.retrieve_for_reading(record, state=state, payload=source, now=NOW,
                shared_controls=controls.empty_controls(), retriever=Mock(return_value=(changed, [])),
                diagnostic_observer=lambda d: prepared.observe_retrieval(state, d, NOW))
        contrary = deepcopy(changed); contrary.version = 'arxiv_preprint_v2'
        with patch.object(access, 'fetch_candidate', return_value=contrary):
            new = queue.run(source, state, now=NOW, known_sources_only=True,
                attempt=lambda r, p, n, t: queue.perform_stage(r, p, n), clock=lambda: 0)
        row = new['records'][queue.record_key(record)]
        self.assertEqual(row['document'], queue.document_metadata(doc))
        self.assertEqual(row['source_refreshes'][0]['reason'], 'source_version_unverified')


if __name__ == '__main__':
    unittest.main()

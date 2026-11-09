"""Metadata-only source handoff re-fetches through normal guarded retrieval."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from test_weekly_source_acquisition import queue, access, item, arxiv_item, weekly, rows, NOW, document, result_for
import acquisition_handoff as handoff


class AcquisitionHandoffTests(unittest.TestCase):
    def test_observer_persists_restrictions_before_a_receipt_hold_raises(self):
        ledger = [{"stage": "article", "status": "article_http_403", "url": "https://www.econstor.eu/denied.pdf", "retryable": False},
                  handoff.note("acquisition_receipt_content_changed")]
        observed = []
        with patch.object(handoff, "_retrieve_for_reading", return_value=(None, ledger)):
            with self.assertRaisesRegex(ValueError, "acquisition_receipt_content_changed"):
                handoff.retrieve_for_reading({}, diagnostic_observer=lambda entries: observed.extend(entries))
        self.assertEqual(observed, ledger)

    def setUp(self):
        self.record = item()
        self.payload = weekly(self.record)
        self.doc = document()
        self.doc.url = 'https://www.econstor.eu/recovered-author-copy.pdf'
        self.doc.source_bytes = b'%PDF-synthetic-private-source-bytes'
        self.state = queue.run(self.payload, now=NOW, known_sources_only=True,
                               attempt=lambda *args: result_for(self.doc), clock=lambda: 0)

    def retrieve(self, *, record=None, state=None, payload=None, doc=None, retriever=None, now=NOW):
        callback = retriever or Mock(return_value=(copy.deepcopy(doc or self.doc), []))
        result = handoff._retrieve_for_reading(record or self.record,
            state=self.state if state is None else state,
            payload=self.payload if payload is None else payload, now=now, retriever=callback,
            shared_controls=handoff.controls.empty_controls())
        return result, callback

    def test_validated_receipt_prioritizes_exact_source_and_rechecks_hashes(self):
        original = copy.deepcopy(self.state)
        (doc, ledger), callback = self.retrieve()
        self.assertIsNotNone(doc)
        args = callback.call_args
        hint = args.kwargs['known_sources'][0]
        self.assertEqual(hint['url'], self.doc.url)
        self.assertEqual(hint['version'], 'publishedVersion')
        self.assertEqual(hint['provider'], handoff.PROVIDER)
        self.assertEqual(doc.coverage['acquisition_state_sha256'], self.state['state_sha256'])
        self.assertEqual(doc.coverage['acquisition_receipt_status'], 'revalidated_not_reviewed')
        self.assertEqual(ledger[-1]['status'], 'acquisition_receipt_revalidated')
        self.assertEqual(self.state, original)
        self.assertNotIn('PRIVATE_SOURCE_SENTINEL', json.dumps(doc.manifest()))
        self.assertNotIn('synthetic-private-source-bytes', json.dumps(doc.manifest()))
        self.assertIsNone(hint['license'], 'A receipt is not a redistribution license')
        self.assertFalse(hint['redistribution_granted'])

    def test_missing_checkpoint_keeps_ordinary_retrieval(self):
        with tempfile.TemporaryDirectory() as folder:
            callback = Mock(return_value=(None, []))
            handoff.retrieve_for_reading(self.record, state_path=Path(folder)/'missing.json',
                                         weekly_path=Path(folder)/'weekly.json', retriever=callback)
        callback.assert_called_once_with(self.record)

    def test_bad_checkpoint_checksum_or_unknown_prose_holds_before_fetch(self):
        for mutation in ('checksum', 'prose'):
            state = copy.deepcopy(self.state)
            if mutation == 'checksum': state['state_sha256'] = '0' * 64
            else:
                state['raw_source'] = 'PRIVATE_SOURCE_SENTINEL'
                state['state_sha256'] = queue.digest({k:v for k,v in state.items() if k != 'state_sha256'})
            callback = Mock()
            (doc, ledger), _ = self.retrieve(state=state, retriever=callback)
            callback.assert_not_called()
            self.assertIsNone(doc)
            self.assertEqual(ledger[-1]['status'], 'acquisition_metadata_invalid')

    def test_corrupt_existing_checkpoint_is_held_even_if_weekly_snapshot_is_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'state.json'
            bad = copy.deepcopy(self.state); bad['state_sha256'] = '0' * 64
            path.write_text(json.dumps(bad))
            callback = Mock()
            doc, ledger = handoff._retrieve_for_reading(self.record, state_path=path,
                weekly_path=Path(folder)/'missing.json', retriever=callback)
        callback.assert_not_called()
        self.assertIsNone(doc)
        self.assertEqual(ledger[-1]['status'], 'acquisition_metadata_invalid')

    def test_global_provider_and_host_pauses_survive_an_unmatched_receipt(self):
        state = copy.deepcopy(self.state)
        state['provider_pauses'] = {'host:www.econstor.eu': (NOW + timedelta(hours=1)).isoformat(),
                                   'provider:OpenAIRE': (NOW + timedelta(hours=2)).isoformat()}
        state.pop('run'); queue.seal_state(state)
        changed = {**self.record, 'title':'A changed exact title requiring a new receipt'}
        callback = Mock(return_value=(None, []))
        self.retrieve(record=changed, state=state, retriever=callback)
        self.assertEqual(callback.call_args.kwargs['host_backoff'], {'www.econstor.eu':3600})
        self.assertNotIn('OpenAIRE', [name for name, _ in callback.call_args.kwargs['providers']])
        self.assertNotIn('known_sources', callback.call_args.kwargs)
        with tempfile.TemporaryDirectory() as folder:
            callback.reset_mock()
            handoff.retrieve_for_reading(changed, state=state, weekly_path=Path(folder)/'missing.json',
                                         now=NOW, retriever=callback)
        self.assertEqual(callback.call_args.kwargs['host_backoff'], {'www.econstor.eu':3600})
        self.assertNotIn('OpenAIRE', [name for name, _ in callback.call_args.kwargs['providers']])

    def test_changed_current_identity_does_not_inherit_receipt(self):
        for change in ({'title': 'Different article title about attention'},
                       {'url': 'https://www.econstor.eu/different.pdf'},
                       {'published': '2026-10-29'}, {'doi': '10.5555/other'},
                       {'publication_date_provenance': {}}):
            record = {**self.record, **change}
            callback = Mock(return_value=(None, []))
            self.retrieve(record=record, retriever=callback)
            callback.assert_called_once_with(record)

    def test_operational_recheck_time_drift_does_not_discard_matching_commentary(self):
        record = item(doi='', kind='nonacademic', publication_date_provenance={
            'basis':'publisher_datePublished', 'date':'2026-10-28',
            'source_url':self.record['url'], 'checked_at':'2026-11-08T09:34:27+00:00'})
        payload = weekly(record)
        state = queue.run(payload, now=NOW, known_sources_only=True,
                          attempt=lambda *args:result_for(self.doc), clock=lambda:0)
        current = copy.deepcopy(record)
        current['publication_date_provenance']['checked_at'] = '2026-11-07T22:15:47+00:00'
        (doc, ledger), _ = self.retrieve(record=current, state=state, payload=payload)
        self.assertIsNotNone(doc)
        self.assertEqual(ledger[-1]['status'], 'acquisition_receipt_revalidated')
        for field, value in (('date','2026-10-29'), ('basis','publisher_atom_published'),
                             ('source_url','https://www.econstor.eu/other')):
            changed = copy.deepcopy(current); changed['publication_date_provenance'][field] = value
            callback = Mock(return_value=(None, []))
            self.retrieve(record=changed, state=state, payload=payload, retriever=callback)
            callback.assert_called_once_with(changed)
        # The checkpoint still binds the exact weekly observation, timestamp included.
        changed_payload = copy.deepcopy(payload)
        changed_payload['items'][0]['publication_date_provenance']['checked_at'] = '2026-11-09T00:00:00+00:00'
        callback = Mock(return_value=(None, []))
        self.retrieve(record=current, state=state, payload=changed_payload, retriever=callback)
        callback.assert_called_once_with(current)

    def test_changed_weekly_route_fingerprint_does_not_inherit_receipt(self):
        payload = copy.deepcopy(self.payload)
        payload['items'][0]['fulltext_candidates'] = [{'url': 'https://www.econstor.eu/new.pdf'}]
        callback = Mock(return_value=(None, []))
        self.retrieve(payload=payload, retriever=callback)
        callback.assert_called_once_with(self.record)

    def test_different_week_or_missing_record_does_not_inherit_receipt(self):
        for change in ({'items': []}, {'run': {'publication_window': {
                'from': '2026-11-02', 'to': '2026-11-08', 'timezone': 'UTC'}}}):
            payload = {**self.payload, **change}
            callback = Mock(return_value=(None, []))
            self.retrieve(payload=payload, retriever=callback)
            callback.assert_called_once_with(self.record)

    def test_source_text_bytes_version_and_parser_changes_are_held(self):
        for key in ('text', 'bytes', 'version', 'coverage'):
            doc = copy.deepcopy(self.doc)
            if key == 'text': doc.units[0]['text'] += ' New source edition.'
            elif key == 'bytes': doc.source_bytes += b'changed-figure'
            elif key == 'version': doc.version = 'acceptedVersion'
            else: doc.coverage['evidence_status'] = 'partial_full_text'
            (retrieved, ledger), _ = self.retrieve(doc=doc)
            self.assertIsNone(retrieved)
            self.assertEqual(ledger[-1]['status'], 'acquisition_source_version_changed' if key == 'version'
                             else 'acquisition_receipt_content_changed')

    def test_partial_html_is_revalidated_but_never_promoted_to_complete(self):
        doc = access.Document([{'location': 'paragraph:1', 'text': 'Full article paragraph. '*200}],
            self.doc.url, 'unspecified', {'evidence_status':'partial_full_text',
                'html_completeness':'not_verified','html_extraction_version':queue.HTML_EXTRACTION_VERSION})
        state = queue.run(self.payload, now=NOW, known_sources_only=True,
                          attempt=lambda *args: result_for(doc), clock=lambda:0)
        (fresh, _), _ = self.retrieve(state=state, doc=doc)
        self.assertEqual(fresh.coverage['evidence_status'], 'partial_full_text')
        self.assertEqual(rows(state)[0]['document']['semantic_completeness'], 'not_verified')
        changed = copy.deepcopy(doc); changed.coverage['html_extraction_version'] = 'article-body-v999'
        (fresh, ledger), _ = self.retrieve(state=state, doc=changed)
        self.assertIsNone(fresh)
        self.assertEqual(ledger[-1]['status'], 'acquisition_receipt_content_changed')

    def test_independent_alternative_keeps_its_own_version_without_old_receipt(self):
        alternate = copy.deepcopy(self.doc)
        alternate.url = 'https://zenodo.org/records/1/files/accepted.pdf'
        alternate.version = 'acceptedVersion'
        alternate.coverage['retrieval_provider'] = 'OpenAIRE'
        (doc, ledger), _ = self.retrieve(doc=alternate)
        self.assertEqual(doc.version, 'acceptedVersion')
        self.assertNotIn('acquisition_state_sha256', doc.coverage)
        self.assertEqual(ledger[-1]['status'], 'independent_source_after_acquisition_hint')

    def test_changed_redirect_from_receipt_hint_is_not_relabelled_original_version(self):
        changed = copy.deepcopy(self.doc)
        changed.url = 'https://www.econstor.eu/new-version.pdf'
        changed.coverage['retrieval_provider'] = handoff.PROVIDER
        (doc, ledger), _ = self.retrieve(doc=changed)
        self.assertIsNone(doc)
        self.assertEqual(ledger[-1]['status'], 'acquisition_receipt_route_changed')

    def test_saved_denial_is_not_replayed_through_handoff(self):
        state = copy.deepcopy(self.state)
        rows(state)[0]['diagnostics'].append({'stage':'article','status':'article_http_403',
            'retryable':False,'url':self.doc.url})
        state.pop('run'); queue.seal_state(state)
        callback = Mock()
        (doc, ledger), _ = self.retrieve(state=state, retriever=callback)
        callback.assert_not_called()
        self.assertIsNone(doc)
        self.assertEqual(ledger[-1]['status'], 'acquisition_source_access_blocked')

    def test_host_and_provider_pauses_reach_existing_guarded_reader(self):
        state = copy.deepcopy(self.state)
        state['provider_pauses'] = {'host:www.econstor.eu': (NOW + timedelta(hours=1)).isoformat(),
                                   'provider:OpenAIRE': (NOW + timedelta(hours=2)).isoformat()}
        state.pop('run'); queue.seal_state(state)
        (_, _), callback = self.retrieve(state=state)
        self.assertEqual(callback.call_args.kwargs['host_backoff'], {'www.econstor.eu': 3600})
        names = [name for name, _ in callback.call_args.kwargs['providers']]
        self.assertNotIn('OpenAIRE', names)
        self.assertIn('Crossref publisher locations', names)

    def test_first_version_is_pinned_and_latest_alias_cannot_replace_it(self):
        record = arxiv_item()
        payload = weekly(record)
        doc = copy.deepcopy(self.doc)
        doc.url = 'https://arxiv.org/pdf/2610.12345v1'; doc.version = 'arxiv_preprint_v1'
        state = queue.run(payload, now=NOW, known_sources_only=True,
                          attempt=lambda *args: result_for(doc), clock=lambda:0)
        (fresh, _), callback = self.retrieve(record=record, state=state, payload=payload, doc=doc)
        self.assertIsNotNone(fresh)
        self.assertEqual(callback.call_args.kwargs['providers'], [])
        self.assertTrue(all('2610.12345v1' in r['url'] for r in callback.call_args.kwargs['known_sources']))
        latest = copy.deepcopy(doc); latest.url = 'https://arxiv.org/pdf/2610.12345'
        (fresh, ledger), _ = self.retrieve(record=record, state=state, payload=payload, doc=latest)
        self.assertIsNone(fresh)
        self.assertEqual(ledger[-1]['status'], 'acquisition_source_version_changed')

    def test_verified_first_version_stays_pinned_without_a_receipt(self):
        record = arxiv_item()
        callback = Mock(return_value=(None, []))
        with tempfile.TemporaryDirectory() as folder:
            handoff.retrieve_for_reading(record, state_path=Path(folder)/'missing.json', retriever=callback)
        self.assertEqual(callback.call_args.kwargs['providers'], [])
        sources = callback.call_args.kwargs['known_sources']
        self.assertTrue(all(queue.is_pinned_arxiv_url(row['url'], '2610.12345v1') for row in sources))
        self.assertTrue(all(row['version'] == 'arxiv_preprint_v1' for row in sources))
        record['publication_date_provenance']['requested_id'] = '2610.12345v2'
        callback.reset_mock()
        with tempfile.TemporaryDirectory() as folder:
            result = handoff._retrieve_for_reading(record, state_path=Path(folder)/'missing.json', retriever=callback)
        callback.assert_not_called()
        self.assertEqual(result[1][-1]['status'], 'acquisition_source_version_unverified')

    def test_duplicate_input_fingerprints_match_without_losing_extra_routes(self):
        second = {**self.record, 'fulltext_candidates':[{'url':'https://www.econstor.eu/another.pdf'}]}
        payload = weekly(self.record, second)
        state = queue.run(payload, now=NOW, known_sources_only=True,
                          attempt=lambda *args: result_for(self.doc), clock=lambda:0)
        (doc, ledger), _ = self.retrieve(state=state, payload=payload)
        self.assertIsNotNone(doc)
        self.assertEqual(ledger[-1]['status'], 'acquisition_receipt_revalidated')
        payload['items'].reverse()
        (doc, ledger), _ = self.retrieve(state=state, payload=payload)
        self.assertIsNotNone(doc)
        self.assertEqual(ledger[-1]['status'], 'acquisition_receipt_revalidated')

    def test_xml_license_is_checked_again_and_cannot_be_inherited_from_receipt(self):
        import structured_article_access as xml
        from test_structured_article_access import jats
        url = 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC123/fullTextXML'
        record = item(fulltext_candidates=[{'url':url, 'structured_format':'jats',
                                          'version':'repository_article_xml'}])
        payload = weekly(record)
        original = jats(doi=record['doi'], title=record['title'])
        doc = xml.document_from_xml(original, record, url, format='jats', version='repository_article_xml')
        state = queue.run(payload, now=NOW, known_sources_only=True,
                          attempt=lambda *args: result_for(doc), clock=lambda:0)
        with patch.object(access, 'request', return_value=(original, url, 'application/xml')),              patch.object(access, 'default_providers', return_value=[]):
            (fresh, ledger), _ = self.retrieve(record=record, state=state, payload=payload, retriever=access.retrieve)
        self.assertIsNotNone(fresh)
        self.assertEqual(ledger[-1]['status'], 'acquisition_receipt_revalidated')
        restricted = jats(license=False, doi=record['doi'], title=record['title'])
        with patch.object(access, 'request', return_value=(restricted, url, 'application/xml')),              patch.object(access, 'robots_allowed', return_value=False),              patch.object(access, 'default_providers', return_value=[]):
            (fresh, ledger), _ = self.retrieve(record=record, state=state, payload=payload, retriever=access.retrieve)
        self.assertIsNone(fresh)
        self.assertIn('structured_reuse_license_unverified', [row['status'] for row in ledger])

    def test_reader_callback_preserves_machine_review_and_publication_quarantine(self):
        import comprehensive_readings as reading
        import build_public
        record = {**self.record, 'reading': {'level':'citation_only'}}
        def callback(value):
            return handoff.retrieve_for_reading(value, state=self.state, payload=self.payload, now=NOW,
                retriever=lambda *args, **kwargs: (copy.deepcopy(self.doc), []))
        def synthesize(doc, *args, **kwargs):
            return {'coverage':doc.manifest()}
        with patch.object(reading, 'screen_source', return_value={'decision':'include'}),              patch.object(reading, 'synthesize', side_effect=synthesize):
            stats = reading.process([record], Mock(), retriever=callback)
        self.assertEqual(stats['summaries_completed'], 1)
        self.assertEqual(record['deep_analysis']['review_status'], 'machine_checked_not_independently_reviewed')
        self.assertEqual(record['deep_analysis']['coverage']['acquisition_receipt_status'], 'revalidated_not_reviewed')
        self.assertNotIn('source_review', record)
        self.assertNotIn('original_reading', record)
        self.assertFalse(build_public.readable(record))
        self.assertNotIn('PRIVATE_SOURCE_SENTINEL', json.dumps(record))

    def test_explicit_receipt_hold_never_summarizes_old_indexed_sections(self):
        import comprehensive_readings as reading
        record = {**self.record, 'analysis': {'fulltext_url': self.doc.url,
                  'results':'Previously retained source section that must not bypass a changed receipt.'}}
        changed = copy.deepcopy(self.doc); changed.units[0]['text'] += ' Changed source.'
        def callback(value):
            return handoff.retrieve_for_reading(value, state=self.state, payload=self.payload, now=NOW,
                retriever=lambda *args, **kwargs:(changed, []))
        with patch.object(reading, 'screen_source', return_value={'decision':'include'}),              patch.object(reading, 'synthesize') as synthesis,              patch.object(reading, 'indexed_sections') as indexed:
            stats = reading.process([record], Mock(), retriever=callback)
        synthesis.assert_not_called(); indexed.assert_not_called()
        self.assertEqual(stats['failure_stages'], {'retrieval':1})
        self.assertEqual(record['complete_reading_attempt']['status'], 'acquisition_receipt_content_changed')
        self.assertNotIn('deep_analysis', record)
        self.assertIn('results', record['analysis'])

    def test_metadata_mismatch_does_not_erase_saved_denial_controls(self):
        state = copy.deepcopy(self.state)
        rows(state)[0]['diagnostics'].extend([
            {'stage':'article','status':'article_http_403','retryable':False,'url':self.doc.url},
            {'stage':'discovery','status':'http_403','retryable':False,'provider':'OpenAIRE',
             'failure_url':'https://api.openaire.eu/search/publications'},
        ])
        state.pop('run'); queue.seal_state(state)
        changed = {**self.record, 'title':'A changed title with the same denied source'}
        def guarded(*args, **options):
            self.assertIn('www.econstor.eu', access.HOST_DENIALS.get())
            self.assertIn(self.doc.url, access.SOURCE_DENIALS.get())
            self.assertNotIn('OpenAIRE', [name for name, _ in options['providers']])
            return None, []
        self.retrieve(record=changed, state=state, retriever=guarded)
        unrelated = item(99)
        self.retrieve(record=unrelated, state=state, retriever=guarded)
        self.assertIsNone(access.HOST_DENIALS.get())
        self.assertIsNone(access.SOURCE_DENIALS.get())

    def test_real_reader_still_checks_robots_and_article_identity(self):
        with patch.object(access, 'robots_allowed', return_value=False) as robots, \
             patch.object(access, 'request') as request, \
             patch.object(access, 'default_providers', return_value=[]):
            (doc, ledger), _ = self.retrieve(retriever=access.retrieve)
        self.assertIsNone(doc)
        self.assertEqual(robots.call_args_list[0].args[0], self.doc.url)
        request.assert_not_called()
        self.assertTrue(any(d['status']=='robots_disallow_or_unavailable' for d in ledger))
        with patch.object(access, 'robots_allowed', return_value=True), \
             patch.object(access, 'request', return_value=(b'<html>Wrong article</html>', self.doc.url, 'text/html')), \
             patch.object(access, 'default_providers', return_value=[]):
            (doc, ledger), _ = self.retrieve(retriever=access.retrieve)
        self.assertIsNone(doc)
        self.assertTrue(any(d['status']=='document_identity_unverified' for d in ledger))

    def test_saved_exact_route_denial_applies_to_nested_pdfs_and_redirects(self):
        blocked = 'https://www.econstor.eu/previously-robots-denied.pdf'
        state = copy.deepcopy(self.state)
        rows(state)[0]['diagnostics'].append({'stage':'article','status':'robots_disallow_or_unavailable',
            'retryable':False,'url':blocked})
        state.pop('run'); queue.seal_state(state)
        page = (f'<html><head><meta name="citation_title" content="{self.record["title"]}">'
                f'<meta name="citation_doi" content="{self.record["doi"]}">'
                f'<meta name="citation_pdf_url" content="{blocked}"></head><body>Article</body></html>').encode()
        calls = []
        def request(url, *args, **kwargs):
            calls.append(url)
            access.check_host_cooldown(url)
            return page, url, 'text/html'
        with patch.object(access, 'robots_allowed', return_value=True),              patch.object(access, 'request', side_effect=request),              patch.object(access, 'default_providers', return_value=[]):
            (doc, ledger), _ = self.retrieve(state=state, retriever=access.retrieve)
        self.assertNotIn(blocked, calls)
        self.assertIsNone(doc)
        self.assertIn('source_access_denied_this_run', [d['status'] for d in ledger])
        self.assertIsNone(access.SOURCE_DENIALS.get())
        from urllib.request import Request
        def redirect_probe(*args, **kwargs):
            with self.assertRaisesRegex(ValueError, 'source_access_denied_this_run'):
                access.Guard(access.ARTICLE_HOSTS).redirect_request(
                    Request(self.doc.url), None, 302, 'Found', {}, blocked)
            return None, []
        self.retrieve(state=state, retriever=redirect_probe)
        self.assertIsNone(access.SOURCE_DENIALS.get())

    def test_new_403_stops_same_host_without_replaying_other_source_paths(self):
        with patch.object(access, 'robots_allowed', return_value=True), \
             patch.object(access, 'request', side_effect=HTTPError(self.doc.url, 403, 'Denied', {}, None)) as request, \
             patch.object(access, 'default_providers', return_value=[]):
            (doc, ledger), _ = self.retrieve(retriever=access.retrieve)
        self.assertIsNone(doc)
        self.assertEqual(request.call_count, 1)
        self.assertIn('host_access_denied_this_run', [d['status'] for d in ledger])
        self.assertIsNone(access.HOST_DENIALS.get())


if __name__ == '__main__':
    unittest.main()

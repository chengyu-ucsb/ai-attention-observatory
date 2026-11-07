"""Offline weekly queue tests: no models, credentials or external discovery."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect_weekly_sources as queue
import full_document_access as access

NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
WINDOW = {'from': '2026-10-26', 'to': '2026-11-01', 'timezone': 'UTC'}
SECRET = 'PRIVATE_SOURCE_SENTINEL_NEVER_SAVED'


def item(number=1, **updates):
    from collection_window import publication_date
    day=publication_date(updates.get('published','2026-10-28'))
    return {'title': 'A verified article about attention and generative artificial intelligence',
            'kind': 'scholarly', 'doi': f'10.5555/weekly{number}',
            'url': f'https://www.econstor.eu/article{number}.pdf',
            'published': '2026-10-28',
            'publication_date_provenance': {'status': 'day_known', 'field': 'published-online',
                'source':'Crossref publisher metadata','value':day.isoformat() if day else ''}, **updates}


def weekly(*records):
    return {'run': {'date': '2026-11-02', 'publication_window': dict(WINDOW)},
            'items': list(records)}


def document(complete=True, text=None, **coverage):
    return access.Document([{'location': 'page:1', 'text': text or (SECRET + ' ') * 500},
                            {'location': 'page:2', 'text': 'END' if complete else ''}],
                           'https://www.econstor.eu/article.pdf?token=PRIVATE_TOKEN#secret',
                           'publishedVersion', {'evidence_status': 'full_document_retrieved' if complete else 'partial_full_text',
                            'pages_total': 2, 'pages_processed': 2, 'pages_with_text': 2 if complete else 1, **coverage})


def result_for(document):
    meta = queue.document_metadata(document)
    return {'document': meta, 'diagnostics': [{'stage': 'article', 'status': meta['evidence_status'],
        'url': meta['source_url'], 'retryable': False}]}


def success(*args):
    return result_for(document())


def run(payload, state=None, **kwargs):
    return queue.run(payload, state, now=NOW, known_sources_only=True,
                     attempt=kwargs.pop('attempt', success), clock=kwargs.pop('clock', lambda: 0), **kwargs)


def rows(state):
    return list(state['records'].values())


class WeeklyQueueTests(unittest.TestCase):
    def test_previous_completed_week_required_before_any_fetch(self):
        for window in (None, {'from': '2026-11-01', 'to': '2026-11-07', 'timezone': 'UTC'},
                       {**WINDOW, 'timezone': 'America/Los_Angeles'},
                       {**WINDOW, 'to': '2026-11-02'}):
            payload = weekly(item()); payload['run']['publication_window'] = window
            fetch = Mock()
            with self.assertRaisesRegex(ValueError, 'previous_completed_utc_week_required'):
                run(payload, attempt=fetch)
            fetch.assert_not_called()

    def test_date_gate_inclusive_and_never_first_seen_updated_or_quality(self):
        records = [item(1, published='2026-10-26', source_quality={'decision': 'hold'}),
                   item(2, published='2026-11-01', reading={'level': 'citation_only'}),
                   item(3, published='2026-10-25', first_seen='2026-10-28'),
                   item(4, published='2026-11-02'),
                   item(5, published='', updated='2026-10-28'),
                   item(6, published='2026-10'),
                   item(7, published='2026-10-28', historical_backfill=True),
                   item(8, publication_date_provenance={'basis': 'publisher_atom_updated'}),
                   item(9, publication_date_provenance={'status': 'unresolved'}),
                   item(10, kind='nonacademic', publication_date_provenance={'basis': 'publisher_rss_pubDate', 'date': '2026-10-28'})]
        fetch = Mock(side_effect=success)
        result = run(weekly(*records), attempt=fetch)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(result['run']['selected_records'], 3)
        self.assertEqual(result['run']['excluded']['excluded_outside_publication_window'], 2)
        self.assertEqual(result['run']['excluded']['excluded_nonpublication_date'], 1)
        self.assertFalse(result['run']['model_used'])

    def test_utc_boundary_conversion(self):
        result = run(weekly(item(1, published='2026-11-02T00:30:00+02:00'),
                            item(2, published='2026-10-25T23:30:00-02:00'),
                            item(3, published='2026-11-01T23:30:00-02:00')))
        self.assertEqual(result['run']['selected_records'], 2)
        self.assertEqual({r['published'] for r in rows(result)}, {'2026-11-01', '2026-10-26'})

    def test_complete_unchanged_inputs_are_not_refetched(self):
        first = run(weekly(item()))
        fetch = Mock()
        repeated = run(weekly(item(first_seen='2026-11-07', reading={'level': 'held'})), first, attempt=fetch)
        fetch.assert_not_called()
        self.assertEqual(repeated['run']['attempted_records'], 0)
        self.assertEqual(rows(repeated)[0]['attempts'], 1)

    def test_changed_candidate_version_or_url_reopens(self):
        record = item(fulltext_candidates=[{'url': 'https://www.econstor.eu/version.pdf', 'version': 'v1'}])
        first = run(weekly(record))
        updated = copy.deepcopy(record); updated['fulltext_candidates'][0]['version'] = 'v2'
        fetch = Mock(side_effect=success)
        changed = run(weekly(updated), first, attempt=fetch)
        self.assertEqual(fetch.call_count, 1)
        self.assertNotEqual(rows(changed)[0]['fingerprint'], rows(first)[0]['fingerprint'])

    def test_changed_registry_route_reopens(self):
        with patch.object(access, 'registry_candidates', return_value=[]):
            first = run(weekly(item()))
        with patch.object(access, 'registry_candidates', return_value=[{'url': 'https://www.econstor.eu/new.pdf', 'version': 'v2'}]):
            fetch = Mock(side_effect=success)
            run(weekly(item()), first, attempt=fetch)
        self.assertEqual(fetch.call_count, 1)

    def test_limit_and_fair_cursor_resume_remaining_records(self):
        payload = weekly(*(item(i) for i in range(5)))
        first = run(payload, limit=2)
        second = run(payload, first, limit=2)
        third = run(payload, second, limit=2)
        self.assertEqual(first['run']['pending_records'], 3)
        self.assertEqual(second['run']['pending_records'], 1)
        self.assertEqual(third['run']['pending_records'], 0)
        self.assertEqual(first['run']['stop_reason'], 'record_limit')
        self.assertTrue(all(row['attempts'] == 1 for row in rows(third)))

    def test_candidate_cursor_does_not_repeat_permanent_known_route_failure(self):
        record = item(fulltext_candidates=[{'url': 'https://www.econstor.eu/first.pdf'}])
        failed = Mock(return_value={'diagnostics': [{'stage': 'article', 'status': 'article_http_403', 'retryable': False}]})
        first = run(weekly(record), attempt=failed)
        self.assertEqual(rows(first)[0]['cursor']['known'], 1)
        self.assertEqual(rows(first)[0]['status'], 'pending_routes')
        fetch = Mock(side_effect=success)
        final = run(weekly(record), first, attempt=fetch)
        self.assertEqual(fetch.call_args.args[1]['source']['url'], record['url'])
        self.assertTrue(rows(final)[0]['complete'])

    def test_retry_after_preserved_and_429_distinct_from_access_blocked(self):
        rate = Mock(return_value={'diagnostics': [{'status': 'article_http_429', 'retryable': True, 'retry_after_seconds': 7200}]})
        state = run(weekly(item()), attempt=rate)
        self.assertEqual(rows(state)[0]['status'], 'rate_limited')
        self.assertEqual(rows(state)[0]['next_retry_at'], '2026-11-07T14:00:00+00:00')
        run(weekly(item()), state, attempt=rate)
        self.assertEqual(rate.call_count, 1)
        self.assertEqual(rows(state)[0]['cursor']['known'], 0)
        blocked = run(weekly(item()), attempt=lambda *a: {'diagnostics': [{'status': 'article_http_403', 'retryable': False}]})
        self.assertEqual(rows(blocked)[0]['status'], 'access_blocked')
        self.assertTrue(rows(blocked)[0]['complete'])

    def test_retry_resumes_when_due(self):
        first = run(weekly(item()), attempt=lambda *a: {'diagnostics': [{'status': 'URLError', 'retryable': True, 'retry_after_seconds': 1}]})
        final = queue.run(weekly(item()), first, now='2026-11-07T12:00:01Z', known_sources_only=True, attempt=success)
        self.assertTrue(rows(final)[0]['complete'])
        self.assertEqual(rows(final)[0]['attempts'], 2)

    def test_exception_passages_and_query_credentials_are_not_saved(self):
        def bad(*args):
            raise ValueError(SECRET + ' https://source.test/?api_key=PRIVATE_TOKEN')
        state = run(weekly(item(url='https://www.econstor.eu/a.pdf?tracking=PRIVATE_TOKEN#fragment')), attempt=bad)
        serialized = json.dumps(state)
        self.assertNotIn(SECRET, serialized)
        self.assertNotIn('PRIVATE_TOKEN', serialized)
        self.assertEqual(rows(state)[0]['diagnostics'][0]['status'], 'ValueError')

    def test_document_coverage_metadata_keeps_every_interval_not_prose(self):
        state = run(weekly(item()))
        meta = rows(state)[0]['document']
        self.assertEqual(meta['semantic_completeness'], 'not_verified')
        self.assertEqual(meta['review_status'], 'not_reviewed')
        self.assertFalse(meta['redistribution_granted'])
        self.assertTrue(meta['all_retrieved_text_chunked'])
        self.assertEqual(meta['units'][1]['characters'], 3)
        intervals = [r for c in meta['chunk_intervals'] for r in c['ranges']]
        self.assertEqual(sum(r['end'] - r['start'] for r in intervals), sum(unit['characters'] for unit in meta['units']))
        self.assertNotIn(SECRET, json.dumps(state))
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(state))
        self.assertNotIn('text', meta)

    def test_manifest_unknown_fields_and_location_strings_never_escape(self):
        doc = access.Document([{'location': SECRET, 'text': 'body text'}],
            'https://www.econstor.eu/a.pdf?x=secret', SECRET,
            {'document_title': SECRET, 'reported_license': SECRET, 'source_excerpt': SECRET,
             'semantic_completeness': 'verified', 'evidence_status': 'partial_full_text'})
        meta = queue.document_metadata(doc)
        self.assertNotIn(SECRET, json.dumps(meta))
        self.assertEqual(meta['document_version'], 'unspecified')

    def test_html_partial_text_is_never_semantically_complete(self):
        state = run(weekly(item(kind='nonacademic')), attempt=lambda *a: result_for(
            document(False, html_completeness='not_verified')))
        self.assertEqual(rows(state)[0]['status'], 'partial_full_text_not_reviewed')
        self.assertEqual(rows(state)[0]['document']['semantic_completeness'], 'not_verified')

    def test_coverage_gap_and_duplicate_locations_fail_closed(self):
        with patch.object(queue, 'coverage_is_complete', return_value=False):
            with self.assertRaisesRegex(ValueError, 'coverage_gap'):
                queue.document_metadata(document())
        doc = document(); doc.units.append(dict(doc.units[0]))
        with self.assertRaisesRegex(ValueError, 'invalid_document_locations'):
            queue.document_metadata(doc)

    def test_provider_budget_cursor_resumes_without_source_refetch(self):
        record = item(url='https://doi.org/10.5555/weekly1')
        tried = [queue.digest('https://www.econstor.eu/a.pdf'), queue.digest('https://www.econstor.eu/b.pdf')]
        result = {'diagnostics': [{'stage': 'discovery', 'status': 'candidates', 'candidates': 5, 'retryable': False},
                  {'stage': 'article', 'status': 'article_http_404', 'retryable': False},
                  {'stage': 'article', 'status': 'article_http_404', 'retryable': False}], 'tried_sources': tried}
        first = queue.run(weekly(record), now=NOW, attempt=lambda *a: result, max_candidates=2)
        self.assertEqual(rows(first)[0]['cursor']['provider_tried'], sorted(tried))
        fetch = Mock(return_value={'diagnostics': [{'stage': 'discovery', 'status': 'no_exact_match', 'candidates': 0, 'retryable': False}]})
        second = queue.run(weekly(record), first, now=NOW, attempt=fetch)
        self.assertEqual(fetch.call_args.args[1]['tried_sources'], sorted(tried))
        self.assertEqual(rows(second)[0]['cursor']['provider'], 1)

    def test_known_sources_only_never_calls_locators(self):
        record = item()
        with patch.object(access, 'retrieve', return_value=(document(), [])) as retrieve:
            queue.perform_stage(record, {'kind': 'known', 'source': {'url': record['url']}, 'publication_window': WINDOW}, 8)
        self.assertEqual(retrieve.call_args.kwargs['providers'], [])
        self.assertEqual(retrieve.call_args.kwargs['known_sources'], [{'url': record['url']}])
        self.assertNotIn('OpenAlex XML', queue.PROVIDERS)
        self.assertNotIn('Unpaywall', queue.PROVIDERS)

    def test_optional_known_sources_override_skips_registry(self):
        with patch.object(access, 'known_candidates', side_effect=AssertionError('must not expand')), \
             patch.object(access, 'fetch_candidate', return_value=document()):
            result, ledger = access.retrieve(item(), providers=[], known_sources=[{'url': 'https://www.econstor.eu/only.pdf'}])
        self.assertIsNotNone(result)
        self.assertEqual(len(ledger), 1)

    def test_older_related_preprint_and_outside_candidate_not_fetched(self):
        record = item(fulltext_candidates=[
            {'url': 'https://arxiv.org/abs/2410.12345v1', 'doi': '10.48550/arxiv.2410.12345', 'related_doi': '10.5555/weekly1'},
            {'url': 'https://www.econstor.eu/old.pdf', 'published': '2024-02-01'}])
        fetch = Mock(side_effect=success)
        state = run(weekly(record), attempt=fetch)
        self.assertEqual(fetch.call_args.args[1]['source']['url'], record['url'])
        self.assertEqual(rows(state)[0]['excluded_related_or_outside_window_routes'], 3)

    def test_no_route_stays_honest_and_duplicate_inputs_not_retrieved_twice(self):
        record = item(url='https://doi.org/10.5555/weekly1')
        state = run(weekly(record, record))
        self.assertEqual(state['run']['duplicate_records'], 1)
        self.assertEqual(state['run']['attempted_records'], 0)
        self.assertEqual(rows(state)[0]['status'], 'source_unavailable')

    def test_time_budget_stops_before_another_record(self):
        moments = iter([0, 0, 20, 20])
        fetch = Mock(side_effect=success)
        state = run(weekly(item(1), item(2)), attempt=fetch, time_budget=10, clock=lambda: next(moments))
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(state['run']['stop_reason'], 'time_budget')
        self.assertEqual(state['run']['pending_records'], 1)

    def test_in_progress_checkpoint_can_resume_interrupted_run(self):
        checkpoints = []
        first = run(weekly(item()), save=lambda x: checkpoints.append(copy.deepcopy(x)))
        self.assertEqual(rows(checkpoints[0])[0]['status'], 'in_progress')
        resumed = run(weekly(item()), checkpoints[0])
        self.assertTrue(rows(resumed)[0]['complete'])
        self.assertEqual(rows(resumed)[0]['attempts'], 2)

    def test_atomic_state_file_has_only_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            state = run(weekly(item()), save=lambda x: queue.atomic_save(path, x))
            self.assertEqual(json.loads(path.read_text()), state)
            self.assertNotIn(SECRET, path.read_text())
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_legacy_registry_date_without_provenance_is_not_retrieved(self):
        fetch = Mock()
        state = run(weekly(item(publication_date_provenance={})), attempt=fetch)
        fetch.assert_not_called()
        self.assertEqual(state['run']['excluded']['excluded_unverified_original_publication_date'], 1)

    def test_spawned_worker_reports_guard_rejection_without_network(self):
        result = queue.bounded_stage(item(), {'kind': 'known', 'source': {'url': 'http://127.0.0.1/private'}, 'publication_window': WINDOW}, 1, 5)
        self.assertEqual(result['diagnostics'][0]['status'], 'route_policy_excluded')
        self.assertNotIn('document', result)

    def test_cutoff_terminates_worker_and_returns_retry_metadata(self):
        import threading
        receiver, sender, child, context = Mock(), Mock(), Mock(), Mock()
        release = threading.Event()
        receiver.recv_bytes.side_effect = lambda n: release.wait(.2)
        child.is_alive.side_effect = [True, False]
        child.terminate.side_effect = release.set
        context.Pipe.return_value = (receiver, sender)
        context.Process.return_value = child
        with patch.object(queue.multiprocessing, 'get_context', return_value=context):
            result = queue.bounded_stage(item(), {'kind': 'known'}, 1, .01)
        child.terminate.assert_called_once()
        self.assertEqual(result['diagnostics'][0]['status'], 'deferred_time_budget')
        self.assertTrue(result['diagnostics'][0]['retryable'])

    def test_provider_cursor_tracks_urls_not_response_order(self):
        record = item(url='https://doi.org/10.5555/weekly1')
        candidates = [{'url': f'https://www.econstor.eu/{letter}.pdf', 'doi': record['doi']} for letter in 'abc']
        provider = Mock(side_effect=[candidates, [candidates[2], candidates[0], candidates[1]], list(reversed(candidates))])
        seen = []
        def fetch(candidate, record):
            seen.append(candidate['url'])
            raise HTTPError(candidate['url'], 404, 'not found', {}, None)
        state = None
        with patch.object(access, 'default_providers', return_value=[('Europe PMC XML', provider)]), \
             patch.object(access, 'fetch_candidate', side_effect=fetch):
            for _ in range(3):
                state = queue.run(weekly(record), state, now=NOW, max_candidates=1,
                    attempt=lambda r, p, n, t: queue.perform_stage(r, p, n))
        self.assertEqual(seen, [r['url'] for r in candidates])
        self.assertEqual(rows(state)[0]['cursor']['provider'], 1)

    def test_old_arxiv_candidate_date_applies_to_derived_pdf_route(self):
        record = item(doi='', url='https://arxiv.org/abs/2610.31335v1',
                      fulltext_candidates=[{'url': 'https://arxiv.org/abs/2610.31335v1', 'published': '2026-10-22'}])
        routes, excluded = queue.eligible_routes(record, WINDOW)
        self.assertEqual(routes, [])
        self.assertEqual(excluded, 2)

    def test_429_pauses_other_records_on_the_same_provider_or_host(self):
        rate = Mock(return_value={'diagnostics': [{'stage': 'article', 'status': 'article_http_429',
                                                 'retryable': True, 'retry_after_seconds': 600}]})
        state = run(weekly(item(1), item(2)), attempt=rate)
        self.assertEqual(rate.call_count, 1)
        self.assertEqual(state['run']['deferred_retry_records'], 2)
        self.assertIn('host:www.econstor.eu', state['run']['active_provider_pauses'])
        records = [item(i, url=f'https://doi.org/10.5555/weekly{i}') for i in (1, 2)]
        rate.reset_mock()
        state = queue.run(weekly(*records), now=NOW, attempt=rate)
        self.assertEqual(rate.call_count, 1)
        self.assertIn('provider:Europe PMC XML', state['provider_pauses'])

    def test_new_host_allowlist_is_exact_and_does_not_allow_subdomain_lookalikes(self):
        for host in ('eff.org', 'www.eff.org', 'niemanlab.org', 'www.niemanlab.org',
                     'ainowinstitute.org', 'www.ainowinstitute.org', 'themarkup.org', 'www.themarkup.org'):
            self.assertTrue(access.safe_url(f'https://{host}/article'))
            self.assertFalse(access.safe_url(f'https://{host}.attacker.example/article'))
        self.assertFalse(access.safe_url('https://unreviewed.eff.org/article'))

    def test_new_week_preserves_unfinished_old_metadata_without_fetching_old_articles(self):
        old = run(weekly(item(1), item(2)), limit=1)
        payload = weekly(item(3, published='2026-11-04'))
        payload['run']['publication_window'] = {'from': '2026-11-02', 'to': '2026-11-08', 'timezone': 'UTC'}
        fetch = Mock(side_effect=success)
        state = queue.run(payload, old, now='2026-11-09', known_sources_only=True, attempt=fetch)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[0]['published'], '2026-11-04')
        self.assertEqual(state['closed_windows'][0]['pending_records'], 1)
        self.assertEqual(state['closed_windows'][0]['status'], 'closed_with_pending_records')
        self.assertEqual(len(state['closed_windows'][0]['pending_record_metadata']), 1)

    def test_conflicting_original_date_evidence_does_not_fetch(self):
        fetch = Mock()
        state = run(weekly(item(publication_date_provenance={'status': 'day_known',
            'value': '2024-02-01', 'field': 'published-online'})), attempt=fetch)
        fetch.assert_not_called()
        self.assertEqual(state['run']['excluded']['excluded_conflicting_publication_date'], 1)

    def test_duplicate_record_new_candidate_is_merged_and_reopens_completion(self):
        old = run(weekly(item()))
        second = item(fulltext_candidates=[{'url': 'https://www.econstor.eu/new-version.pdf', 'version': 'v2'}])
        fetch = Mock(side_effect=success)
        state = run(weekly(item(), second), old, attempt=fetch)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(state['run']['duplicate_records'], 1)
        unchanged = Mock()
        run(weekly(second, item()), state, attempt=unchanged)
        unchanged.assert_not_called()

    def test_identical_duplicates_do_not_repeat_a_blocked_route(self):
        record = item()
        fetch = Mock(return_value={'diagnostics': [{'status': 'article_http_403', 'retryable': False}]})
        state = run(weekly(record, record), attempt=fetch)
        self.assertTrue(rows(state)[0]['complete'])
        run(weekly(record, record), state, attempt=fetch)
        self.assertEqual(fetch.call_count, 1)

    def test_corrupt_saved_rows_are_refused_without_save_or_fetch(self):
        good = run(weekly(item()))
        mutations = [
            lambda s: rows(s)[0].update(raw_text=SECRET),
            lambda s: rows(s)[0]['document'].update(raw_text=SECRET),
            lambda s: rows(s)[0]['document'].update(source_sha256='bad'),
            lambda s: rows(s)[0]['document'].update(chunks_total=999),
            lambda s: rows(s)[0]['document']['chunk_intervals'][0]['ranges'][0].update(start=1),
            lambda s: rows(s)[0]['document']['units'][0].update(characters=1),
            lambda s: rows(s)[0]['document'].update(pages_with_text=1),
            lambda s: rows(s)[0]['document_evidence'].update(url='https://www.econstor.eu/other.pdf'),
            lambda s: rows(s)[0]['cursor'].update(known=-1),
            lambda s: rows(s)[0]['cursor'].update(provider=999),
            lambda s: rows(s)[0].update(attempts=True),
            lambda s: rows(s)[0].update(source_url='https://www.econstor.eu/a?token=SECRET'),
            lambda s: s.update(raw_source=SECRET),
            lambda s: s['provider_pauses'].update({'provider:' + SECRET: '2026-11-07T13:00:00+00:00'}),
        ]
        for mutate in mutations:
            state = copy.deepcopy(good); mutate(state)
            # Recompute the checksum so this exercises the schema, not just
            # checksum mismatch detection. It is not an authenticity signature.
            state['state_sha256'] = queue.digest({k: v for k, v in state.items() if k != 'state_sha256'})
            fetch, save = Mock(), Mock()
            with self.subTest(mutation=mutate), self.assertRaisesRegex(ValueError, 'invalid_acquisition_state'):
                run(weekly(item()), state, attempt=fetch, save=save)
            fetch.assert_not_called(); save.assert_not_called()

    def test_forged_complete_flag_and_old_schema_are_not_repaired_or_refetched(self):
        for change in ('flag', 'old_version', 'checksum'):
            state = run(weekly(item()), limit=0)
            if change == 'flag':
                rows(state)[0].update(complete=True, status='full_document_retrieved_not_reviewed')
                state['state_sha256'] = queue.digest({k: v for k, v in state.items() if k != 'state_sha256'})
            elif change == 'old_version':
                state['schema_version'] = 1
            else:
                state['state_sha256'] = '0' * 64
            fetch, save = Mock(), Mock()
            with self.assertRaisesRegex(ValueError, 'invalid_acquisition_state'):
                run(weekly(item()), state, attempt=fetch, save=save)
            fetch.assert_not_called(); save.assert_not_called()

    def test_archived_state_is_recursively_validated(self):
        old = run(weekly(item()), limit=0)
        payload = weekly(item(2, published='2026-11-04'))
        payload['run']['publication_window'] = {'from': '2026-11-02', 'to': '2026-11-08', 'timezone': 'UTC'}
        state = queue.run(payload, old, now='2026-11-09', limit=0)
        archive = next(iter(state['closed_windows'][0]['pending_record_metadata'].values()))
        archive['raw_text'] = SECRET
        state['state_sha256'] = queue.digest({k: v for k, v in state.items() if k != 'state_sha256'})
        with self.assertRaisesRegex(ValueError, 'invalid_acquisition_state'):
            queue.validate_state(state)

    def test_atomic_save_rejects_invalid_state_before_touching_existing_file(self):
        state = run(weekly(item()), limit=0)
        state['raw_text'] = SECRET
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'; path.write_text('original bytes')
            with self.assertRaisesRegex(ValueError, 'invalid_acquisition_state'):
                queue.atomic_save(path, state)
            self.assertEqual(path.read_text(), 'original bytes')
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_removed_and_newly_excluded_same_week_records_have_dispositions(self):
        previous = run(weekly(item(1), item(2), item(3)), limit=0)
        current = run(weekly(item(1), item(3, publication_date_provenance={})), previous, limit=0)
        self.assertEqual(current['run']['pending_records'], 1)
        self.assertEqual(len(current['dispositions']), 2)
        self.assertEqual({d['reason'] for d in current['dispositions']},
                         {'removed_from_input', 'excluded_unverified_original_publication_date'})
        self.assertTrue(all(not d['record']['complete'] for d in current['dispositions']))
        queue.validate_state(current)

    def test_readding_unchanged_completed_record_uses_retained_disposition(self):
        old = run(weekly(item()))
        removed = run(weekly(), old)
        fetch = Mock()
        readded = run(weekly(item()), removed, attempt=fetch)
        fetch.assert_not_called()
        self.assertTrue(rows(readded)[0]['complete'])
        self.assertEqual(removed['dispositions'][0]['reason'], 'removed_from_input')

    def test_replaced_candidate_version_retains_old_result_metadata(self):
        old = run(weekly(item()))
        changed = run(weekly(item(fulltext_candidates=[{'url': 'https://www.econstor.eu/v2.pdf'}])), old)
        self.assertEqual(changed['dispositions'][0]['reason'], 'replaced_input_version')
        self.assertTrue(changed['dispositions'][0]['record']['complete'])

    def test_openalex_tei_and_credentialed_queries_never_reach_retrieval(self):
        routes = [
            {'url': 'https://content.openalex.org/works/W12345.grobid-xml', 'structured_format': 'tei'},
            {'url': 'https://www.econstor.eu/p.pdf?api_key=DUMMY'},
            {'url': 'https://www.econstor.eu/p.pdf?X-Amz-Signature=DUMMY'},
            {'url': 'https://www.econstor.eu/p.pdf?token=DUMMY'},
        ]
        for route in routes:
            record = item(url='https://doi.org/10.5555/weekly1', fulltext_candidates=[route])
            fetch = Mock()
            result = run(weekly(record), attempt=fetch)
            fetch.assert_not_called()
            self.assertEqual(rows(result)[0]['excluded_related_or_outside_window_routes'], 1)
            with patch.dict('os.environ', {'OPENALEX_API_KEY': 'DUMMY'}), patch.object(access, 'retrieve') as retrieve:
                result = queue.perform_stage(record, {'kind': 'known', 'source': route, 'publication_window': WINDOW}, 1)
                retrieve.assert_not_called()
                self.assertEqual(result['diagnostics'][0]['status'], 'route_policy_excluded')

    def test_provider_routes_obey_date_relation_and_credential_policy(self):
        record = item(url='https://doi.org/10.5555/weekly1')
        found = [
            {'url': 'https://www.econstor.eu/old.pdf', 'published': '2024-02-01'},
            {'url': 'https://www.econstor.eu/related.pdf', 'related_doi': record['doi']},
            {'url': 'https://www.econstor.eu/auth.pdf?token=DUMMY'},
            {'url': 'https://content.openalex.org/works/W1.grobid-xml', 'structured_format': 'tei'},
            {'url': 'https://www.econstor.eu/current.pdf', 'published': '2026-10-28'}]
        fetch = Mock(side_effect=lambda option, r: (_ for _ in ()).throw(HTTPError(option['url'], 404, 'missing', {}, None)))
        with patch.object(access, 'default_providers', return_value=[('Europe PMC XML', lambda _: found)]), \
             patch.object(access, 'fetch_candidate', fetch):
            result = queue.perform_stage(record, {'kind': 'provider', 'name': 'Europe PMC XML',
                'tried_sources': [], 'publication_window': WINDOW}, 8)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[0]['url'], found[-1]['url'])
        self.assertEqual(result['tried_sources'], [queue.digest(found[-1]['url'])])

    def test_provider_stops_immediately_after_first_rate_limit(self):
        record = item(url='https://doi.org/10.5555/weekly1')
        found = [{'url': f'https://www.econstor.eu/{n}.pdf'} for n in range(3)]
        fetch = Mock(side_effect=HTTPError(found[0]['url'], 429, 'quota', {'Retry-After': '7200'}, None))
        with patch.object(access, 'default_providers', return_value=[('Europe PMC XML', lambda _: found)]), \
             patch.object(access, 'fetch_candidate', fetch):
            result = queue.perform_stage(record, {'kind': 'provider', 'name': 'Europe PMC XML',
                'tried_sources': [], 'publication_window': WINDOW}, 3)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result['tried_sources'], [])
        self.assertTrue(any(d['status'] == 'article_http_429' for d in result['diagnostics']))

    def test_retry_after_starts_at_response_time_not_run_start(self):
        moments = iter([0, 0, 45])
        state = run(weekly(item()), clock=lambda: next(moments), attempt=lambda *a: {
            'diagnostics': [{'status': 'article_http_429', 'retryable': True, 'retry_after_seconds': 10}]})
        self.assertEqual(rows(state)[0]['next_retry_at'], '2026-11-07T12:00:55+00:00')
        self.assertEqual(state['provider_pauses']['host:www.econstor.eu'], '2026-11-07T12:00:55+00:00')

    def test_nested_publisher_pdf_rate_limit_is_not_swallowed(self):
        root = 'https://www.econstor.eu/article'; pdf1 = root + '/a.pdf'; pdf2 = root + '/b.pdf'
        def request(url, *args, **kwargs):
            if url == root:
                return b'<html>article</html>', root, 'text/html'
            raise HTTPError(url, 429, 'quota', {'Retry-After': '7200'}, None)
        with patch.object(access, 'robots_allowed', return_value=True), \
             patch.object(access, 'request', side_effect=request) as fetched, \
             patch.object(access, 'publisher_pdf_links', return_value=[pdf1, pdf2]), \
             patch.object(access, 'document_from_html') as html:
            doc, ledger = access.retrieve(item(), providers=[], known_sources=[{'url': root}])
        self.assertIsNone(doc)
        self.assertEqual([call.args[0] for call in fetched.call_args_list], [root, pdf1])
        self.assertEqual(ledger[0]['status'], 'article_http_429')
        self.assertEqual(ledger[0]['retry_after_seconds'], 7200)
        html.assert_not_called()

    def test_robots_temporary_errors_propagate_but_permanent_denials_do_not(self):
        from urllib.error import URLError
        for error in (HTTPError('https://www.econstor.eu/robots.txt', 429, 'quota', {}, None),
                      HTTPError('https://www.econstor.eu/robots.txt', 503, 'unavailable', {}, None),
                      URLError('temporary transport')):
            with patch.object(access, 'request', side_effect=error), self.assertRaises(type(error)):
                access.robots_allowed('https://www.econstor.eu/article')
        for status, expected in ((403, False), (404, True)):
            with patch.object(access, 'request', side_effect=HTTPError('https://www.econstor.eu/robots.txt', status, '', {}, None)):
                self.assertEqual(access.robots_allowed('https://www.econstor.eu/article'), expected)

    def test_retry_after_http_date_is_parsed_and_bounded(self):
        from email.utils import format_datetime
        from datetime import timedelta
        future = format_datetime(NOW + timedelta(seconds=900), usegmt=True)
        with patch.object(access, 'datetime') as clock:
            clock.now.return_value = NOW
            result = access.failure_diagnostic(HTTPError('https://www.econstor.eu/a', 429, '', {'Retry-After': future}, None))
        self.assertEqual(result['retry_after_seconds'], 900)

    @unittest.skipUnless('fork' in queue.multiprocessing.get_all_start_methods(), 'POSIX partial-frame regression')
    def test_full_ipc_frame_receipt_has_deadline(self):
        import os, struct, time
        context = queue.multiprocessing.get_context('fork')
        def partial(sender, *args):
            os.write(sender.fileno(), struct.pack('!i', 10000) + b'x')
            time.sleep(.4)
            sender.close()
        started = time.monotonic()
        with patch.object(queue.multiprocessing, 'get_context', return_value=context), \
             patch.object(queue, 'child_stage', partial):
            result = queue.bounded_stage(item(), {}, 1, .02)
        self.assertLess(time.monotonic() - started, .25)
        self.assertEqual(result['diagnostics'][0]['status'], 'deferred_time_budget')

    def test_completed_source_denial_is_not_retried_through_another_provider(self):
        record = item()
        candidate = {'url': record['url'], 'doi': record['doi']}
        fetch = Mock(side_effect=HTTPError(record['url'], 403, 'denied', {}, None))
        with patch.object(access, 'default_providers', return_value=[(name, lambda _: [candidate]) for name in queue.PROVIDERS]), \
             patch.object(access, 'fetch_candidate', fetch):
            state = None
            for _ in range(5):
                state = queue.run(weekly(record), state, now=NOW,
                    attempt=lambda r, p, n, t: queue.perform_stage(r, p, n))
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(rows(state)[0]['status'], 'access_blocked')
        self.assertTrue(rows(state)[0]['complete'])

    def test_doi_less_news_never_calls_or_plans_identifier_locators(self):
        record = item(kind='nonacademic', doi='')
        provider = Mock()
        with patch.object(access, 'default_providers', return_value=[('Europe PMC XML', provider)]):
            result = queue.perform_stage(record, {'kind': 'provider', 'name': 'Europe PMC XML',
                'tried_sources': [], 'publication_window': WINDOW}, 1)
            provider.assert_not_called()
            self.assertEqual(result['diagnostics'][0]['status'], 'no_exact_match')
        state = queue.run(weekly(record), now=NOW, attempt=lambda *a: result_for(document(False)))
        self.assertTrue(rows(state)[0]['complete'])
        self.assertFalse(rows(state)[0]['plan']['doi_lookup_permitted'])

    def test_whitespace_only_pdf_page_retains_physical_coverage_honestly(self):
        doc = document(False)
        doc.units[1]['text'] = ' \n\t'
        meta = queue.document_metadata(doc)
        queue.validate_document(meta)
        self.assertEqual(meta['units'][1]['characters'], 3)
        self.assertFalse(meta['units'][1]['has_text'])
        self.assertEqual(meta['pages_with_text'], 1)
        state = run(weekly(item()), attempt=lambda *a: result_for(doc))
        self.assertEqual(rows(state)[0]['status'], 'partial_full_text_not_reviewed')

    def test_article_rate_limit_pauses_actual_host_before_next_known_record(self):
        known = item(100)
        first = next(item(n, url=f'https://doi.org/10.5555/weekly{n}') for n in range(1, 100)
                     if queue.record_key(item(n, url=f'https://doi.org/10.5555/weekly{n}')) < queue.record_key(known))
        fetch = Mock(return_value={'diagnostics': [{'stage': 'article', 'status': 'article_http_429',
            'url': 'https://link.springer.com/article/example',
            'failure_url': known['url'], 'retryable': True, 'retry_after_seconds': 600}]})
        state = queue.run(weekly(first, known), now=NOW, attempt=fetch, clock=lambda: 0)
        self.assertEqual(fetch.call_count, 1)
        self.assertIn('provider:Europe PMC XML', state['provider_pauses'])
        self.assertIn('host:www.econstor.eu', state['provider_pauses'])
        self.assertEqual(state['records'][queue.record_key(known)]['status'], 'rate_limited')
        self.assertEqual(state['records'][queue.record_key(known)]['attempts'], 0)

    def test_other_locator_respects_existing_article_host_cooldown(self):
        record = item()
        plan = {'kind': 'provider', 'name': 'CORE', 'tried_sources': [],
                'publication_window': WINDOW, 'host_backoff': {'www.econstor.eu': 600}}
        with patch.object(access, 'default_providers', return_value=[('CORE', lambda _: [{'url': record['url']}])]), \
             patch.object(access, 'fetch_candidate') as fetch:
            result = queue.perform_stage(record, plan, 8)
        fetch.assert_not_called()
        self.assertEqual(result['diagnostics'][-1]['status'], 'rate_limit_pause')
        self.assertTrue(result['diagnostics'][-1]['retryable'])

    def test_anonymous_queue_rejects_nested_pdf_credentials_before_request(self):
        record = item(); root = 'https://www.econstor.eu/article'
        for key in ('api_key', 'auth', 'sig'):
            page = (f'<meta name="citation_doi" content="{record["doi"]}">'
                    f'<meta name="citation_title" content="{record["title"]}">'
                    f'<meta name="citation_pdf_url" content="https://www.econstor.eu/file.pdf?{key}=DUMMY">').encode()
            doc = document(False); doc.url = root
            with patch.object(access, 'robots_allowed', return_value=True), \
                 patch.object(access, 'request', return_value=(page, root, 'text/html')) as request, \
                 patch.object(access, 'document_from_html', return_value=doc):
                access.retrieve(record, providers=[], known_sources=[{'url': root}], anonymous_only=True)
            self.assertEqual([call.args[0] for call in request.call_args_list], [root])
        self.assertFalse(access.ANONYMOUS_ONLY.get())

    def test_anonymous_requests_and_redirects_reject_sensitive_query_keys(self):
        from urllib.request import Request
        scope = access.ANONYMOUS_ONLY.set(True)
        try:
            for key in ('api_key', 'auth', 'sig', 'X-Amz-Signature', 'X-Goog-Credential'):
                target = 'https://www.econstor.eu/file.pdf?' + key + '=DUMMY'
                with patch.object(access, 'build_opener') as opener, \
                     self.assertRaisesRegex(ValueError, 'credentialed_source_url_disallowed'):
                    access.request(target)
                opener.assert_not_called()
                with self.assertRaisesRegex(ValueError, 'credentialed_source_url_disallowed'):
                    access.Guard(access.ARTICLE_HOSTS).redirect_request(
                        Request('https://www.econstor.eu/article'), None, 302, '', {}, target)
        finally:
            access.ANONYMOUS_ONLY.reset(scope)

    def test_shared_nested_failure_host_does_not_replace_record_counter_keys(self):
        from itertools import permutations
        hosts = ['www.eff.org', 'www.niemanlab.org', 'www.econstor.eu',
                 'www.ainowinstitute.org', 'www.themarkup.org', 'www.nngroup.com', 'techpolicy.press']
        nested, first, second = next((q, p, r) for q, p, r in permutations(hosts, 3)
            if list({'host:' + p, 'host:' + q})[-1] == 'host:' + q
            and list({'host:' + r, 'host:' + q})[-1] == 'host:' + q)
        fetch = Mock(return_value={'diagnostics': [{'stage': 'article', 'status': 'article_http_429',
            'failure_url': f'https://{nested}/shared.pdf', 'retryable': True, 'retry_after_seconds': 600}]})
        state = run(weekly(item(1, url=f'https://{first}/one'),
                           item(2, url=f'https://{second}/two')), attempt=fetch)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(state['run']['attempted_records'], 2)
        self.assertEqual(state['run']['attempted_stages'], 2)
        queue.validate_state(state)

    def test_nested_pdf_host_cooldown_is_deferred_without_new_http_response(self):
        record = item(url='https://www.eff.org/article')
        pdf = 'https://www.econstor.eu/shared.pdf'
        page = (f'<meta name="citation_doi" content="{record["doi"]}">'
                f'<meta name="citation_title" content="{record["title"]}">'
                f'<meta name="citation_pdf_url" content="{pdf}">').encode()
        previous = run(weekly(record), limit=0)
        pause = '2026-11-07T12:10:00+00:00'
        previous['provider_pauses'] = {'host:www.econstor.eu': pause}
        previous['run']['active_provider_pauses'] = dict(previous['provider_pauses'])
        queue.seal_state(previous)
        with patch.object(access, 'robots_allowed', return_value=True) as robots, \
             patch.object(access, 'request', return_value=(page, record['url'], 'text/html')) as request, \
             patch.object(access, 'document_from_html') as html:
            state = run(weekly(record), previous,
                        attempt=lambda r, p, n, t: queue.perform_stage(r, p, n))
        self.assertEqual([call.args[0] for call in request.call_args_list], [record['url']])
        self.assertEqual([call.args[0] for call in robots.call_args_list], [record['url']])
        html.assert_not_called()
        self.assertEqual(rows(state)[0]['status'], 'rate_limited')
        self.assertEqual(rows(state)[0]['cursor']['known'], 0)
        self.assertEqual(rows(state)[0]['tried_sources'], [])
        self.assertEqual(state['provider_pauses'], previous['provider_pauses'])
        paused = next(d for d in rows(state)[0]['diagnostics'] if d['status'] == 'rate_limit_pause')
        self.assertTrue(paused['retryable'])
        self.assertEqual(paused['failure_url'], pdf)
        self.assertFalse(any(d['status'].endswith('http_429') for d in rows(state)[0]['diagnostics']))
        self.assertIsNone(access.HOST_COOLDOWNS.get())

    def test_existing_cooldown_blocks_requests_robots_and_redirects(self):
        from urllib.request import Request
        scope = access.HOST_COOLDOWNS.set({'www.econstor.eu': queue.time.monotonic() + 600})
        target = 'https://www.econstor.eu/target.pdf'
        try:
            with patch.object(access, 'build_opener') as opener, self.assertRaises(access.HostRateLimitPause):
                access.request(target)
            opener.assert_not_called()
            with patch.object(access, 'request') as request, self.assertRaises(access.HostRateLimitPause):
                access.robots_allowed(target)
            request.assert_not_called()
            with self.assertRaises(access.HostRateLimitPause) as caught:
                access.Guard(access.ARTICLE_HOSTS).redirect_request(
                    Request('https://www.eff.org/article'), None, 302, '', {}, target)
            outcome = access.failure_diagnostic(caught.exception, article=True)
            self.assertEqual(outcome['status'], 'rate_limit_pause')
            self.assertEqual(outcome['failure_url'], target)
            self.assertTrue(outcome['retryable'])
        finally:
            access.HOST_COOLDOWNS.reset(scope)

    def test_nested_redirect_pause_is_not_swallowed_as_html_fallback(self):
        record = item(url='https://www.eff.org/article')
        pdf = 'https://www.niemanlab.org/allowed.pdf'
        final = 'https://www.econstor.eu/paused.pdf'
        def request(url, *args, **kwargs):
            if url == record['url']:
                return b'<html>article</html>', url, 'text/html'
            raise access.HostRateLimitPause(final, 500)
        with patch.object(access, 'robots_allowed', return_value=True), \
             patch.object(access, 'request', side_effect=request) as fetched, \
             patch.object(access, 'publisher_pdf_links', return_value=[pdf]), \
             patch.object(access, 'document_from_html') as html:
            doc, ledger = access.retrieve(record, providers=[], known_sources=[{'url': record['url']}],
                anonymous_only=True, host_backoff={'www.econstor.eu': 600})
        self.assertIsNone(doc)
        self.assertEqual([call.args[0] for call in fetched.call_args_list], [record['url'], pdf])
        self.assertEqual(ledger[0]['status'], 'rate_limit_pause')
        self.assertEqual(ledger[0]['failure_url'], final)
        html.assert_not_called()

    def test_robots_redirect_existing_pause_is_not_mislabeled_permanent(self):
        failure = access.HostRateLimitPause('https://www.econstor.eu/robots.txt', 500)
        with patch.object(access, 'request', side_effect=failure), self.assertRaises(access.HostRateLimitPause):
            access.robots_allowed('https://www.eff.org/article')

    def test_cooldown_expiring_during_stage_is_not_recorded_as_a_new_pause(self):
        record = item()
        plan = {'kind': 'known', 'source': {'url': record['url']}, 'publication_window': WINDOW,
                'host_backoff': {'www.econstor.eu': 10}}
        with patch.object(queue.time, 'monotonic', side_effect=[0, 20, 20]), \
             patch.object(access, 'retrieve', return_value=(None, [])) as fetch:
            result = queue.perform_stage(record, plan, 1)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.kwargs['host_backoff'], {'www.econstor.eu': 0})
        self.assertFalse(any(d['status'] == 'rate_limit_pause' for d in result['diagnostics']))

    def test_invalid_budgets_fail_before_fetch(self):
        for args in ({'limit': -1}, {'time_budget': 0}, {'max_candidates': 33}, {'item_time_budget': -1}):
            with self.assertRaisesRegex(ValueError, 'invalid_acquisition_budget'):
                run(weekly(item()), **args)


if __name__ == '__main__':
    unittest.main()

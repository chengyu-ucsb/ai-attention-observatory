"""Offline durable-query, rate-limit and strict-week recovery contracts."""
import datetime as dt
from email.utils import format_datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from academic_state import DiscoveryState, ProviderDeferred, cursor_search, retry_after
import update
import priority_research as pr

WINDOW = {'from': '2026-10-26', 'to': '2026-11-01'}
SCOPE = [('AI & cognition', 'AI cognitive offloading', *WINDOW.values(), 'previous_publication_week')]
PARAMS = {'query.bibliographic': 'AI cognitive offloading', 'filter': 'from-pub-date:2026-10-26,until-pub-date:2026-11-01'}


def work(n, day=(2026, 10, 29)):
    return {'DOI': f'10.1234/attention{n}', 'type': 'journal-article',
            'title': [f'Generative AI cognitive offloading {n}'],
            'container-title': ['Computers & Education'], 'published': {'date-parts': [list(day)]},
            'abstract': 'Generative AI and cognitive offloading affect critical thinking.'}


def oa(n):
    return {'id': f'https://openalex.org/W{n}', 'title': f'Generative AI cognitive offloading {n}',
            'doi': f'https://doi.org/10.1234/attention{n}', 'publication_date': '2026-10-29'}


def page(rows, total=None, cursor=None):
    value = {'items': rows}
    if total is not None: value['total-results'] = total
    if cursor is not None: value['next-cursor'] = cursor
    return {'message': value}


class FakeClock:
    def __init__(self): self.value = 1804500000.; self.sleeps = []
    def now(self): return self.value
    def sleep(self, seconds): self.sleeps.append(seconds); self.value += seconds


class StateFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.json'
        self.clock = FakeClock()

    def state(self, **kwargs):
        return DiscoveryState(self.path, window=WINDOW, now=self.clock.now, sleep=self.clock.sleep, **kwargs)


class ResumeTests(StateFixture, unittest.TestCase):
    def test_page_cap_persists_successor_and_replays_after_process_restart(self):
        seen = []
        def fetch(url):
            cursor = parse_qs(urlparse(url).query)['cursor'][0]; seen.append(cursor)
            return page([work(1)], 2, 'second') if cursor == '*' else page([work(2)], 2)
        rows, audit, _ = cursor_search(fetch, 'Crossref', PARAMS, state=self.state(), max_pages=1, page_size=1)
        self.assertEqual(audit['reason'], 'page budget reached')
        rows, audit, _ = cursor_search(fetch, 'Crossref', PARAMS, state=self.state(), max_pages=1, page_size=1)
        self.assertEqual(seen, ['*', 'second']); self.assertEqual(len(rows), 2)
        self.assertEqual(audit['status'], 'complete'); self.assertEqual(audit['cached_pages'], 1)
        rows, audit, _ = cursor_search(lambda _: self.fail('Completed search refetched'), 'Crossref', PARAMS, state=self.state(), page_size=1)
        self.assertEqual(len(rows), 2); self.assertEqual(audit['requests_this_run'], 0)

    def test_crash_after_durable_page_before_article_publication_loses_nothing(self):
        state = self.state()
        cursor_search(lambda _: page([work(1)], 2, 'second'), 'Crossref', PARAMS, state=state, max_pages=1, page_size=1)
        # A new process has no in-memory candidates, but can replay first page.
        rows, _, _ = cursor_search(lambda _: page([work(2)], 2), 'Crossref', PARAMS, state=self.state(), page_size=1)
        self.assertEqual({r['DOI'] for r in rows}, {'10.1234/attention1', '10.1234/attention2'})

    def test_failure_never_advances_uncommitted_cursor(self):
        state = self.state(); calls = []
        def fetch(url):
            cursor = parse_qs(urlparse(url).query)['cursor'][0]; calls.append(cursor)
            if cursor == 'second': raise TimeoutError()
            return page([work(1)], 2, 'second')
        rows, audit, errors = cursor_search(fetch, 'Crossref', PARAMS, state=state, page_size=1)
        self.assertEqual(len(rows), 1); self.assertTrue(errors)
        self.assertEqual(next(iter(state.current['queries'].values()))['cursor'], 'second')
        self.clock.sleep(5)
        rows, audit, _ = cursor_search(lambda url: (calls.append(parse_qs(urlparse(url).query)['cursor'][0]) or page([work(2)], 2)), 'Crossref', PARAMS, state=self.state(), page_size=1)
        self.assertEqual(calls, ['*', 'second', 'second']); self.assertEqual(len(rows), 2)

    def test_same_query_key_ignores_credentials_but_includes_page_size(self):
        state = self.state()
        first = state.query_id('OpenAlex', {'search': 'AI', 'api_key': 'first-secret'}, 100)
        self.assertEqual(first, state.query_id('OpenAlex', {'search': 'AI', 'api_key': 'rotated-secret'}, 100))
        self.assertNotEqual(first, state.query_id('OpenAlex', {'search': 'AI'}, 50))
        cursor_search(lambda _: {'results': [], 'meta': {'count': 0}}, 'OpenAlex', {'search': 'AI', 'api_key': 'secret-value'}, state=state)
        self.assertNotIn('secret-value', self.path.read_text()); self.assertNotIn('api_key', self.path.read_text())

    def test_query_drift_starts_new_cursor_and_retains_old_audit(self):
        state = self.state(); state.register_plan('general', [('Crossref', PARAMS, 1)])
        cursor_search(lambda _: page([work(1)], 2, 'second'), 'Crossref', PARAMS, state=state, max_pages=1, page_size=1)
        changed = dict(PARAMS, **{'query.bibliographic': 'AI attention'})
        state.register_plan('general', [('Crossref', changed, 1)])
        calls = []
        cursor_search(lambda u: (calls.append(parse_qs(urlparse(u).query)['cursor'][0]) or page([], 0)), 'Crossref', changed, state=state, page_size=1)
        self.assertEqual(calls, ['*']); self.assertEqual(state.summary()['superseded_queries'], 1)
        self.assertEqual(state.summary()['pending_queries'], 0); self.assertEqual(len(state.current['queries']), 2)

    def test_resume_only_never_starts_drifted_query(self):
        state = self.state(); state.register_plan('general', [('Crossref', PARAMS, 1)])
        changed = dict(PARAMS, **{'query.bibliographic': 'new topic'})
        resumed = self.state(resume_only=True); resumed.register_plan('general', [('Crossref', changed, 1)])
        _, audit, _ = cursor_search(lambda _: self.fail('New full sweep started'), 'Crossref', changed, state=resumed, page_size=1)
        self.assertEqual(audit['status'], 'deferred'); self.assertTrue(resumed.summary()['query_plan_drift'])

    def test_rollover_isolates_stale_pending_pages_and_preserves_cooldown(self):
        state = self.state(); state.register_plan('general', [('Crossref', PARAMS, 1)])
        cursor_search(lambda _: page([work(1)], 10, 'old-cursor'), 'Crossref', PARAMS, state=state, max_pages=1, page_size=1)
        state.data['providers']['Crossref'] = {'next_retry_at': self.clock.now() + 100, 'last_http_status': 429}; state.save()
        next_window = {'from': '2026-11-02', 'to': '2026-11-08'}
        newer = DiscoveryState(self.path, window=next_window, now=self.clock.now)
        self.assertFalse(newer.had_window); self.assertFalse(newer.current['queries'])
        self.assertEqual(newer.summary()['stale_windows'][0]['pending_queries'], 1)
        self.assertGreater(newer.data['providers']['Crossref']['next_retry_at'], self.clock.now())
        with self.assertRaises(ValueError): state.validate_window('weekly', next_window)

    def test_exact_repeated_articles_do_not_count_towards_provider_total(self):
        state = self.state(); count = 0
        def fetch(_):
            nonlocal count
            count += 1
            return page([work(1)], 2, 'cursor' + str(count))
        rows, audit, _ = cursor_search(fetch, 'Crossref', PARAMS, state=state, page_size=1, max_pages=2)
        self.assertEqual(len(rows), 1); self.assertEqual(audit['records_seen'], 2)
        self.assertEqual(audit['records_unique'], 1); self.assertEqual(audit['status'], 'truncated')

    def test_repeated_crossref_cursor_stops_even_if_metadata_changes(self):
        counter = 0
        def fetch(_):
            nonlocal counter
            counter += 1
            return page([work(counter)], 3, 'opaque')
        rows, audit, _ = cursor_search(fetch, 'Crossref', PARAMS, state=self.state(), page_size=1)
        self.assertEqual(len(rows), 2); self.assertEqual(audit['status'], 'truncated')
        self.assertEqual(audit['reason'], 'cursor did not advance to new records')

    def test_supported_provider_page_sizes(self):
        with self.assertRaises(ValueError):
            cursor_search(lambda _: self.fail('Unsupported OpenAlex request'), 'OpenAlex', {}, page_size=101)
        _, audit, _ = cursor_search(lambda _: page([], 0), 'Crossref', {}, page_size=1000)
        self.assertEqual(audit['status'], 'complete')

    def test_missing_or_inconsistent_pagination_is_partial_not_complete(self):
        examples = [page([work(1)], 10), page([], 10), page([work(1)], None, '*')]
        for index, response in enumerate(examples):
            with self.subTest(index=index):
                _, audit, _ = cursor_search(lambda _: response, 'Crossref', {'query.title': str(index)}, state=self.state(), page_size=100)
                self.assertNotEqual(audit['status'], 'complete')
        _, audit, _ = cursor_search(lambda _: page([work(1)]), 'Crossref', {'query.title': 'short'}, state=self.state(), page_size=100)
        self.assertEqual(audit['status'], 'complete')

    def test_malformed_second_page_keeps_first_page_and_cursor(self):
        state = self.state()
        cursor_search(lambda _: page([work(1)], 3, 'second'), 'Crossref', PARAMS, state=state, max_pages=1, page_size=1)
        rows, audit, errors = cursor_search(lambda _: page([None], 3, 'third'), 'Crossref', PARAMS, state=state, page_size=1)
        self.assertEqual(len(rows), 1); self.assertEqual(audit['pages'], 1); self.assertTrue(errors)
        self.assertEqual(next(iter(state.current['queries'].values()))['cursor'], 'second')

    def test_invalid_record_does_not_commit_part_of_page(self):
        state = self.state()
        malformed = work(2); malformed['author'] = 'not author objects'
        rows, audit, errors = cursor_search(lambda _: page([work(1), malformed], 2, 'third'), 'Crossref', PARAMS, state=state)
        self.assertFalse(rows); self.assertEqual(audit['pages'], 0); self.assertTrue(errors)
        self.assertEqual(next(iter(state.current['queries'].values()))['cursor'], '*')

    def test_corrupt_or_unsupported_checkpoint_fails_closed(self):
        for content in ('not JSON', '{"schema_version":99,"providers":{},"windows":{}}'):
            self.path.write_text(content)
            with self.assertRaises(ValueError): self.state()
            self.assertEqual(self.path.read_text(), content)

    def test_atomic_write_failure_does_not_replace_previous_checkpoint(self):
        state = self.state(); state.save(); before = self.path.read_text()
        state.data['providers']['Crossref'] = {'consecutive_failures': 1}
        with patch('academic_state.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): state.save()
        self.assertEqual(self.path.read_text(), before)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_zero_budget_retains_page_without_network(self):
        state = self.state()
        cursor_search(lambda _: page([work(1)], 10, 'second'), 'Crossref', PARAMS, state=state, max_pages=1, page_size=1)
        rows, audit, _ = cursor_search(lambda _: self.fail('Zero budget made request'), 'Crossref', PARAMS, state=self.state(), max_pages=0, page_size=1)
        self.assertEqual(len(rows), 1); self.assertEqual(audit['reason'], 'page budget is zero')


class RateLimitTests(StateFixture, unittest.TestCase):
    def test_retry_after_seconds_persisted_across_queries_and_processes(self):
        attempts = []
        def limited(url):
            attempts.append(url); raise HTTPError(url, 429, 'Slow down', {'Retry-After': '120'}, None)
        _, audit, _ = cursor_search(limited, 'Crossref', PARAMS, state=self.state())
        self.assertTrue(audit['quota_exhausted']); self.assertEqual(audit['retry_at'], self.clock.now() + 120)
        cursor_search(limited, 'Crossref', {'query.title': 'another'}, state=self.state())
        self.assertEqual(len(attempts), 1)
        self.clock.sleep(119)
        cursor_search(limited, 'Crossref', PARAMS, state=self.state())
        self.assertEqual(len(attempts), 1)
        self.clock.sleep(1)
        _, audit, _ = cursor_search(lambda _: page([], 0), 'Crossref', PARAMS, state=self.state())
        self.assertEqual(audit['status'], 'complete')

    def test_http_date_retry_after_and_bounded_inline_wait_are_honored(self):
        until = dt.datetime.fromtimestamp(self.clock.now() + 12, dt.timezone.utc)
        calls = []
        def fetch(url):
            calls.append(self.clock.now())
            if len(calls) == 1: raise HTTPError(url, 503, 'Busy', {'Retry-After': format_datetime(until, usegmt=True)}, None)
            return page([], 0)
        _, audit, errors = cursor_search(fetch, 'Crossref', PARAMS, state=self.state(max_inline_wait=12))
        self.assertEqual(calls[1] - calls[0], 12); self.assertEqual(self.clock.sleeps, [12])
        self.assertEqual(audit['status'], 'complete'); self.assertFalse(errors)

    def test_long_retry_after_is_not_clipped_to_inline_budget_or_backoff_cap(self):
        state = self.state(max_inline_wait=2)
        _, audit, _ = cursor_search(lambda u: (_ for _ in ()).throw(HTTPError(u, 429, 'Quota', {'Retry-After': '86400'}, None)), 'Crossref', PARAMS, state=state)
        self.assertEqual(audit['retry_at'], self.clock.now() + 86400)
        self.assertFalse(self.clock.sleeps)

    def test_missing_retry_after_uses_persisted_exponential_backoff(self):
        def fail(url): raise HTTPError(url, 503, 'Busy', {}, None)
        state = self.state()
        cursor_search(fail, 'Crossref', PARAMS, state=state)
        self.assertEqual(state.data['providers']['Crossref']['next_retry_at'], self.clock.now() + 5)
        self.clock.sleep(5)
        state = self.state(); cursor_search(fail, 'Crossref', PARAMS, state=state)
        self.assertEqual(state.data['providers']['Crossref']['next_retry_at'], self.clock.now() + 10)
        self.assertIsNone(retry_after('NaN', self.clock.now()))
        self.assertIsNone(retry_after('nonsense', self.clock.now()))

    def test_401_and_403_persist_stop_without_retry_or_alternate_route(self):
        for code in (401, 403):
            with self.subTest(code=code):
                provider = 'Crossref' if code == 401 else 'OpenAlex'
                state = self.state(max_inline_wait=100)
                calls = []
                def denied(url):
                    calls.append(url); raise HTTPError(url, code, 'Denied', {}, None)
                with self.assertRaises(HTTPError): state.fetch(provider, 'https://example.test', denied)
                self.clock.sleep(1000)
                with self.assertRaises(ProviderDeferred): self.state().fetch(provider, 'https://example.test', denied)
                self.assertEqual(len(calls), 1); self.assertTrue(all(value == 1000 for value in self.clock.sleeps))


class CollectionResumeTests(StateFixture, unittest.TestCase):
    def collect(self, state, fetch, *, today='2026-11-07', scopes=SCOPE, **kwargs):
        with patch.object(update, 'TODAY', today), patch.object(update, 'plan', return_value=scopes), patch.object(update, 'request', fetch), patch.object(update.time, 'sleep'):
            return update.discover(state=state, **kwargs)

    def test_lookup_budget_resumes_only_unverified_dois_without_researching(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if 'openalex.org/works?' in url: return {'results': [oa(1), oa(2)], 'meta': {'count': 2}}
            if '/works?' in url: return page([], 0)
            return {'message': work(1 if url.endswith('attention1') else 2)}
        rows, _, stats = self.collect(self.state(), fetch, max_date_lookups=1)
        self.assertEqual(len(rows), 1); self.assertEqual(stats['date_lookups_deferred'], 1)
        calls.clear()
        rows, _, stats = self.collect(self.state(resume_only=True), fetch, max_date_lookups=1)
        self.assertEqual(len(rows), 2); self.assertEqual(len(calls), 1); self.assertTrue(calls[0].endswith('attention2'))
        self.assertEqual(stats['configured_query_status'], 'complete_for_configured_queries')
        self.assertEqual(stats['queries_attempted'], 0)

    def test_resume_keeps_online_first_dates_outside_window_excluded(self):
        def fetch(url):
            if 'openalex.org/works?' in url: return {'results': [oa(1)], 'meta': {'count': 1}}
            if '/works?' in url: return page([], 0)
            old = work(1); old['published-online'] = {'date-parts': [[2025, 1, 1]]}
            return {'message': old}
        rows, _, _ = self.collect(self.state(), fetch)
        self.assertFalse(rows)
        rows, _, stats = self.collect(self.state(resume_only=True), lambda _: self.fail('Complete queries refetched'))
        self.assertFalse(rows); self.assertEqual(stats['publication_date_corrections']['10.1234/attention1'][0], '2025-01-01')

    def test_uncertain_crossref_original_day_is_quarantined_not_complete(self):
        uncertain = work(1); uncertain['published-online'] = {'date-parts': [[2026, 10]]}
        rows, _, stats = self.collect(self.state(), lambda url: {'results': [], 'meta': {'count': 0}} if 'openalex' in url else page([uncertain], 1))
        self.assertFalse(rows); self.assertEqual(stats['publication_date_unverified'], 1)
        self.assertEqual(stats['configured_query_status'], 'partial')
        self.assertEqual(stats['publication_date_quarantine'][0]['published'], '')

    def test_priority_queries_share_provider_pause_and_preserve_plan(self):
        state = self.state()
        cursor_search(lambda u: (_ for _ in ()).throw(HTTPError(u, 429, 'Quota', {'Retry-After': '60'}, None)), 'Crossref', PARAMS, state=state)
        manifest = {'venue_queries': [{'venue': 'Computers & Education', 'q': 'AI cognition', 'lane': 'AI & cognition'}]}
        rows, _, stats = pr.discover(lambda _: self.fail('Ignored provider cooldown'), dt.date(2026, 11, 7), manifest=manifest, state=state)
        self.assertFalse(rows); self.assertEqual(stats['journal_queries_attempted'], 0)
        self.assertEqual(stats['journal_queries_deferred'], 1); self.assertIn('journals', state.current['plans'])

    def test_main_initial_plan_then_resume_publishes_all_retained_articles_once(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if 'openalex' in url:
                cursor = parse_qs(urlparse(url).query)['cursor'][0]
                return {'results': [oa(1 if cursor == '*' else 2)], 'meta': {'count': 2, 'next_cursor': 'second' if cursor == '*' else None}}
            if '/works?' in url: return page([], 0)
            return {'message': work(1 if url.endswith('attention1') else 2)}
        env = {'MODE': 'weekly', 'ACADEMIC_MAX_PAGES': '1', 'ACADEMIC_PAGE_SIZE': '1'}
        with patch.object(update, 'DIR', self.path.parent), patch.object(update, 'TODAY', '2026-11-07'), patch.object(update, 'plan', return_value=SCOPE), patch.object(update, 'priority_manifest', return_value={'venue_queries': []}), patch.object(update, 'request', fetch), patch.object(update.time, 'sleep'), patch('builtins.print'), patch.dict('os.environ', env, clear=True):
            update.main()
            self.assertEqual(len(json.loads((self.path.parent / 'weekly.json').read_text())['items']), 1)
            calls.clear()
            with patch.dict('os.environ', {'DISCOVERY_RESUME_ONLY': '1'}): update.main()
            result = json.loads((self.path.parent / 'weekly.json').read_text())
            self.assertEqual(len(result['items']), 2)
            self.assertEqual(result['run']['stats']['configured_query_status'], 'complete_for_configured_queries')
            self.assertFalse(any('cursor=%2A' in url for url in calls))
            calls.clear()
            with patch.dict('os.environ', {'DISCOVERY_RESUME_ONLY': '1'}): update.main()
            self.assertFalse(calls)
            self.assertEqual(len(json.loads((self.path.parent / 'library.json').read_text())), 2)

    def test_main_resume_no_current_plan_is_read_only_noop(self):
        data = Path(self.tmp.name)
        (data / 'weekly.json').write_text('{"sentinel": true}')
        with patch.object(update, 'DIR', data), patch.object(update, 'TODAY', '2026-11-07'), patch.dict('os.environ', {'MODE': 'weekly', 'DISCOVERY_RESUME_ONLY': '1'}, clear=True), patch.object(update, 'request', side_effect=AssertionError('Unexpected network')), patch('builtins.print'):
            update.main()
        self.assertEqual((data / 'weekly.json').read_text(), '{"sentinel": true}')
        self.assertFalse((data / 'academic-discovery-state.json').exists())
        self.assertFalse((data / 'library.json').exists())

    def test_main_week_rollover_does_not_publish_stale_state(self):
        state = self.state(); state.register_plan('general', [('Crossref', PARAMS, 1)])
        cursor_search(lambda _: page([work(1)], 2, 'old'), 'Crossref', PARAMS, state=state, max_pages=1, page_size=1)
        before = self.path.read_text()
        with patch.object(update, 'DIR', self.path.parent), patch.object(update, 'TODAY', '2026-11-14'), patch.dict('os.environ', {'MODE': 'weekly', 'DISCOVERY_RESUME_ONLY': '1', 'ACADEMIC_DISCOVERY_STATE': str(self.path)}, clear=True), patch.object(update, 'request', side_effect=AssertionError('Unexpected old-window recovery')), patch('builtins.print'):
            update.main()
        self.assertEqual(self.path.read_text(), before); self.assertFalse((self.path.parent / 'weekly.json').exists())


if __name__ == '__main__': unittest.main()

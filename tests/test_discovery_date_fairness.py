"""Offline repeated-run scheduling, not evidence of live provider coverage."""
from collections import Counter
from copy import deepcopy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from academic_state import DiscoveryState
from academic_state_schema import validate_state
import search_plan
import update
import weekly_preparation as prep

NOW = dt.datetime(2026, 11, 9, 18, tzinfo=dt.timezone.utc)
WINDOW = {'from': '2026-11-02', 'to': '2026-11-08'}
FIRST = 'generative AI cognitive offloading critical thinking'
MANIFEST = {'venue_queries': [{'venue': 'Computers & Education', 'q': 'AI cognition', 'lane': 'AI & cognition'}]}


def rows(count=60, day='2026-11-03'):
    return [{'id': f'https://openalex.org/W{1000+i}', 'doi': f'https://doi.org/10.5555/audit-{i}',
             'title': f'Generative AI cognitive offloading and attention study {i}',
             'publication_date': day,
             'primary_location': {'source': {'display_name': 'Computers in Human Behavior'}}} for i in range(count)]


class DateFairnessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / 'data/academic-discovery-state.json'
        self.calls = []
        self.rows = rows()
        self.outcome = 404
        self.date_parts = [2026, 11, 3]
        self.daily = False
        self.first = FIRST
        self.network = patch('urllib.request.urlopen', side_effect=AssertionError('No live provider access'))
        self.network.start(); self.addCleanup(self.network.stop)
        sleep = patch('time.sleep'); sleep.start(); self.addCleanup(sleep.stop)

    def request(self, url):
        self.calls.append(url)
        parsed = urlsplit(url); query = parse_qs(parsed.query)
        if parsed.netloc == 'api.openalex.org':
            result = self.rows if query['search'][0] == self.first else []
            if self.daily and 'from_publication_date:2026-11-02,' not in query['filter'][0]: result = []
            return {'results': result, 'meta': {'count': len(result)}}
        if parsed.path == '/works':
            return {'message': {'items': [], 'total-results': 0}}
        if parsed.path.startswith('/works/'):
            if self.outcome:
                raise HTTPError(url, self.outcome, 'Unavailable', {'Retry-After': '200000'}, None)
            return {'message': {'DOI': unquote(parsed.path[len('/works/'):]),
                                'published-online': {'date-parts': [self.date_parts]}}}
        self.fail('Unexpected URL')

    def prepare(self, now=NOW, **kwargs):
        self.calls = []
        defaults = dict(closeout=True, closeout_pass='initial', feeds=[], academic_request=self.request,
                        max_requests=48, max_feed_requests=0)
        defaults.update(kwargs)
        packet = prep.prepare(self.root, now=now, **defaults)
        self.assertEqual(packet['coverage']['academic_requests_this_run'], len(self.calls))
        self.assertLessEqual(len(self.calls), defaults['max_requests'])
        return packet

    def checks(self):
        return [url for url in self.calls if '/works/' in url]

    def state(self):
        data = json.loads(self.path.read_text()); validate_state(data)
        return data

    def test_finite_404_page_advances_all_queries_and_each_doi_then_waits(self):
        request_counts = []; checked = []
        for n in range(5):
            packet = self.prepare()
            request_counts.append(len(self.calls)); checked.extend(self.checks())
            self.assertEqual(packet['coverage']['academic'][0]['checkpoint']['completed_queries'], 32)
            self.assertFalse(packet['items'])
            self.assertEqual(packet['status'], 'partial')
            self.assertFalse(self.state()['windows']['closeout:2026-11-02:2026-11-08']['date_evidence'])
            if n == 0:
                self.assertEqual(sum('query.container-title=' in u for u in self.calls), 8)
            else:
                self.assertTrue(all('/works/' in url for url in self.calls))
        self.assertEqual(request_counts, [48, 44, 0, 0, 0])
        self.assertEqual(len(set(checked)), 60)
        self.assertEqual(set(Counter(checked).values()), {1})
        self.assertEqual(len(self.state()['date_retries']), 60)
        before = self.state()
        self.prepare(now=NOW + dt.timedelta(minutes=59))
        self.assertEqual(self.calls, [])
        self.assertEqual(before, self.state())

    def test_due_failure_retries_rotate_and_healthy_recovery_never_replays_searches(self):
        self.prepare(); self.prepare()
        self.prepare(now=NOW + dt.timedelta(hours=1))
        first_retry = set(self.checks()); self.assertEqual(len(first_retry), 48)
        self.prepare(now=NOW + dt.timedelta(hours=1))
        self.assertEqual(len(self.checks()), 12)
        self.assertFalse(first_retry & set(self.checks()))
        self.outcome = None
        packet = self.prepare(now=NOW + dt.timedelta(hours=3))
        self.assertEqual(len(packet['items']), 48)
        packet = self.prepare(now=NOW + dt.timedelta(hours=3))
        self.assertEqual(len(packet['items']), 60)
        self.assertTrue(all('/works/' in u for u in self.calls))
        self.assertFalse(self.state()['date_retries'])
        self.prepare(now=NOW + dt.timedelta(hours=4))
        self.assertFalse(self.calls)

    def test_daily_slices_always_progress_despite_old_failed_dates(self):
        self.daily = True; self.rows = rows(day='2026-11-02')
        seen_checks = set()
        for day in range(2, 9):
            now = dt.datetime(2026, 11, day, 1, 29, tzinfo=dt.timezone.utc)
            packet = self.prepare(now=now, closeout=False, closeout_pass=None)
            self.assertTrue(all(r['checkpoint']['completed_queries'] == 32 for r in packet['coverage']['academic']))
            self.assertEqual(sum('query.container-title=' in u for u in self.calls), 8)
            searches = [u for u in self.calls if '/works/' not in u]
            self.assertEqual(len(searches), 32)
            self.assertTrue(all(f'2026-11-{day:02}' in u for u in searches))
            seen_checks.update(self.checks())
            self.assertFalse(packet['items'])
        self.assertEqual(len(seen_checks), 60)

    def test_failure_schedule_shared_with_fresh_closeout_namespace(self):
        self.prepare(); self.prepare()
        packet = self.prepare(closeout_pass='late_index')
        self.assertEqual(len(self.calls), 32)  # New query generation, no new DOI attempts.
        self.assertFalse(self.checks()); self.assertFalse(packet['items'])
        self.assertEqual(len(self.state()['date_retries']), 60)
        self.assertEqual(len(self.state()['windows']), 2)
        self.prepare(closeout_pass='late_index')
        self.assertFalse(self.calls)

    def test_one_request_budget_round_robins_slices_and_journals(self):
        self.first = 'AI cognitive offloading'; self.rows = []
        now = dt.datetime(2026, 11, 3, 1, 29, tzinfo=dt.timezone.utc)
        seen = []
        with patch.object(search_plan, 'LANES', {'AI & cognition': [self.first]}):
            for _ in range(6):
                packet = self.prepare(now=now, closeout=False, closeout_pass=None, max_requests=1, manifest=MANIFEST)
                self.assertEqual(len(self.calls), 1); seen.extend(self.calls)
            self.assertEqual(len(set(seen)), 6)
            self.assertTrue(all(r['checkpoint']['completed_queries'] == 3 for r in packet['coverage']['academic']))
            self.prepare(now=now, closeout=False, closeout_pass=None, max_requests=1, manifest=MANIFEST)
            self.assertFalse(self.calls)

    def test_advancing_daily_search_backlog_preserves_verification_turns(self):
        original = self.request
        self.outcome = None
        def paginated(url):
            parsed = urlsplit(url); query = parse_qs(parsed.query)
            if parsed.netloc == 'api.openalex.org':
                self.calls.append(url)
                day = query['filter'][0].split(',')[0].split(':')[1]
                page = 1 if query['cursor'][0] == '*' else int(query['cursor'][0])
                term = str(sum(map(ord, query['search'][0])))
                work = rows(1, day)[0]
                work['doi'] = f'https://doi.org/10.5555/{day}-{term}-{page}'
                return {'results': [work], 'meta': {'count': 100, 'next_cursor': str(page + 1)}}
            if parsed.path.startswith('/works/'):
                self.calls.append(url)
                doi = unquote(parsed.path[len('/works/'):])
                day = doi.split('/')[1][:10]
                return {'message': {'DOI': doi, 'published-online': {'date-parts': [list(map(int, day.split('-')))]}}}
            return original(url)
        admitted = 0
        for day in range(2, 6):
            now = dt.datetime(2026, 11, day, 1, 29, tzinfo=dt.timezone.utc)
            packet = self.prepare(now=now, closeout=False, closeout_pass=None, page_size=1,
                                  academic_request=paginated)
            self.assertGreaterEqual(len(self.checks()), 8)
            self.assertLessEqual(len(self.calls) - len(self.checks()), 40)
            self.assertGreater(len(packet['items']), admitted)
            self.assertTrue(any(row['published'] == now.date().isoformat() for row in packet['items']))
            admitted = len(packet['items'])

    def test_failed_search_head_cannot_starve_unattempted_queries(self):
        self.first = 'AI cognitive offloading'; self.rows = []
        original = self.request
        def unavailable(url):
            if 'api.openalex.org' in url:
                self.calls.append(url); raise HTTPError(url, 404, 'Missing', {}, None)
            return original(url)
        with patch.object(search_plan, 'LANES', {'AI & cognition': [self.first]}):
            for _ in range(3):
                packet = self.prepare(max_requests=1, manifest=MANIFEST, academic_request=unavailable)
            checkpoint = packet['coverage']['academic'][0]['checkpoint']
            self.assertEqual(checkpoint['completed_queries'], 2)
            self.assertEqual(checkpoint['pending_queries'], 1)
            saved = next(iter(self.state()['windows'].values()))['queries']
            self.assertEqual(sorted(q.get('attempts', 0) for q in saved.values()), [1, 1, 1])

    def test_new_week_queries_start_fresh_without_resetting_retry_ledger(self):
        self.prepare(); self.prepare()
        retries = deepcopy(self.state()['date_retries'])
        packet = self.prepare(now=NOW + dt.timedelta(days=7))
        self.assertEqual(len(self.calls), 32)
        self.assertFalse(self.checks()); self.assertFalse(packet['items'])
        self.assertEqual(self.state()['date_retries'], retries)
        self.assertIn('closeout:2026-11-09:2026-11-15', self.state()['windows'])

    def test_429_and_403_date_failures_preserve_provider_pause_across_namespaces(self):
        for code in (429, 403):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp); self.path = self.root / 'data/academic-discovery-state.json'
                self.outcome = code
                self.prepare()
                self.assertEqual(len(self.checks()), 1)
                provider = deepcopy(self.state()['providers']['Crossref'])
                self.prepare(closeout_pass='late_index')
                self.assertTrue(all('api.openalex.org' in url for url in self.calls))
                self.assertEqual(provider, self.state()['providers']['Crossref'])
                self.assertEqual(len(self.state()['date_retries']), 1)
                self.assertTrue(all(not w['date_evidence'] for w in self.state()['windows'].values()))

    def test_budget_deferral_is_not_a_failed_attempt_and_zero_budget_sends_no_requests(self):
        self.prepare(max_requests=1)
        self.assertFalse(self.state().get('date_retries'))
        before = deepcopy(self.state()['providers'])
        self.prepare(max_requests=0)
        self.assertFalse(self.calls)
        self.assertEqual(before, self.state()['providers'])
        self.assertFalse(self.state().get('date_retries'))

    def test_imprecise_or_out_of_window_publication_never_becomes_eligible(self):
        for parts in ([2026, 11], [2026, 8, 1], [2026, 11, 8]):
            with self.subTest(parts=parts), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp); self.path = self.root / 'data/academic-discovery-state.json'
                self.rows = rows(1); self.outcome = None; self.date_parts = parts
                packet = self.prepare()
                # A later Crossref day conflicts with the earlier OA day.
                self.assertFalse(packet['items'])
                packet = self.prepare(now=NOW + dt.timedelta(days=1))
                self.assertFalse(packet['items']); self.assertFalse(self.calls)
                self.assertFalse(self.state()['date_retries'])

    def test_arxiv_failure_backoff_retains_first_version_and_title_gates(self):
        self.rows = rows(1); self.rows[0]['doi'] = 'https://doi.org/10.48550/arxiv.2611.12345'
        atom_calls = []
        def atom(url):
            atom_calls.append(url); self.calls.append(url)
            return b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2611.12345v2</id><published>2026-11-03</published><title>Wrong title</title></entry></feed>'
        with patch.object(update, 'fetch_atom', atom):
            packet = self.prepare(); self.assertFalse(packet['items'])
            self.assertEqual(len(atom_calls), 1)
            self.assertTrue(atom_calls[0].endswith('2611.12345v1'))
            self.prepare(); self.assertEqual(len(atom_calls), 1)
            self.prepare(now=NOW + dt.timedelta(hours=1)); self.assertEqual(len(atom_calls), 2)
        self.assertFalse(self.state()['windows']['closeout:2026-11-02:2026-11-08']['date_evidence'])


class RetryLedgerTests(unittest.TestCase):
    def test_old_schema_remains_valid_and_retry_fields_are_not_date_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            state = DiscoveryState(path, window=WINDOW, now=lambda: NOW.timestamp())
            state.save(); self.assertNotIn('date_retries', state.data)
            state.record_date_retry('Crossref', '10.5555/missing', unavailable=True)
            loaded = DiscoveryState(path, window=WINDOW, now=lambda: NOW.timestamp())
            self.assertFalse(loaded.date_retry_due('Crossref', '10.5555/missing'))
            self.assertFalse(loaded.current['date_evidence'])
            valid = deepcopy(loaded.data)
            for field, value in [('value', '2026-11-03'), ('next_retry_at', True), ('attempts', 0),
                                 ('outcome', 'day_known'), ('provider', 'unknown'), ('provider', {}),
                                 ('next_retry_at', NOW.timestamp() + 99999999)]:
                broken = deepcopy(valid); next(iter(broken['date_retries'].values()))[field] = value
                with self.subTest(field=field), self.assertRaises(ValueError): validate_state(broken)

    def test_capacity_eviction_cannot_starve_untracked_candidates(self):
        state = DiscoveryState(window=WINDOW, now=lambda: NOW.timestamp())
        identities = [f'10.5555/{n}' for n in range(8)]
        seen = []
        with patch('academic_state.MAX_DATE_RETRIES', 2):
            for _ in range(16):
                due = [doi for doi in identities if state.date_retry_due('Crossref', doi)]
                selected = min(due, key=lambda doi: state.date_retry_order('Crossref', doi))
                seen.append(selected)
                state.record_date_retry('Crossref', selected, unavailable=True)
                self.assertLessEqual(len(state.data['date_retries']), 2)
        self.assertEqual(len(set(seen[:8])), 8)
        # Entries still retained in the two-slot ledger correctly stay asleep;
        # eviction must not keep any original candidate from its first turn.
        self.assertEqual(set(seen), set(identities))

    def test_retry_ledger_has_bounded_entries_age_attempts_and_backoff(self):
        now = [NOW.timestamp()]
        state = DiscoveryState(window=WINDOW, now=lambda: now[0])
        with patch('academic_state.MAX_DATE_RETRIES', 2):
            for n in range(3):
                state.record_date_retry('Crossref', f'10.5555/{n}', unavailable=True); now[0] += 1
            self.assertEqual(len(state.data['date_retries']), 2)
            for _ in range(40): state.record_date_retry('Crossref', '10.5555/2', unavailable=True)
            retry = state.data['date_retries'][state.date_retry_key('Crossref', '10.5555/2')]
            self.assertEqual(retry['attempts'], 32)
            self.assertEqual(retry['next_retry_at'] - now[0], 7 * 86400)
            now[0] += 91 * 86400
            state.record_date_retry('Crossref', '10.5555/new', unavailable=True)
            self.assertEqual(len(state.data['date_retries']), 1)
            state.record_date_retry('Crossref', '10.5555/new', resolved=True)
            self.assertFalse(state.data['date_retries'])


if __name__ == '__main__': unittest.main()

"""Offline rolling preparation, post-Sunday reconciliation and isolation tests."""
from copy import deepcopy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from academic_state import DiscoveryState, cursor_search
import search_plan
import update
import weekly_preparation as prep

SAT = dt.datetime(2026, 11, 7, 15, tzinfo=dt.timezone.utc)
MON = dt.datetime(2026, 11, 9, 0, 10, tzinfo=dt.timezone.utc)
WINDOW = {'from': '2026-11-02', 'to': '2026-11-08', 'timezone': 'UTC'}
FEED = {'id': 'one', 'name': 'Example', 'url': 'https://example.org/feed',
        'article_hosts': ['example.org'], 'source_type': 'journalism'}


def crossref(doi='10.1234/early', date=(2026, 11, 7)):
    return {'DOI': doi, 'type': 'journal-article',
        'title': ['Generative AI and cognitive offloading ' + doi],
        'container-title': ['Computers & Education'],
        'published': {'date-parts': [list(date)]},
        'abstract': 'Generative AI and cognitive offloading affect critical thinking.'}


def feed(day='2026-11-07', slug='early'):
    return ET.fromstring(f'<rss><channel><item><title>AI and human attention in learning</title>'
        f'<link>https://example.org/{slug}</link><pubDate>{day}</pubDate>'
        '<description>AI attention and cognitive learning</description></item></channel></rss>')


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'data').mkdir()
        self.lanes = patch.object(search_plan, 'LANES', {'AI & cognition': ['AI cognitive offloading']})
        self.lanes.start(); self.addCleanup(self.lanes.stop)
        self.sleeps = patch.object(update.time, 'sleep')
        self.sleeps.start(); self.addCleanup(self.sleeps.stop)
        self.calls = []
        self.works = [crossref()]
        self.bad_provider = None
        self.code = 429

    def fetch(self, url):
        self.calls.append(url)
        provider = 'OpenAlex' if 'api.openalex.org' in url else 'Crossref'
        if provider == self.bad_provider:
            raise HTTPError(url, self.code, 'blocked', {'Retry-After': '200000'}, None)
        if provider == 'OpenAlex':
            return {'results': [], 'meta': {'count': 0}}
        args = parse_qs(urlsplit(url).query)
        if 'filter' in args:
            filt = args['filter'][0]
            start, end = [value.split(':', 1)[1] for value in filt.split(',')]
            rows = [r for r in self.works if len(r['published']['date-parts'][0]) != 3
                    or start <= '-'.join(str(v).zfill(2 if i else 4) for i, v in enumerate(r['published']['date-parts'][0])) <= end]
        else:
            rows = self.works
        return {'message': {'items': rows, 'total-results': len(rows)}}

    def prepare(self, now=SAT, **kwargs):
        defaults = {'feeds': [], 'manifest': {'papers': [], 'venue_queries': []},
                    'academic_request': self.fetch, 'max_requests': 100, 'max_feed_requests': 0}
        defaults.update(kwargs)
        return prep.prepare(self.root, now=now, **defaults)

    def test_preparation_is_private_actual_observation_and_completed_queries_replay(self):
        protected = {'library.json': '[{"published":"2020-01-01"}]', 'weekly.json': '{"published":"unchanged"}',
            'issue-editorial.json': '{"approved":"unchanged"}', 'readings.json': '[]'}
        for name, value in protected.items():
            (self.root / 'data' / name).write_text(value)
        packet = self.prepare()
        self.assertEqual(packet['target_publication_window'], WINDOW)
        self.assertEqual(packet['run']['date'], '2026-11-07')
        self.assertEqual(packet['observation_at'], SAT.isoformat())
        self.assertEqual(packet['phase'], 'preparing')
        self.assertFalse(packet['public_eligible'])
        self.assertFalse(packet['source_checked']); self.assertFalse(packet['approved'])
        self.assertEqual([r['published'] for r in packet['items']], ['2026-11-07'])
        self.assertEqual(packet['items'][0]['first_seen'], '2026-11-07')
        self.assertEqual(packet['items'][0]['metadata_observed_at'], SAT.isoformat())
        calls = len(self.calls)
        later = self.prepare(now=SAT + dt.timedelta(hours=2))
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(later['items'][0]['metadata_observed_at'], SAT.isoformat())
        self.assertEqual(later['coverage']['academic_requests_this_run'], 0)
        for name, value in protected.items():
            self.assertEqual((self.root / 'data' / name).read_text(), value)
        self.assertEqual(len(list((self.root / 'data' / 'weekly-preparation' / WINDOW['from'] / 'snapshots').glob('*.json'))), 2)
        with self.assertRaisesRegex(ValueError, 'post-Sunday'):
            prep.closed_packet(packet, SAT)

    def test_fresh_closeout_includes_late_sunday_and_delayed_earlier_indexing(self):
        early = self.prepare()
        self.works.extend([crossref('10.1234/sunday', (2026, 11, 8)),
                           crossref('10.1234/delayed', (2026, 11, 3))])
        before = len(self.calls)
        packet = self.prepare(now=MON, closeout=True)
        self.assertEqual(packet['phase'], 'closed')
        self.assertEqual(len(packet['items']), 3)
        new_calls = self.calls[before:]
        self.assertEqual(len(new_calls), 2)
        for url in new_calls:
            args = parse_qs(urlsplit(url).query)
            self.assertEqual(args['cursor'], ['*'])
            self.assertIn('2026-11-02', args['filter'][0])
            self.assertIn('2026-11-08', args['filter'][0])
        exported = prep.closed_packet(packet, MON)
        self.assertEqual(exported['run']['date'], '2026-11-09')
        self.assertEqual(exported['run']['publication_window']['to'], '2026-11-08')
        self.assertEqual({r['doi'] for r in exported['items']}, {r['doi'] for r in packet['items']})
        calls = len(self.calls)
        self.prepare(now=MON + dt.timedelta(hours=1), closeout=True)
        self.assertEqual(len(self.calls), calls)
        state = json.loads((self.root / 'data' / 'academic-discovery-state.json').read_text())
        self.assertIn('preparation:2026-11-07:2026-11-07', state['windows'])
        self.assertIn('closeout:2026-11-02:2026-11-08', state['windows'])
        self.assertEqual(early['items'][0]['first_seen'], packet['items'][1]['first_seen'])

    def test_real_clock_rejects_open_packet_as_closed_or_future_and_never_overrides_weekly(self):
        packet = self.prepare()
        for mutate in [lambda p: p.update(observation_at=MON.isoformat()),
                       lambda p: p.update(phase='closed'),
                       lambda p: p.update(approved=True),
                       lambda p: p['items'][0].update(published='2026-11-08')]:
            bad = deepcopy(packet); mutate(bad)
            with self.assertRaises(ValueError):
                prep.validate_packet(bad, SAT)
        with self.assertRaises(ValueError):
            prep.validate_packet(packet, MON)
        with self.assertRaisesRegex(ValueError, 'cannot be overridden'):
            update.discover(observed_on=SAT, publication_window=WINDOW, metadata_request=self.fetch)
        self.assertEqual(search_plan.plan(SAT)[0][2:4], ('2026-10-26', '2026-11-01'))

    def test_unknown_date_and_earlier_correction_never_promoted_by_first_seen(self):
        self.works.append(crossref('10.1234/unknown', (2026, 11)))
        packet = self.prepare()
        self.assertEqual(packet['status'], 'partial')
        self.assertTrue(any(r.get('doi') == '10.1234/unknown' for r in packet['quarantine']))
        self.works[0] = crossref(date=(2026, 10, 30))
        # Provider can return out-of-window correction metadata; the production
        # collector records its date evidence but does not admit it.
        def correction(url):
            if 'crossref' in url:
                self.calls.append(url)
                return {'message': {'items': self.works, 'total-results': len(self.works)}}
            return self.fetch(url)
        packet = self.prepare(now=MON, closeout=True, academic_request=correction)
        self.assertEqual(packet['items'], [])
        self.assertTrue(any(r.get('doi') == '10.1234/early' and r['published'] == '2026-10-30'
                            for r in packet['quarantine']))
        self.assertTrue(any(r.get('doi') == '10.1234/unknown' for r in packet['quarantine']))

    def test_preparation_cannot_reset_normal_weekly_queries_or_provider_pause(self):
        state_path = self.root / 'data' / 'academic-discovery-state.json'
        weekly = DiscoveryState(state_path, window={'from': '2026-10-26', 'to': '2026-11-01'}, now=lambda: SAT.timestamp())
        cursor_search(self.fetch, 'OpenAlex', {'search': 'existing'}, state=weekly)
        previous = deepcopy(weekly.current)
        weekly.data['providers']['Crossref'] = {'next_retry_at': SAT.timestamp() + 200000,
            'consecutive_failures': 2, 'last_http_status': 429, 'reason': 'HTTP 429'}
        weekly.save(); self.calls.clear()
        packet = self.prepare()
        state = json.loads(state_path.read_text())
        self.assertEqual(state['windows'][weekly.window_id], previous)
        self.assertEqual(state['providers']['Crossref']['next_retry_at'], SAT.timestamp() + 200000)
        self.assertFalse(any('crossref' in u for u in self.calls))
        self.assertEqual(packet['status'], 'partial')

    def test_preparation_quota_and_denial_apply_to_closeout_and_normal_discovery(self):
        for code in (429, 403):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temp:
                self.root = Path(temp); (self.root / 'data').mkdir()
                self.bad_provider = 'Crossref'; self.code = code; self.calls.clear()
                self.prepare()
                self.assertEqual(sum('crossref' in u for u in self.calls), 1)
                self.calls.clear()
                self.prepare(now=MON, closeout=True)
                self.assertFalse(any('crossref' in u for u in self.calls))
                state = DiscoveryState(self.root / 'data' / 'academic-discovery-state.json',
                    window={'from': '2026-11-02', 'to': '2026-11-08'}, now=lambda: MON.timestamp())
                _, audit, _ = cursor_search(self.fetch, 'Crossref', {}, state=state)
                self.assertTrue(audit['provider_paused'])
                self.assertFalse(any('crossref' in u for u in self.calls))

    def test_global_request_budget_resumes_without_duplicate_completed_searches(self):
        first = self.prepare(max_requests=1)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(first['coverage']['academic_requests_this_run'], 1)
        self.assertEqual(first['status'], 'partial')
        prior = self.calls[0]
        second = self.prepare(now=SAT + dt.timedelta(hours=1), max_requests=2)
        self.assertEqual(second['coverage']['academic_requests_this_run'], 2)
        self.assertEqual(self.calls.count(prior), 1)

    def test_publisher_snapshots_preserve_sunday_and_missing_day_quarantine(self):
        self.works = []
        packet = self.prepare(feeds=[FEED], max_feed_requests=1, feed_fetcher=lambda _: feed())
        self.assertEqual(len(packet['items']), 1)
        packet = self.prepare(now=SAT + dt.timedelta(hours=1), feeds=[FEED], max_feed_requests=1,
            feed_fetcher=lambda _: feed('', 'unknown'))
        self.assertTrue(any(r.get('status') == 'original_publication_date_missing' for r in packet['quarantine']))
        packet = self.prepare(now=MON, closeout=True, feeds=[FEED], max_feed_requests=1,
            feed_fetcher=lambda _: feed('2026-11-08', 'sunday'))
        self.assertEqual({r['published'] for r in packet['items']}, {'2026-11-07', '2026-11-08'})
        self.assertTrue(any(r.get('status') == 'original_publication_date_missing' for r in packet['quarantine']))
        self.assertEqual(packet['status'], 'partial')

    def test_publisher_denial_persists_across_preparation_and_closeout(self):
        calls = []
        def denied(url):
            calls.append(url)
            raise HTTPError(url, 403, 'denied', {}, None)
        self.prepare(feeds=[FEED], max_feed_requests=1, feed_fetcher=denied)
        self.prepare(now=MON, closeout=True, feeds=[FEED], max_feed_requests=1, feed_fetcher=denied)
        self.assertEqual(calls, [FEED['url']])

    def test_closed_adoption_preserves_readings_and_approval_and_strict_date_gate(self):
        packet = self.prepare(now=MON, closeout=True)
        old = deepcopy(packet['items'][0])
        old.update(reading={'overview': 'An existing approved body', 'level': 'abstract'},
                   approved=True, first_seen='2026-11-07', source_checked='2026-11-07')
        old['abstract_text'] = ''
        original = deepcopy(old)
        result = prep.adopt_closed_packet(packet, [old], MON)
        self.assertEqual(old, original)  # Pure function.
        updated = result['library'][0]
        for field in ('reading', 'approved', 'source_checked', 'first_seen'):
            self.assertEqual(updated[field], old[field])
        self.assertTrue(updated['abstract_text'])
        self.assertEqual(result['weekly']['run']['date'], '2026-11-09')
        self.assertEqual(result['weekly']['items'][0]['published'], '2026-11-07')
        correction = ['2026-10-30', {'status': 'day_known', 'source': 'Crossref publisher metadata',
            'field': 'published-online', 'value': '2026-10-30'}]
        packet['coverage']['publication_date_corrections'][old['doi']] = correction
        corrected = prep.adopt_closed_packet(packet, [old], MON)
        self.assertFalse(corrected['weekly']['items'])
        self.assertEqual(corrected['library'][0]['published'], '2026-10-30')
        with self.assertRaises(ValueError):
            prep.adopt_closed_packet(self.prepare(), [old], SAT)

    def test_closeout_checkpoint_adoption_avoids_duplicate_searches_and_never_overwrites(self):
        self.prepare(now=MON, closeout=True)
        path = self.root / 'data' / 'academic-discovery-state.json'
        before = json.loads(path.read_text())
        result = prep.adopt_closeout_checkpoint(path, MON)
        self.assertTrue(result['adopted'])
        after = json.loads(path.read_text())
        self.assertEqual(after['providers'], before['providers'])
        for ident in before['windows']:
            self.assertEqual(after['windows'][ident], before['windows'][ident])
        self.calls.clear()
        state = DiscoveryState(path, window={'from': WINDOW['from'], 'to': WINDOW['to']})
        rows, _, _ = update.discover(state=state, observed_on=MON, metadata_request=self.fetch)
        self.assertEqual(len(rows), 1)
        self.assertFalse(self.calls)
        saved = path.read_text()
        result = prep.adopt_closeout_checkpoint(path, MON)
        self.assertFalse(result['adopted'])
        self.assertEqual(path.read_text(), saved)

    def test_partial_closeout_cannot_seed_normal_weekly_cursor(self):
        packet = self.prepare(now=MON, closeout=True, max_requests=1)
        result = prep.adopt_closeout_checkpoint(self.root / 'data' / 'academic-discovery-state.json', MON)
        self.assertFalse(result['adopted'])
        self.assertEqual(result['status'], 'partial_closeout_resume_required')
        self.assertEqual(packet['status'], 'partial')
        self.assertEqual(prep.closed_packet(packet, MON)['run']['stats']['discovery_status'], 'partial')

    def test_one_named_late_index_generation_finds_monday_indexed_sunday_article(self):
        first = self.prepare(now=MON, closeout=True)
        self.works.append(crossref('10.1234/indexed-monday-morning', (2026, 11, 8)))
        calls = len(self.calls)
        with self.assertRaisesRegex(ValueError, 'Monday 06:00'):
            self.prepare(now=MON + dt.timedelta(hours=1), closeout=True, closeout_pass='late_index')
        self.assertEqual(len(self.calls), calls)
        later = MON + dt.timedelta(hours=6)
        packet = self.prepare(now=later, closeout=True, closeout_pass='late_index')
        self.assertEqual(len(packet['items']), 2)
        self.assertEqual(len(self.calls), calls + 2)
        self.assertEqual(packet['coverage']['closeout_pass'], 'late_index')
        self.assertEqual(packet['coverage']['closeout_started_at'], first['coverage']['closeout_started_at'])
        calls = len(self.calls)
        self.prepare(now=later + dt.timedelta(hours=1), closeout=True)
        self.assertEqual(len(self.calls), calls)
        with self.assertRaisesRegex(ValueError, 'do not regress'):
            self.prepare(now=later + dt.timedelta(hours=1), closeout=True, closeout_pass='initial')
        state = json.loads((self.root / 'data' / 'academic-discovery-state.json').read_text())
        self.assertIn('closeout_late_index:2026-11-02:2026-11-08', state['windows'])

    def test_metadata_adoption_cannot_smuggle_staged_reviews_bodies_or_approval(self):
        packet = self.prepare(now=MON, closeout=True)
        injected = {'source_review': {'approved': True, 'body': 'private full text'},
                    'deep_analysis': {'body': 'private full text'},
                    'reading_coverage': {'document_complete': True}, 'approved': True,
                    'source_checked': '2026-11-09', 'curated': True,
                    'reading': {'level': 'full_text', 'overview': 'private full text'},
                    'full_text': 'private full text', 'source_body': 'private full text',
                    'original_reading_sha256': 'forged'}
        # Persisted staging is a closed metadata schema. Source-bearing fields
        # fail validation before checkpoint copy or canonical adoption.
        for key, value in {**injected, 'original_reading': {'approved': True}}.items():
            bad = deepcopy(packet); bad['items'][0][key] = value
            with self.assertRaises(ValueError):
                prep.adopt_closed_packet(bad, [], MON)
        pending = deepcopy(packet['items'][0]); pending.update(doi='10.1234/uncertain', published='')
        pending['publication_date_provenance'] = {'status': 'unresolved'}
        pending.update(injected)
        packet['quarantine'].append(pending)
        with self.assertRaises(ValueError):
            prep.adopt_closed_packet(packet, [], MON)

    def test_every_nested_packet_object_rejects_body_and_approval_keys(self):
        packet = self.prepare(feeds=[FEED], max_feed_requests=1, feed_fetcher=lambda _: feed())
        packet['quarantine'].append(prep.editorial.quarantine_item(
            {'title': 'AI and human attention uncertain date', 'url': 'https://example.org/unknown'},
            FEED, 'original_publication_date_missing'))
        prep.validate_packet(packet, SAT)
        paths = []
        def collect(value, path=()):
            if isinstance(value, dict):
                paths.append(path)
                for key, child in value.items():
                    collect(child, (*path, key))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    collect(child, (*path, index))
        collect(packet)
        self.assertGreater(len(paths), 50)
        for path in paths:
            for name, value in (('raw_source_body', 'UNLICENSED ARTICLE BODY SENTINEL'), ('approved', True)):
                with self.subTest(path=path, field=name):
                    bad = deepcopy(packet); target = bad
                    for key in path:
                        target = target[key]
                    target[name] = value
                    with self.assertRaisesRegex(ValueError, 'Invalid preparation metadata'):
                        prep.validate_packet(bad, SAT)

    def test_metadata_scalars_and_report_bounds_cannot_hide_nested_bodies(self):
        packet = self.prepare(feeds=[FEED], max_feed_requests=1, feed_fetcher=lambda _: feed())
        mutations = [
            lambda p: p['items'][0].update(title={'raw_source_body': 'PRIVATE'}),
            lambda p: p['items'][0].update(authors=[{'approved': True}]),
            lambda p: p['items'][0].update(abstract_text='X' * 6001),
            lambda p: p['coverage'].update(errors=[{'raw_source_body': 'PRIVATE'}]),
            lambda p: p['coverage']['academic'][0]['general']['provider_windows'][0].update(reason=['PRIVATE']),
            lambda p: p['coverage']['academic'][0]['general']['provider_windows'][0].update(status='approved'),
            lambda p: p['coverage']['publisher_snapshots'].update(requests=float('nan')),
            lambda p: p['coverage']['editorial'].update(full_articles_retrieved=1),
            lambda p: p['coverage']['editorial']['sources'][0].update(warnings=['X' * 161]),
            lambda p: p.update(metadata_sha256='a' * 64),
        ]
        for mutate in mutations:
            bad = deepcopy(packet); mutate(bad)
            with self.assertRaisesRegex(ValueError, 'Invalid preparation metadata'):
                prep.validate_packet(bad, SAT)
        bad = deepcopy(packet)
        nested = bad['items'][0]['publication_date_provenance']
        for _ in range(10):
            nested['earlier_publication_evidence'] = {}; nested = nested['earlier_publication_evidence']
        with self.assertRaisesRegex(ValueError, 'Invalid preparation metadata'):
            prep.validate_packet(bad, SAT)

    def test_poisoned_saved_packet_stops_before_requests_or_new_snapshots(self):
        packet = self.prepare()
        folder = self.root / 'data' / 'weekly-preparation' / WINDOW['from']
        before = {p.name: p.read_text() for p in (folder / 'snapshots').iterdir()}
        packet['raw_source_body'] = 'UNLICENSED ARTICLE BODY SENTINEL'
        raw = json.dumps(packet, sort_keys=True)
        (folder / 'packet.json').write_text(raw)
        calls = len(self.calls)
        with self.assertRaisesRegex(ValueError, 'Invalid preparation metadata'):
            self.prepare(now=SAT + dt.timedelta(hours=1))
        self.assertEqual(len(self.calls), calls)
        self.assertEqual({p.name: p.read_text() for p in (folder / 'snapshots').iterdir()}, before)
        self.assertEqual((folder / 'packet.json').read_text(), raw)
        # Neither a stale content filename nor a newly recomputed filename
        # changes the packet trust boundary used by snapshot/checkpoint readers.
        for name in ('unsealed.json', hashlib.sha256(raw.encode()).hexdigest() + '.json'):
            path = self.root / name; path.write_text(raw)
            with self.assertRaisesRegex(ValueError, 'Invalid preparation metadata'):
                prep.validate_packet(json.loads(path.read_text()), SAT)

    def test_generated_packet_and_snapshots_are_metadata_only(self):
        packet = self.prepare(feeds=[FEED], max_feed_requests=1, feed_fetcher=lambda _: feed())
        self.assertEqual({row['kind'] for row in packet['items']}, {'scholarly', 'nonacademic'})
        folder = self.root / 'data' / 'weekly-preparation' / WINDOW['from']
        for path in [folder / 'packet.json', *(folder / 'snapshots').iterdir()]:
            saved = json.loads(path.read_text())
            prep.validate_packet(saved, SAT)
            for row in saved['items']:
                self.assertLessEqual(set(row), prep.METADATA_FIELDS)
                self.assertNotIn('reading', row)
                self.assertNotIn('source_checked', row)
                self.assertNotIn('curated', row)

    def test_nonempty_journal_reports_and_missing_author_metadata_are_supported(self):
        packet = self.prepare(manifest={'papers': [], 'venue_queries': [{
            'q': 'generative AI cognitive offloading', 'venue': 'Computers & Education', 'lane': 'AI & cognition'}]})
        prep.validate_packet(packet, SAT)
        self.assertTrue(packet['coverage']['academic'][-1]['journals']['provider_windows'])
        candidate = deepcopy(packet['items'][0]); candidate['authors'] = [None, 'Known Author']
        self.assertEqual(prep.metadata_record(candidate)['authors'], ['Known Author'])
        candidate['authors'] = [{'source_body': 'PRIVATE'}]
        with self.assertRaises(ValueError):
            prep.metadata_record(candidate)

    def test_oversized_saved_packet_is_rejected_before_parse_or_requests(self):
        self.prepare()
        calls = len(self.calls)
        with patch.object(prep, 'MAX_PACKET_BYTES', 16), patch.object(prep, 'strict_json_loads') as parse:
            with self.assertRaisesRegex(ValueError, 'Invalid preparation metadata'):
                self.prepare(now=SAT + dt.timedelta(hours=1))
            parse.assert_not_called()
        self.assertEqual(len(self.calls), calls)

    def test_unknown_collector_report_data_cannot_be_saved(self):
        with patch.object(prep, 'discover_priority', return_value=([], [], {
                'discovery_status': 'complete', 'raw_source_body': 'UNLICENSED ARTICLE BODY SENTINEL'})):
            with self.assertRaisesRegex(ValueError, 'Invalid preparation metadata'):
                self.prepare()
        folder = self.root / 'data' / 'weekly-preparation' / WINDOW['from']
        self.assertFalse((folder / 'packet.json').exists())
        self.assertFalse((folder / 'snapshots').exists())

    def test_canonical_adoption_is_idempotent_and_never_writes_public_artifacts(self):
        packet = self.prepare(now=MON, closeout=True)
        protected = ['public-weekly.json', 'issue-editorial.json']
        for name in protected:
            (self.root / 'data' / name).write_text('protected')
        result = prep.adopt_to_canonical(self.root, packet, MON)
        self.assertEqual(result['weekly']['items'][0]['published'], '2026-11-07')
        again = prep.adopt_to_canonical(self.root, packet, MON)
        self.assertEqual(len(again['library']), 1)
        self.assertEqual(len(json.loads((self.root / 'data' / 'runs.json').read_text())), 1)
        for name in protected:
            self.assertEqual((self.root / 'data' / name).read_text(), 'protected')

    def test_unchanged_bound_provenance_preserves_checked_at_but_changes_invalidate(self):
        packet = self.prepare()
        path = self.root / 'data' / 'weekly-preparation' / WINDOW['from'] / 'packet.json'
        packet['items'][0]['publication_date_provenance']['checked_at'] = SAT.isoformat()
        prep.atomic_save(path, packet)
        refreshed = self.prepare(now=SAT + dt.timedelta(hours=1))
        self.assertEqual(refreshed['items'][0]['publication_date_provenance'], packet['items'][0]['publication_date_provenance'])
        self.assertNotEqual(refreshed['observation_at'], packet['observation_at'])
        old = {'x': deepcopy(packet['items'][0])}
        same = deepcopy(old); same['x']['publication_date_provenance']['checked_at'] = MON.isoformat()
        prep.preserve_unchanged_check_times(same, old)
        self.assertEqual(same, old)
        for field in ('value', 'basis', 'source', 'version'):
            changed = deepcopy(old)
            changed['x']['publication_date_provenance'].update(checked_at=MON.isoformat(), **{field: 'changed'})
            prep.preserve_unchanged_check_times(changed, old)
            self.assertEqual(changed['x']['publication_date_provenance']['checked_at'], MON.isoformat())

    def test_reading_and_acquisition_receipts_are_never_mutated(self):
        self.prepare()
        folder = self.root / 'data' / 'weekly-preparation' / WINDOW['from']
        names = ['readings.json', 'acquisition.json', 'review-status.json']
        for name in names:
            (folder / name).write_text('{"receipt":"must stay unchanged"}')
        self.prepare(now=MON, closeout=True)
        for name in names:
            self.assertEqual((folder / name).read_text(), '{"receipt":"must stay unchanged"}')


if __name__ == '__main__':
    unittest.main()

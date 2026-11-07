"""Provider-window, pagination and original-publication-date regressions."""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import priority_research as pr
import update
from arxiv_publication import ArxivPublicationVerifier

TODAY = '2026-11-07'
SCOPE = [('AI & cognition', 'AI cognitive offloading', '2026-10-26', '2026-11-01', 'previous_publication_week')]
DOI = '10.1234/attention'


def crossref(day=(2026, 10, 29), doi=DOI):
    return {'DOI': doi, 'type': 'journal-article', 'title': ['Generative AI and cognitive offloading'],
            'published': {'date-parts': [list(day)]}, 'container-title': ['Computers & Education'],
            'abstract': 'Generative AI and cognitive offloading affect critical thinking.'}


def openalex(day='2026-10-29', doi=DOI):
    return {'id': 'https://openalex.org/W123', 'title': 'Generative AI and cognitive offloading',
            'doi': 'https://doi.org/' + doi if doi else '', 'publication_date': day,
            'primary_location': {'source': {'display_name': 'Computers & Education'}}}


class PaginationTests(unittest.TestCase):
    def test_crossref_cursor_collects_all_pages(self):
        calls = []
        def fetch(url):
            params = parse_qs(urlparse(url).query); calls.append(params)
            return {'message': {'items': [crossref(doi='10.1234/' + str(len(calls)))],
                                'total-results': 3, 'next-cursor': str(len(calls))}}
        rows, audit, errors = pr.crossref_search(fetch, {'query.title': 'AI'}, max_pages=5, page_size=1)
        self.assertEqual(len(rows), 3)
        self.assertEqual([p['cursor'][0] for p in calls], ['*', '1', '2'])
        self.assertEqual(audit['status'], 'complete'); self.assertFalse(errors)
        self.assertFalse(any('mailto' in p for p in calls))

    def test_crossref_cap_is_explicit(self):
        rows, audit, errors = pr.crossref_search(lambda url: {'message': {'items': [crossref()], 'total-results': 50, 'next-cursor': 'next'}}, {}, max_pages=1, page_size=1)
        self.assertEqual(len(rows), 1); self.assertTrue(audit['truncated'])
        self.assertEqual(audit['reason'], 'page budget reached')

    def test_repeated_cursor_and_short_inconsistent_page_are_not_complete(self):
        for message in [{'items': [crossref()], 'total-results': 50, 'next-cursor': '*'},
                        {'items': [crossref()], 'total-results': 50}]:
            _, audit, _ = pr.crossref_search(lambda url: {'message': message}, {}, max_pages=3, page_size=100)
            self.assertEqual(audit['status'], 'truncated')

    def test_error_preserves_prior_page_and_marks_partial(self):
        count = 0
        def fetch(url):
            nonlocal count
            count += 1
            if count == 2: raise HTTPError(url, 429, 'Quota', None, None)
            return {'message': {'items': [crossref()], 'total-results': 10, 'next-cursor': 'next'}}
        rows, audit, errors = pr.crossref_search(fetch, {}, page_size=1)
        self.assertEqual(len(rows), 1); self.assertTrue(errors)
        self.assertEqual(audit['status'], 'error'); self.assertTrue(audit['quota_exhausted'])

    def test_openalex_cursor_collects_and_reports_cap(self):
        def fetch(url):
            cursor = parse_qs(urlparse(url).query)['cursor'][0]
            return {'results': [openalex()], 'meta': {'count': 3, 'next_cursor': '1' if cursor == '*' else '2'}}
        with patch.object(update, 'request', fetch):
            rows, audit, errors = update.openalex_search({}, max_pages=2, page_size=1)
        self.assertEqual(len(rows), 1); self.assertEqual(audit['pages'], 2); self.assertTrue(audit['truncated']); self.assertFalse(errors)


class AcademicCollectionTests(unittest.TestCase):
    def discover(self, oa, cr, direct=None, **kwargs):
        calls = []
        def fetch(url):
            calls.append(url)
            if 'api.openalex.org' in url: return {'results': oa, 'meta': {'count': len(oa)}}
            if '/works/10.' in url: return {'message': direct or crossref()}
            return {'message': {'items': cr, 'total-results': len(cr)}}
        with patch.object(update, 'TODAY', TODAY), patch.object(update, 'plan', return_value=SCOPE), patch.object(update, 'request', fetch), patch.object(update.time, 'sleep'):
            rows, errors, stats = update.discover(**kwargs)
        return rows, errors, stats, calls

    def test_provider_filters_and_client_side_gate_are_both_strict(self):
        rows, errors, stats, calls = self.discover([
            openalex('2026-11-02', doi='10.1234/current-week'),
            openalex('2026-10-25', doi='10.1234/older-week'),
            openalex('2026-10', doi='10.1234/partial')],
            [crossref((2026, 11, 2), doi='10.1234/current-week'),
             crossref((2026, 10), doi='10.1234/partial'), crossref()])
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['published'], '2026-10-29')
        self.assertTrue(all('news.google' not in u and 'mailto=' not in u for u in calls))
        self.assertTrue(all('2026-10-26' in u and '2026-11-01' in u for u in calls))
        self.assertGreaterEqual(stats['publication_date_rejected'], 5); self.assertFalse(errors)

    def test_online_first_outside_window_overrides_current_print(self):
        work = crossref(); work['published-online'] = {'date-parts': [[2025, 8, 1]]}
        rows, errors, stats, _ = self.discover([openalex()], [work])
        self.assertFalse(rows); self.assertFalse(errors)
        self.assertEqual(stats['publication_date_corrections'][DOI][0], '2025-08-01')

    def test_earlier_openalex_date_cannot_be_relabeled_as_crossref_original_evidence(self):
        rows, _, stats, _ = self.discover([openalex('2026-10-28')], [], direct=crossref((2026, 11, 2)))
        self.assertEqual(rows, [])
        self.assertEqual(stats['publication_date_unverified'], 1)
        pending = stats['publication_date_quarantine'][0]
        self.assertEqual(pending['published'], '')
        self.assertNotEqual(pending['publication_date_provenance'].get('status'), 'day_known')

    def test_same_week_disagreement_does_not_make_earlier_registry_index_day_authoritative(self):
        rows, _, stats, _ = self.discover([openalex('2026-10-28')], [], direct=crossref((2026, 10, 29)))
        self.assertEqual(rows, [])
        self.assertEqual(stats['publication_date_unverified'], 1)

    def test_cross_provider_conflict_quarantines_all_rows_and_existing_record_for_doi(self):
        rows, _, stats, _ = self.discover([openalex('2026-10-28')], [crossref((2026, 10, 29))])
        self.assertEqual(rows, [])
        self.assertEqual(stats['publication_date_unverified'], 1)
        old = {'title': 'Generative AI and cognitive offloading', 'doi': DOI,
               'url': 'https://doi.org/' + DOI, 'kind': 'scholarly', 'source': 'Crossref',
               'published': '2026-10-29', 'publication_date_provenance': {
                   'status': 'day_known', 'source': 'Crossref publisher metadata',
                   'field': 'published', 'value': '2026-10-29'}}
        library, week = self.run_main([old], rows, stats)
        self.assertEqual(week['items'], [])
        self.assertIn(library[0]['publication_date_provenance']['status'], ('conflict', 'unresolved'))

    def test_conflicting_crossref_query_rows_cannot_admit_newer_original_day(self):
        for dates in (((2026, 9, 1), (2026, 10, 29)), ((2026, 10, 29), (2026, 9, 1))):
            with self.subTest(dates=dates):
                candidates, _, stats, _ = self.discover([], [crossref(day) for day in dates])
                _, week = self.run_main([], candidates, stats)
                self.assertEqual(week['items'], [])

    def test_provider_conflict_survives_priority_import_and_later_metadata_refresh(self):
        priority = pr.crossref_article(crossref(), lane='AI & cognition', scope='venue_targeted',
            query='generative AI', today=dt.date.fromisoformat(TODAY), screen=False)
        priority_stats = {'publication_date_corrections': {
            DOI: (priority['published'], priority['publication_date_provenance'])}}
        for old in ([], [dict(priority)]):
            with self.subTest(existing=bool(old)):
                candidates, _, stats, _ = self.discover([openalex('2026-10-28')], [crossref()])
                library, week = self.run_main(old, candidates, stats,
                    priority=[dict(priority)], priority_stats=json.loads(json.dumps(priority_stats)))
                self.assertEqual(week['items'], [])
                evidence = library[0]['publication_date_provenance']
                self.assertTrue(evidence['requires_explicit_date_resolution'])
                self.assertIn(evidence['status'], ('conflict', 'unresolved'))
                # A later run lacking the disagreeing provider is not an adjudication.
                refreshed, later = self.run_main(library, [dict(priority)],
                    {'publication_date_corrections': {DOI: (priority['published'], priority['publication_date_provenance'])}},
                    priority=[dict(priority)], priority_stats=json.loads(json.dumps(priority_stats)))
                self.assertEqual(later['items'], [])
                self.assertEqual(refreshed[0]['publication_date_provenance'], evidence)

    def test_priority_only_repeated_dates_cannot_lose_earlier_original_event(self):
        manifest = {'papers': [], 'venue_queries': [
            {'venue': 'Computers & Education', 'lane': 'AI & cognition', 'q': 'generative AI'}]}
        for dates in (((2026, 9, 1), (2026, 10, 29)), ((2026, 10, 29), (2026, 9, 1))):
            with self.subTest(dates=dates):
                works = [crossref(day) for day in dates]
                priority, errors, stats = pr.discover(
                    lambda url: {'message': {'items': works, 'total-results': len(works)}},
                    dt.date.fromisoformat(TODAY), manifest=manifest)
                self.assertEqual(errors, [])
                _, week = self.run_main([], [], priority=priority, priority_stats=stats)
                self.assertEqual(week['items'], [])

    def test_openalex_doi_date_is_verified_once_then_shared_between_queries(self):
        work = crossref(); work['published-online'] = {'date-parts': [[2026, 10, 27]]}
        rows, errors, stats, calls = self.discover([openalex(), openalex()], [], direct=work)
        self.assertEqual(len(rows), 1)  # Duplicate provider/query rows are one article.
        self.assertTrue(all(r['published'] == '2026-10-27' for r in rows))
        self.assertEqual(sum('/works/10.' in u for u in calls), 1)
        self.assertFalse(errors)

    def test_missing_original_day_does_not_use_indexed_date(self):
        work = crossref((2026, 10)); work['indexed'] = {'date-parts': [[2026, 10, 29]]}
        rows, _, _, _ = self.discover([openalex()], [], direct=work)
        self.assertFalse(rows)

    def test_lookup_budget_is_visible_and_does_not_admit_unverified_print_date(self):
        rows, errors, stats, _ = self.discover([openalex()], [], max_date_lookups=0)
        self.assertFalse(rows); self.assertEqual(stats['date_lookups_deferred'], 1)
        self.assertEqual(stats['discovery_status'], 'partial')

    def test_non_doi_openalex_date_is_quarantined_and_counted(self):
        rows, errors, stats, _ = self.discover([openalex(doi='')], [])
        self.assertFalse(rows); self.assertFalse(errors)
        self.assertEqual(stats['publication_date_unverified'], 1)
        self.assertEqual(stats['discovery_status'], 'partial')
        pending = stats['publication_date_quarantine'][0]
        self.assertEqual(pending['published'], '')
        self.assertEqual(pending['publication_date_provenance']['provider_publication_date'], '2026-10-29')
        library, week = self.run_main([], [], stats)
        self.assertEqual(len(library), 1); self.assertFalse(week['items'])
        self.assertEqual(week['run']['stats']['publication_date_quarantine_records'], 1)

    def test_newer_registry_event_keeps_earlier_verified_date_provenance(self):
        row = dict(kind='scholarly', published='2025-05-01', publication_date_provenance={
            'status': 'day_known', 'source': 'Crossref publisher metadata', 'field': 'published-online', 'value': '2025-05-01'})
        update.apply_publication_evidence(row, '2026-10-29', {
            'status': 'day_known', 'source': 'Crossref publisher metadata', 'field': 'published-print', 'value': '2026-10-29'})
        self.assertEqual(row['published'], '2025-05-01')
        self.assertEqual(row['publication_date_provenance']['earlier_publication_evidence']['field'], 'published-online')
        update.apply_publication_evidence(row, '', {'status': 'unresolved', 'verification_error': True})
        self.assertEqual(row['published'], '2025-05-01')

    def test_legacy_or_mismatching_prior_day_does_not_override_verified_original_day(self):
        for prior in ({'status': 'day_known'},
                      {'status': 'day_known', 'source': 'Crossref publisher metadata',
                       'field': 'published-online', 'value': '2025-05-02'}):
            with self.subTest(prior=prior):
                row = dict(kind='scholarly', published='2025-05-01', publication_date_provenance=prior)
                incoming = {'status': 'day_known', 'source': 'Crossref publisher metadata',
                            'field': 'published-online', 'value': '2026-10-29'}
                update.apply_publication_evidence(row, '2026-10-29', incoming)
                self.assertEqual(row['published'], '2026-10-29')
                self.assertEqual(row['publication_date_provenance']['value'], '2026-10-29')
                self.assertNotIn('earlier_publication_evidence', row['publication_date_provenance'])

    def test_arxiv_doi_uses_official_v1_metadata_not_crossref(self):
        atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2610.12345v1</id><title>Generative AI and cognitive offloading</title><published>2026-10-28T10:00:00Z</published><updated>2026-11-07T00:00:00Z</updated><summary>Not persisted</summary></entry></feed>'
        verifier = ArxivPublicationVerifier(lambda url: atom, sleep=lambda seconds: None)
        rows, errors, stats, calls = self.discover([openalex(doi='10.48550/arxiv.2610.12345')], [], arxiv_verifier=verifier)
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['published'], '2026-10-28')
        self.assertEqual(rows[0]['publication_date_provenance']['basis'], 'arxiv_first_submitted')
        self.assertFalse(any('/works/10.' in url for url in calls)); self.assertFalse(errors)
        self.assertEqual(stats['arxiv_publication_verification']['requests'], 1)
        verifier = ArxivPublicationVerifier(lambda url: atom.replace('2026-10-28T10:00:00Z', '2025-10-28T10:00:00Z'), sleep=lambda seconds: None)
        rows, _, stats, _ = self.discover([openalex(doi='10.48550/arxiv.2610.12345')], [], arxiv_verifier=verifier)
        self.assertFalse(rows)
        self.assertEqual(stats['publication_date_corrections']['10.48550/arxiv.2610.12345'][0], '2025-10-28')

    def test_priority_weekly_skips_nominations_and_drops_old_online_first(self):
        work = crossref(); work['published-online'] = {'date-parts': [[2025, 8, 1]]}
        urls = []
        def fetch(url):
            urls.append(url)
            return {'message': {'items': [work, crossref(doi='10.1234/new')], 'total-results': 2}}
        manifest = {'papers': [{'doi': DOI}], 'venue_queries': [{'venue': 'Computers & Education', 'lane': 'AI & cognition', 'q': 'generative AI'}]}
        rows, errors, stats = pr.discover(fetch, dt.date.fromisoformat(TODAY), manifest=manifest)
        self.assertEqual([r['doi'] for r in rows], ['10.1234/new'])
        self.assertEqual(stats['priority_dois_requested'], 0)
        self.assertTrue(all('/works?' in u and 'mailto=' not in u for u in urls)); self.assertFalse(errors)

    def run_main(self, old, candidates, stats=None, mode='weekly', prior_week=None, priority=None, priority_stats=None):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / 'library.json').write_text(json.dumps(old))
            if prior_week is not None: (data / 'weekly.json').write_text(json.dumps(prior_week))
            with patch.object(update, 'DIR', data), patch.object(update, 'TODAY', TODAY), patch.dict('os.environ', {'MODE': mode}), patch.object(update, 'discover', return_value=(candidates, [], stats or {})), patch.object(update, 'discover_priority', return_value=(priority or [], [], priority_stats or {})), patch('builtins.print'):
                update.main()
            return json.loads((data / 'library.json').read_text()), json.loads((data / 'weekly.json').read_text())

    def test_main_preserves_history_but_only_includes_eligible_published_sources(self):
        old = [{'title': 'Old AI cognitive offloading', 'published': '2020-01-01', 'kind': 'scholarly', 'doi': DOI, 'first_seen': TODAY}]
        new = [{'title': f'AI cognitive offloading {i}', 'published': '2026-10-29', 'kind': 'scholarly', 'doi': f'10.1234/{i}', 'url': f'https://doi.org/10.1234/{i}', 'lane': 'AI & cognition', 'publication_date_provenance': {'status': 'day_known', 'source': 'Crossref publisher metadata', 'field': 'published-online', 'value': '2026-10-29'}} for i in range(65)]
        library, week = self.run_main(old, new)
        self.assertEqual(len(library), 66); self.assertEqual(len(week['items']), 65)
        self.assertEqual(week['run']['publication_window']['from'], '2026-10-26')

    def test_new_date_correction_removes_existing_print_dated_item(self):
        prior = {'title': 'AI cognitive offloading', 'published': '2026-10-29', 'source': 'Crossref', 'kind': 'scholarly', 'doi': DOI, 'publication_date_provenance': {'status': 'day_known', 'source': 'Crossref publisher metadata', 'field': 'published-print', 'value': '2026-10-29'}}
        library, week = self.run_main([prior], [], {'publication_date_corrections': {DOI: ('2025-08-01', {'status': 'day_known', 'source': 'Crossref publisher metadata', 'field': 'published-online', 'value': '2025-08-01'})}})
        self.assertFalse(week['items']); self.assertEqual(library[0]['published'], '2025-08-01')

    def test_manual_backfill_does_not_replace_weekly_membership(self):
        existing = {'run': {'date': '2026-11-02'}, 'items': [{'title': 'Saved weekly source'}]}
        _, week = self.run_main([], [], mode='backfill', prior_week=existing)
        self.assertEqual(week, existing)


if __name__ == '__main__':
    unittest.main()

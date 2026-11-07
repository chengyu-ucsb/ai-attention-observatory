"""Offline regressions for strict original-publication-week membership."""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collection_window import (crossref_publication, date_in_window, previous_week,
                               publication_date, weekly_eligible, window_metadata)
from build_weekly import select, build


def verified_record(title, published='', **fields):
    return dict(title=title, published=published, kind='scholarly',
                publication_date_provenance={'status': 'day_known',
                    'source': 'Crossref publisher metadata', 'field': 'published-online', 'value': published},
                **fields)


class CollectionWindowTests(unittest.TestCase):
    def test_every_day_in_run_week_uses_same_completed_utc_week(self):
        expected = dt.date(2026, 10, 26), dt.date(2026, 11, 1)
        for day in range(2, 9):
            self.assertEqual(previous_week(dt.date(2026, 11, day)), expected)
            self.assertEqual(previous_week(f'2026-11-{day:02}'), expected)
        self.assertEqual(previous_week('2026-11-09'), (dt.date(2026, 11, 2), dt.date(2026, 11, 8)))

    def test_timezone_conversion_happens_before_week_selection(self):
        self.assertEqual(previous_week('2026-11-01T23:30:00-05:00'), previous_week('2026-11-02'))
        self.assertEqual(previous_week(dt.datetime(2026, 11, 2, 0, 0, tzinfo=dt.timezone.utc)), previous_week('2026-11-02'))
        self.assertEqual(publication_date('2026-11-01T23:30:00-05:00'), dt.date(2026, 11, 2))

    def test_leap_and_year_boundary(self):
        self.assertEqual(previous_week('2024-03-04'), (dt.date(2024, 2, 26), dt.date(2024, 3, 3)))
        self.assertEqual(previous_week('2027-01-01'), (dt.date(2026, 12, 21), dt.date(2026, 12, 27)))

    def test_exact_inclusive_boundaries_and_no_partial_padding(self):
        start, end = previous_week('2026-11-07')
        for value in ['2026-10-26', '2026-11-01', '2026-11-01T23:59:59Z']:
            self.assertTrue(date_in_window(value, start, end), value)
        for value in [None, '', '2026', '2026-11', '2026-02-30', '2026-10-25', '2026-11-02', '2026-11-01 arbitrary']:
            self.assertFalse(date_in_window(value, start, end), value)
        with self.assertRaises(ValueError):
            previous_week('2026-11')

    def test_online_first_precedes_print_and_retains_all_date_evidence(self):
        work = {'published': {'date-parts': [[2026, 10, 28]]},
                'published-print': {'date-parts': [[2026, 11, 1]]},
                'published-online': {'date-parts': [[2025, 9, 3]]},
                'indexed': {'date-time': '2026-10-30T00:00:00Z'}}
        day, provenance = crossref_publication(work)
        self.assertEqual(day, '2025-09-03')
        self.assertEqual(provenance['field'], 'published-online')
        self.assertEqual(len(provenance['evidence']), 3)
        self.assertFalse(date_in_window(day, *previous_week('2026-11-07')))

    def test_partial_original_event_cannot_fall_back_to_later_print(self):
        work = {'published-online': {'date-parts': [[2025]]}, 'published-print': {'date-parts': [[2026, 10, 30]]}}
        self.assertEqual(crossref_publication(work)[0], '')
        for parts in [[2026], [2026, 10], [2026, 2, 31], [2026, 10, 0], [None, 10, 30]]:
            self.assertEqual(crossref_publication({'published': {'date-parts': [parts]}})[0], '', parts)

    def test_registry_activity_dates_are_never_publication_fallback(self):
        work = {name: {'date-parts': [[2026, 10, 30]], 'date-time': '2026-10-30T00:00:00Z'}
                for name in ['created', 'indexed', 'deposited', 'updated']}
        self.assertEqual(crossref_publication(work)[0], '')

    def test_partial_or_malformed_original_events_cannot_hide_behind_precise_print(self):
        for field in ('published-online', 'published', 'issued'):
            for original in ({'date-parts': [[2025]]}, {'date-parts': [[2025, 10]]},
                             {'date-parts': ['2025']}, {'date-parts': []}, '2025'):
                with self.subTest(field=field, original=original):
                    day, provenance = crossref_publication({field: original,
                        'published-print': {'date-parts': [[2026, 10, 28]]}})
                    self.assertEqual(day, '')
                    self.assertEqual(provenance['status'], 'unresolved')
                    self.assertTrue(any(e['field'] == field and e['precision'] == 'unresolved'
                                        for e in provenance['evidence']))

    def test_nomination_first_seen_and_curated_do_not_bypass_dates(self):
        rows = [verified_record('Fresh', '2026-10-26', first_seen='2026-01-01', lane='Extra lane'),
                verified_record('Sunday', '2026-11-01', curated=True),
                verified_record('Old nominated', '2024-01-01', first_seen='2026-11-07', brief_provenance={'week': '2026-11-07'}),
                verified_record('Undated nominated', first_seen='2026-11-07', brief_provenance={'week': '2026-11-07'}),
                verified_record('Current', '2026-11-02', first_seen='2026-11-07'),
                verified_record('Backfill', '2026-10-27', historical_backfill=True)]
        self.assertEqual({r['title'] for r in select(rows, '2026-11-07')}, {'Fresh', 'Sunday'})

    def test_no_display_cap_or_unknown_lane_omission(self):
        rows = [verified_record(str(i), '2026-10-29', lane='Extra lane' if i % 2 else 'AI & cognition') for i in range(100)]
        self.assertEqual(len(select(rows, '2026-11-07')), 100)

    def test_legacy_feed_and_padded_registry_dates_need_fresh_evidence(self):
        start, end = previous_week('2026-11-07')
        base = dict(published='2026-11-01', kind='nonacademic', source='Publisher RSS / Google News RSS', url='https://example.org/story')
        self.assertFalse(weekly_eligible(base, start, end))
        base['publication_date_provenance'] = {'basis': 'publisher_atom_published', 'date': '2026-11-01'}
        self.assertTrue(weekly_eligible(base, start, end))
        base['url'] = 'https://news.google.com/rss/articles/id'
        self.assertFalse(weekly_eligible(base, start, end))
        self.assertFalse(weekly_eligible(dict(published='2026-11-01', source='Crossref', kind='scholarly'), start, end))
        legacy = dict(published='2026-11-01', source='OpenAlex', kind='scholarly', doi='10.1234/old')
        self.assertFalse(weekly_eligible(legacy, start, end))
        legacy['source'] = 'Unknown registry'
        self.assertFalse(weekly_eligible(legacy, start, end))
        for state in ['unresolved', 'conflict', 'unknown']:
            legacy['publication_date_provenance'] = {'status': state, 'source': 'Crossref publisher metadata',
                'field': 'published-online', 'value': '2026-11-01'}
            self.assertFalse(weekly_eligible(legacy, start, end))
        legacy['publication_date_provenance'] = {'status': 'day_known'}
        self.assertFalse(weekly_eligible(legacy, start, end))
        legacy['source'] = 'OpenAlex'
        legacy['publication_date_provenance'] = {'status': 'day_known', 'source': 'OpenAlex', 'field': 'publication_date', 'value': '2026-11-01'}
        self.assertFalse(weekly_eligible(legacy, start, end))
        legacy['publication_date_provenance'] = {'status': 'day_known', 'source': 'Crossref publisher metadata', 'field': 'published-online', 'value': '2026-11-01'}
        self.assertTrue(weekly_eligible(legacy, start, end))

    def test_every_source_needs_matching_recognized_original_day_evidence(self):
        start, end = previous_week('2026-11-07')
        for kind in ('scholarly', 'nonacademic'):
            for source in ('Publisher webpage', 'Weekly brief lead verified against arXiv', 'Unknown registry'):
                base = dict(kind=kind, source=source, published='2026-10-28', doi='',
                            first_seen='2026-10-28', updated='2026-10-28')
                for provenance in ({}, {'status': 'day_known', 'field': 'dateModified', 'value': '2026-10-28'},
                                   {'basis': 'publisher_datePublished', 'date': '2026-09-01'},
                                   {'basis': 'publisher_datePublished', 'date': '2026-10'}, 'not an object'):
                    with self.subTest(kind=kind, source=source, provenance=provenance):
                        self.assertFalse(weekly_eligible(dict(base, publication_date_provenance=provenance), start, end))
                self.assertTrue(weekly_eligible(dict(base, publication_date_provenance={
                    'basis': 'publisher_datePublished', 'date': '2026-10-28'}), start, end))

    def test_partial_earlier_generic_publication_event_is_uncertain(self):
        from collection_window import crossref_publication
        for field in ('published','issued'):
            day,evidence=crossref_publication({'published-print':{'date-parts':[[2026,10,28]]},field:{'date-parts':[[2025]]}})
            self.assertEqual(day,'');self.assertEqual(evidence['status'],'unresolved')

    def test_build_labels_actual_publication_window_and_drops_stale_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data = root / 'data'; data.mkdir()
            (data / 'library.json').write_text(json.dumps([verified_record('Inside', '2026-10-28'), verified_record('Old', '2025-01-01')]))
            (data / 'weekly.json').write_text(json.dumps({'run': {'date': '2026-11-07'}, 'items': [dict(title='Stale', published='2020-01-01')]}))
            with patch('builtins.print'):
                build(root)
            saved = json.loads((data / 'weekly.json').read_text())
        self.assertEqual([r['title'] for r in saved['items']], ['Inside'])
        self.assertEqual(saved['run']['publication_window'], window_metadata('2026-11-07'))
        self.assertEqual(saved['run']['date'], '2026-11-07')
        self.assertEqual(saved['run']['last_seven_days'], 1)


if __name__ == '__main__':
    unittest.main()

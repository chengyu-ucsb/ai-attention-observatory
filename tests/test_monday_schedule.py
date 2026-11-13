"""Monday issue identity stays fixed across late publication and retry runs."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collection_window import window_metadata
from edition_schedule import canonical_edition_date, monday_for_window, release_cutoff, edition_release_open
import compose_issue
import publish_deadline


class MondayEditionTests(unittest.TestCase):
    def root(self, tmp):
        root = Path(tmp)
        (root / 'data').mkdir()
        return root

    def test_every_retry_day_uses_the_same_monday_even_without_an_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            for day in range(9, 16):
                with self.subTest(day=day):
                    self.assertEqual(canonical_edition_date(root, f'2026-11-{day:02d}'), '2026-11-09')
            folder = root / 'data/approved-issues'; folder.mkdir()
            (folder / '2026-11-13.json').write_text(json.dumps({
                'edition_date': '2026-11-13', 'status': 'published',
                'publication_window': window_metadata('2026-11-13')}))
            self.assertEqual(canonical_edition_date(root, '2026-11-15'), '2026-11-09')

    def test_identity_comes_from_the_completed_source_week(self):
        window = window_metadata('2026-11-13')
        self.assertEqual(monday_for_window(window), '2026-11-09')
        # An explicit historical window remains historical during a later repair.
        self.assertEqual(canonical_edition_date(None, '2026-11-16', publication_window=window), '2026-11-09')
        self.assertEqual(canonical_edition_date(None, '2026-11-08'), '2026-11-02')
        self.assertEqual(canonical_edition_date(None, '2026-11-09'), '2026-11-09')
        for change in ({'to': '2026-11-07'}, {'from': '2026-11-03'}, {'timezone': 'America/New_York'}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'complete Monday'):
                monday_for_window({**window, **change})

    def test_release_window_starts_at_1205_eastern_and_tracks_dst(self):
        for month, day, hour in [(11, 9, 17), (6, 8, 16)]:
            with self.subTest(month=month):
                self.assertFalse(release_cutoff(dt.datetime(2026, month, day, hour, 4, tzinfo=dt.timezone.utc)))
                self.assertTrue(release_cutoff(dt.datetime(2026, month, day, hour, 5, tzinfo=dt.timezone.utc)))
        # Sunday evening Eastern can already be Monday UTC; do not release early.
        self.assertFalse(release_cutoff(dt.datetime(2026, 11, 9, 1, tzinfo=dt.timezone.utc)))
        with self.assertRaisesRegex(ValueError, 'timezone'):
            release_cutoff(dt.datetime(2026, 11, 9, 17, 5))


    def test_full_edition_waits_for_eastern_monday_even_after_utc_rollover(self):
        # Midnight Eastern is 05:00 UTC in winter and 04:00 UTC in summer.
        for monday, hour in [('2026-11-09', 5), ('2026-06-08', 4)]:
            day = dt.date.fromisoformat(monday)
            opens = dt.datetime.combine(day, dt.time(hour), dt.timezone.utc)
            with self.subTest(monday=monday):
                self.assertFalse(edition_release_open(monday, opens - dt.timedelta(seconds=1)))
                self.assertTrue(edition_release_open(monday, opens))
                self.assertTrue(edition_release_open(monday, opens + dt.timedelta(days=4)))
        self.assertFalse(edition_release_open('2026-11-09', dt.datetime(2026, 11, 9, 1, tzinfo=dt.timezone.utc)))

    def test_historical_editions_can_be_corrected_without_changing_their_monday(self):
        sunday_eastern = dt.datetime(2026, 11, 9, 1, tzinfo=dt.timezone.utc)
        self.assertTrue(edition_release_open('2026-11-02', sunday_eastern))
        self.assertFalse(edition_release_open('2026-11-16', sunday_eastern))
        with self.assertRaisesRegex(ValueError, 'Monday'):
            edition_release_open('2026-11-13', sunday_eastern)
        with self.assertRaisesRegex(ValueError, 'timezone'):
            edition_release_open('2026-11-09', dt.datetime(2026, 11, 9, 5))


    def test_first_friday_release_keeps_monday_key_and_actual_publication_time(self):
        now = dt.datetime(2026, 11, 13, 18, 20, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            result = publish_deadline.publish(root, now)
            self.assertEqual(result['edition_date'], '2026-11-09')
            folder = root / 'data/approved-issues'
            self.assertEqual([p.name for p in folder.iterdir()], ['2026-11-09.json'])
            path = folder / '2026-11-09.json'
            original = path.read_bytes()
            issue = json.loads(original)
            self.assertEqual(issue['published_at'], now.isoformat())
            self.assertEqual(issue['publication_window'], window_metadata('2026-11-09'))
            publish_deadline.validate_coverage(issue)
            self.assertEqual(publish_deadline.publish(root, now + dt.timedelta(days=2))['status'], 'edition_exists')
            self.assertEqual(path.read_bytes(), original)

    def test_actual_timestamp_does_not_open_coverage_template_to_arbitrary_copy(self):
        issue = publish_deadline.coverage_issue('2026-11-13', '01', [], published_at='2026-11-13T17:05:00+00:00')
        self.assertEqual(issue['edition_date'], '2026-11-09')
        publish_deadline.validate_coverage(issue)
        for change in ({'published_at': '2026-11-13'}, {'deck': 'Unchecked research conclusion.'},
                       {'arbitrary_metadata': 'Unchecked research conclusion.'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                publish_deadline.validate_coverage({**issue, **change})

    def test_pending_and_preflight_report_monday_without_rewriting_discovery_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp); data = root / 'data'
            weekly = {'run': {'date': '2026-11-13', 'publication_window': window_metadata('2026-11-13')}, 'items': []}
            (data / 'public-weekly.json').write_text(json.dumps(weekly))
            (data / 'issue-editorial.json').write_text('{}')
            packet = compose_issue.pending(root, today=dt.date(2026, 11, 13))
            self.assertEqual(packet['run']['date'], '2026-11-13')
            self.assertEqual(packet['run']['edition_date'], '2026-11-09')
            self.assertEqual(compose_issue.readiness(root, today=dt.date(2026, 11, 13))['edition_date'], '2026-11-09')
            self.assertEqual(json.loads((data / 'public-weekly.json').read_text()), weekly)
            folder = data / 'approved-issues'; folder.mkdir()
            notice = publish_deadline.coverage_issue('2026-11-13', '04', [])
            (folder / '2026-11-09.json').write_text(json.dumps(notice))
            packet = compose_issue.pending(root, today=dt.date(2026, 11, 13))
            self.assertEqual(packet['run']['edition_date'], '2026-11-09')
            self.assertEqual(packet['run']['edition_number'], '04')


    def test_composition_writes_draft_and_audit_under_monday_not_execution_day(self):
        weekly = {'run': {'date': '2026-11-13', 'publication_window': window_metadata('2026-11-13'),
                          'edition_number': '04'}, 'items': []}
        packet = [{'key': f'S{i}', 'title': f'Original {i}', 'level': 'full_text'} for i in range(3)]
        draft = {'headline': 'A source-backed weekly synthesis', 'signals': [], 'tension': {}}
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp); data = root / 'data'
            (data / 'issue-editorial.json').write_text('{}')
            with patch.object(compose_issue, 'pending', return_value=copy.deepcopy(weekly)), \
                 patch.object(compose_issue, 'evidence', return_value=packet), \
                 patch.object(compose_issue, 'draft_in_stages', return_value=draft):
                self.assertTrue(compose_issue.compose(root, model=object(), today=dt.date(2026, 11, 13)))
            written = json.loads((data / 'issue-editorial.json').read_text())
            self.assertEqual(list(written), ['2026-11-09'])
            self.assertEqual(written['2026-11-09']['number'], '04')
            audit = json.loads((data / 'edition-audits/2026-11-09.json').read_text())
            self.assertEqual(audit['edition_date'], '2026-11-09')
            self.assertFalse((data / 'edition-audits/2026-11-13.json').exists())


if __name__ == '__main__':
    unittest.main()

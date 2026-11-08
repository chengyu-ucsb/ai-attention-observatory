"""Repeat-feed → publisher-check regressions for exact source-bound receipts."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import discover_editorial as discovery
import editorial_metadata as metadata
import original_readings as original
from checked_reading_types import record_digest
from collection_window import previous_week, weekly_eligible
from test_checked_reading_types import commentary
from test_original_readings import article_screen, approve
from test_editorial_metadata import page

FIRST = '2026-11-05T12:00:00+00:00'
LATER = '2026-11-07T12:00:00+00:00'


def fixture():
    row, note = commentary()
    row['publication_date_provenance'] = {
        'basis': 'publisher_rss_pubDate', 'date': row['published'],
        'source_url': 'https://example.org/feed', 'independently_verified': False}
    html = page(date=row['published'], title=row['title'], canonical=row['url'])
    first = metadata.verify_record(row, html, checked_at=FIRST)
    article_screen(note, first)
    approve(note)
    observation = deepcopy(row['publication_date_provenance'])
    return first, note, html, observation


def status(row, observation):
    return {'verified_existing_records': [{
        'url': row['url'], 'published': row['published'],
        'publication_date_provenance': observation,
        'discovery_provenance': {'method': 'publisher_feed', 'checked_at': LATER}}]}


class EvidenceLifecycleTests(unittest.TestCase):
    def test_repeat_feed_then_page_preserves_receipt_and_updates_run_times(self):
        first, note, html, observation = fixture()
        self.assertTrue(original.eligible(note, first))
        refreshed = discovery.apply_discovery_evidence([deepcopy(first)], status(first, observation))[0]
        self.assertEqual(refreshed['publication_date_provenance'], first['publication_date_provenance'])
        self.assertEqual(refreshed['discovery_provenance']['checked_at'], LATER)
        repeated = metadata.verify_record(refreshed, html, checked_at=LATER)
        self.assertEqual(record_digest(first), record_digest(repeated))
        self.assertTrue(original.eligible(note, repeated))
        self.assertEqual(repeated['editorial_metadata']['checked_at'], LATER)
        self.assertEqual(repeated['publication_date_provenance']['checked_at'], FIRST)

    def test_new_feed_source_or_basis_changes_binding_even_on_same_date(self):
        for key, value in [('source_url', 'https://example.org/new-feed'),
                           ('basis', 'publisher_atom_published')]:
            with self.subTest(key=key):
                first, note, html, observation = fixture()
                observation[key] = value
                refreshed = discovery.apply_discovery_evidence([deepcopy(first)], status(first, observation))[0]
                self.assertFalse(original.eligible(note, refreshed))
                repeated = metadata.verify_record(refreshed, html, checked_at=LATER)
                self.assertNotEqual(record_digest(first), record_digest(repeated))
                self.assertFalse(original.eligible(note, repeated))

    def test_new_publisher_evidence_still_invalidates_after_repeat_feed(self):
        first, note, html, observation = fixture()
        refreshed = discovery.apply_discovery_evidence([deepcopy(first)], status(first, observation))[0]
        html += '<meta property="article:published_time" content="' + first['published'] + '">'
        repeated = metadata.verify_record(refreshed, html, checked_at=LATER)
        self.assertFalse(original.eligible(note, repeated))
        self.assertEqual(repeated['publication_date_provenance']['checked_at'], LATER)

    def test_conflicting_feed_date_quarantines_and_later_match_cannot_clear_it(self):
        first, note, html, observation = fixture()
        conflict = deepcopy(observation)
        conflict['date'] = '2026-09-01'
        current_status = status(first, observation)
        current_status['conflicting_existing_records'] = [{
            'url': first['url'], 'conflicting_evidence': [conflict]}]
        refreshed = discovery.apply_discovery_evidence([deepcopy(first)], current_status)[0]
        self.assertEqual(refreshed['publication_date_provenance']['status'], 'unresolved')
        self.assertFalse(original.eligible(note, refreshed))
        discovery.apply_discovery_evidence([refreshed], status(first, observation))
        repeated = metadata.verify_record(refreshed, html, checked_at=LATER)
        self.assertEqual(repeated['editorial_metadata']['date_status'], 'conflict')
        self.assertFalse(original.eligible(note, repeated))

    def test_unverified_provenance_is_not_protected_as_publisher_checked(self):
        first, _, _, observation = fixture()
        first['publication_date_provenance']['independently_verified'] = False
        refreshed = discovery.apply_discovery_evidence([first], status(first, observation))[0]
        self.assertEqual(refreshed['publication_date_provenance'], observation)

    def test_reconciled_eff_records_keep_exact_existing_acceptance_receipts(self):
        rows = json.loads((ROOT / 'data/library.json').read_text())
        notes = json.loads((ROOT / 'data/original-readings.json').read_text())['articles']
        discovery_status = json.loads((ROOT / 'data/editorial-discovery-status.json').read_text())
        notes = [n for n in notes if n['id'].startswith('checked-eff-')]
        self.assertEqual(len(notes), 3)
        for note in notes:
            with self.subTest(id=note['id']):
                row = next(r for r in rows if r.get('url') == note['record_url'])
                self.assertTrue(original.eligible(note, row))
                self.assertEqual(record_digest(row), note['article_screen']['record_sha256'])
                refreshed = discovery.apply_discovery_evidence([deepcopy(row)], discovery_status)[0]
                self.assertEqual(record_digest(row), record_digest(refreshed))
                # A real evidence/identity change still invalidates the receipt.
                changed = deepcopy(refreshed)
                changed['publication_date_provenance']['evidence'][0]['source_url'] += '/changed'
                self.assertFalse(original.eligible(note, changed))

    def test_parenting_modified_after_week_remains_out_of_historical_shelf(self):
        rows = json.loads((ROOT / 'data/library.json').read_text())
        notes = json.loads((ROOT / 'data/original-readings.json').read_text())['articles']
        note = next(n for n in notes if n['id'] == 'checked-eff-parenting-2026-10-29')
        row = next(r for r in rows if r.get('url') == note['record_url'])
        original.apply([row], {'articles': [note]})
        self.assertTrue(original.eligible(note, row))
        self.assertFalse(weekly_eligible(row, *previous_week('2026-11-08')))


if __name__ == '__main__':
    unittest.main()

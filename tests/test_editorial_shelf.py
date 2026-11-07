"""Thin weekly editions must not be padded with older indexed context."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_public import editorial_shelf
from collection_window import window_metadata


def item(n, seen, level='full_text', published='2026-10-28'):
    return {
        'title': f'Substantive AI research {n}', 'doi': f'10.1100/test{n}',
        'first_seen': seen, 'published': published, 'kind': 'scholarly',
        'publication_date_provenance': {'status': 'day_known', 'source': 'Crossref publisher metadata',
                                        'field': 'published-online', 'value': published},
        'source_group': 'AI-specific',
        'reading': {
            'level': level,
            'findings': ('The authors report a within-class learning comparison, '
                         'with limitations around validity and transfer. ') * 5,
            'methods': 'The methods compare different levels of AI assistance.'
        }
    }


class EditorialShelfTests(unittest.TestCase):
    def test_thin_week_never_adds_older_context_even_without_explicit_window(self):
        fresh = item('new', '2026-11-02')
        recent = [item(i, '2026-10-26', published='2026-09-01') for i in range(8)]
        weekly = {'run': {'date': '2026-11-02'}, 'items': [fresh]}
        shelf = editorial_shelf(weekly, [fresh] + recent)
        self.assertEqual(len(weekly['items']), 1)
        self.assertEqual(shelf['run']['publication_week_source_count'], 1)
        self.assertEqual(shelf['run']['context_source_count'], 0)
        self.assertEqual(shelf['run']['publication_window'], window_metadata('2026-11-02'))
        self.assertEqual(shelf['items'], [{**fresh, 'editorial_role': 'publication_week'}])

    def test_no_extra_sources_if_week_is_already_sufficient(self):
        fresh = [item(i,'2026-11-02') for i in range(4)]
        weekly={'run': {'date': '2026-11-02'}, 'items': fresh}
        shelf = editorial_shelf(weekly, fresh + [item('old','2026-10-26')])
        self.assertEqual(shelf['run']['context_source_count'],0)
        self.assertEqual(len(shelf['items']),4)

    def test_withhold_citation_only_and_historical_backfill(self):
        fresh = item('new', '2026-11-02')
        old = item('old', '2026-10-26', published='2026-10-20')
        citation = item('citation','2026-10-26', level='citation_only')
        ancient = item('ancient','2026-06-01')
        history = {**item('history','2026-10-26'),'historical_backfill':True}
        shelf = editorial_shelf({'run': {'date': '2026-11-02'},'items':[fresh]},
                               [fresh,old,citation,ancient,history])
        self.assertEqual([r['doi'] for r in shelf['items']], [fresh['doi']])
        self.assertEqual(shelf['run']['context_source_count'], 0)

    def test_dated_legacy_shelf_rejects_older_membership(self):
        old = item('old', '2026-11-02', published='2026-08-13')
        with self.assertRaises(ValueError):
            editorial_shelf({'run': {'date': '2026-11-02'}, 'items': [old]}, [old])


if __name__ == '__main__':
    unittest.main()


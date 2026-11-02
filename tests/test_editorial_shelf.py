"""A thin new-source week may use verified older context without inflating new RSS."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_public import editorial_shelf


def item(n, seen, level='full_text'):
    return {
        'title': f'Substantive AI research {n}', 'doi': f'10.1100/test{n}',
        'first_seen': seen, 'published': '2026-10-20', 'kind': 'scholarly',
        'source_group': 'AI-specific',
        'reading': {
            'level': level,
            'findings': ('The authors report a within-class learning comparison, '
                         'with limitations around validity and transfer. ') * 5,
            'methods': 'The methods compare different levels of AI assistance.'
        }
    }


class EditorialShelfTests(unittest.TestCase):
    def test_thin_week_keeps_new_feed_separate_from_context(self):
        fresh = item('new', '2026-11-02')
        recent = [item(i, '2026-10-26') for i in range(8)]
        weekly = {'run': {'date': '2026-11-02'}, 'items': [fresh]}
        shelf = editorial_shelf(weekly, [fresh] + recent)
        self.assertEqual(len(weekly['items']), 1)
        self.assertEqual(shelf['run']['newly_indexed_source_count'], 1)
        self.assertGreaterEqual(shelf['run']['context_source_count'], 3)
        self.assertEqual(shelf['items'][0]['editorial_role'], 'collection_week')
        self.assertTrue(all(x['editorial_role'] == 'previously_indexed_context'
                            for x in shelf['items'][1:]))

    def test_no_extra_sources_if_week_is_already_sufficient(self):
        fresh = [item(i,'2026-11-02') for i in range(4)]
        weekly={'run': {'date': '2026-11-02'}, 'items': fresh}
        shelf = editorial_shelf(weekly, fresh + [item('old','2026-10-26')])
        self.assertEqual(shelf['run']['context_source_count'],0)
        self.assertEqual(len(shelf['items']),4)

    def test_withhold_citation_only_and_historical_backfill(self):
        fresh = item('new', '2026-11-02')
        old = item('old', '2026-10-26')
        citation = item('citation','2026-10-26', level='citation_only')
        ancient = item('ancient','2026-06-01')
        history = {**item('history','2026-10-26'),'historical_backfill':True}
        shelf = editorial_shelf({'run': {'date': '2026-11-02'},'items':[fresh]},
                               [fresh,old,citation,ancient,history])
        self.assertEqual([r['doi'] for r in shelf['items']], [fresh['doi'],old['doi']])


if __name__ == '__main__':
    unittest.main()

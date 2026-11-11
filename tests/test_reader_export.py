from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_reader as reader


class ReaderExportTests(unittest.TestCase):
    def test_export_is_small_versioned_and_bound_to_published_edition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); data = root / 'data'; data.mkdir()
            row = {'doi': '10.1234/a', 'title': 'An article', 'kind': 'scholarly',
                   'analysis': {'results': 'PRIVATE_OPERATION_MARKER' * 100},
                   'reading': {'level': 'full_text', 'digest': {'idea': 'An idea', 'finding': 'An observed result.'}}}
            issue = {'status': 'published', 'edition_date': '2026-11-07', 'sources': [{'id': 'old-source'}]}
            for name, value in [('public-library', [row]), ('public-featured-issue', issue),
                                ('public-weekly', {'run': {'date': '2026-11-11', 'query_log': 'OPERATIONAL_SECRET'}, 'items': [{'id': 'new-source'}]}),
                                ('fulltext-backfill-state', {'total_scholarly':657,'full_text_extracted':303,'diagnostics':'OPERATIONAL_SECRET'})]:
                (data / (name + '.json')).write_text(json.dumps(value))
            report = reader.build(root)
            manifest = json.loads((data / 'reader-manifest.json').read_text())
            self.assertEqual(manifest['issue'], issue)
            self.assertEqual(manifest['edition_id'], '2026-11-07')
            self.assertNotIn('OPERATIONAL_SECRET', json.dumps(manifest))
            self.assertEqual(manifest['backlog'],{'total_scholarly':657,'full_text_extracted':303})
            index = json.loads((root / manifest['index_url']).read_text())
            self.assertNotIn('PRIVATE_OPERATION_MARKER', json.dumps(index))
            self.assertEqual(json.loads((root / index[0]['article_payload']).read_text()), row)
            self.assertTrue(index[0]['has_finding'])
            self.assertIn('observed', index[0]['search_terms'])
            self.assertLess(report['index_bytes'], len(json.dumps(row)))
            reader.build(root)
            self.assertEqual(json.loads((data / 'reader-manifest.json').read_text()), manifest)
            row['title'] = 'A corrected title'
            (data / 'public-library.json').write_text(json.dumps([row]))
            reader.build(root)
            changed = json.loads((data / 'reader-manifest.json').read_text())
            self.assertNotEqual(changed['index_url'], manifest['index_url'])
            self.assertEqual(changed['edition_sha256'], manifest['edition_sha256'])

    def test_citation_only_input_cannot_enter_reader_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'data'; data.mkdir()
            (data / 'public-library.json').write_text(json.dumps([{'reading': {'level': 'citation_only'}}]))
            with self.assertRaisesRegex(ValueError, 'screened_public_library'):
                reader.build(directory)


if __name__ == '__main__':
    unittest.main()

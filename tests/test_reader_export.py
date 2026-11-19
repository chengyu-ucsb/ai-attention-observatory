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
            row = {'doi': '10.1234/a', 'title': 'An article', 'display_headline': 'A shorter reading title', 'kind': 'scholarly',
                   'analysis': {'results': 'PRIVATE_OPERATION_MARKER' * 100},
                   'original_reading': {'evidence': {'finding': ['PRIVATE_REVIEW_LOCATOR']}},
                   'reading': {'level': 'full_text', 'review_scope': 'PRIVATE_REVIEW_SCOPE', 'digest': {'idea': 'An idea', 'finding': 'An observed result.'}}}
            issue = {'status': 'published', 'edition_date': '2026-11-07', 'sources': [{'id': 'old-source'}]}
            for name, value in [('public-library', [row]), ('public-featured-issue', issue),
                                ('public-weekly', {'run': {'date': '2026-11-11', 'query_log': 'OPERATIONAL_SECRET'}, 'items': [{'id': 'new-source'}]}),
                                ('fulltext-backfill-state', {'total_scholarly':657,'full_text_extracted':303,'diagnostics':'OPERATIONAL_SECRET'})]:
                (data / (name + '.json')).write_text(json.dumps(value))
            report = reader.build(root)
            manifest = json.loads((data / 'reader-manifest.json').read_text())
            self.assertEqual(manifest['issue'], reader.feed_snapshot(issue))
            self.assertEqual(manifest['reader_sha256'], reader.sha256(reader.encoded(manifest['issue'])).hexdigest())
            self.assertEqual(manifest['edition_sha256'], reader.sha256(reader.encoded(issue)).hexdigest())
            self.assertEqual(manifest['edition_id'], '2026-11-07')
            self.assertNotIn('OPERATIONAL_SECRET', json.dumps(manifest))
            self.assertEqual(manifest['backlog'],{'total_scholarly':657,'full_text_extracted':303})
            index = json.loads((root / manifest['index_url']).read_text())
            self.assertNotIn('PRIVATE_OPERATION_MARKER', json.dumps(index))
            article = json.loads((root / index[0]['article_payload']).read_text())
            self.assertNotIn('PRIVATE_REVIEW', json.dumps(article))
            self.assertNotIn('PRIVATE_REVIEW', json.dumps(index))
            self.assertEqual(article['reading']['digest']['finding'], row['reading']['digest']['finding'])
            self.assertEqual(article['analysis']['results'], row['analysis']['results'])
            self.assertEqual(index[0]['display_headline'], row['display_headline'])
            self.assertEqual(index[0]['title'], row['title'])
            self.assertTrue(index[0]['has_finding'])
            self.assertIn('observed result', index[0]['search_text'])
            self.assertLess(report['index_bytes'], len(json.dumps(row)))
            reader.build(root)
            self.assertEqual(json.loads((data / 'reader-manifest.json').read_text()), manifest)
            row['title'] = 'A corrected title'
            (data / 'public-library.json').write_text(json.dumps([row]))
            reader.build(root)
            changed = json.loads((data / 'reader-manifest.json').read_text())
            self.assertNotEqual(changed['index_url'], manifest['index_url'])
            self.assertEqual(changed['edition_sha256'], manifest['edition_sha256'])

    def test_deployment_exports_only_reader_fields_and_never_replaces_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'data'
            data.mkdir()
            record = {'kind':'scholarly', 'doi':'10.1234/p', 'url':'https://example.org/p',
                      'title':'Paper', 'original_reading':{'evidence':'INTERNAL LOCATOR'},
                      'reading':{'level':'abstract', 'review_scope':'INTERNAL REVIEW',
                                 'digest':{'idea':'An observation.'}}}
            source = {'id':record['doi'], 'title':'Paper', 'url':record['url'], 'kind':'scholarly',
                      'review_label':'INTERNAL PROCESS', 'source_doi':record['doi']}
            issue = {'edition_date':'2026-11-16', 'status':'published', 'headline':'A question',
                     'editorial_note':'INTERNAL RECEIPT','sources':[source],
                     'signals':[{'text':'See Paper.', 'source_ids':[source['id']],
                                 'citations':[{'source_id':source['id'],'text':'Paper','page':3,
                                               'locator':'INTERNAL LOCATOR'}]}]}
            current = {'edition_date':'2026-11-18', 'status':'awaiting_publication',
                       'note':'INTERNAL DRAFT', 'sources':[source], 'headline':'UNPUBLISHED'}
            weekly = {'run':{'date':'2026-11-18','query_log':'INTERNAL QUERY'}, 'items':[record]}
            inputs = {'public-library':[record],'public-weekly':weekly,'public-featured-issue':issue,
                      'public-issue':current}
            for name,value in inputs.items():
                (data / (name+'.json')).write_text(json.dumps(value))
            destination = root / '_site/data'
            reader.build(root, pages_data=destination)
            self.assertNotIn('INTERNAL',''.join(p.read_text() for p in destination.rglob('*.json')))
            def read(name):
                return json.loads((destination / (name+'.json')).read_text())
            self.assertEqual(read('public-library'),read('public-weekly')['items'])
            self.assertEqual(read('public-featured-issue'),read('reader-manifest')['issue'])
            self.assertEqual(read('public-featured-issue')['signals'][0]['citations'][0],
                             {'source_id':source['id'],'text':'Paper','page':3})
            self.assertEqual(read('public-issue'),{'edition_date':'2026-11-18',
                             'status':'awaiting_publication','sources':[], 'source_count':0})
            self.assertEqual(read('reader-manifest')['edition_sha256'],reader.sha256(reader.encoded(issue)).hexdigest())
            self.assertEqual(read('reader-manifest')['reader_sha256'],
                             reader.sha256(reader.encoded(read('public-featured-issue'))).hexdigest())
            self.assertTrue((root / '_site' / read('reader-manifest')['index_url']).exists())
            for name,value in inputs.items():
                self.assertEqual((data / (name+'.json')).read_text(),json.dumps(value))
            with self.assertRaisesRegex(ValueError,'separate destination'):
                reader.build(root, pages_data=data)

    def test_current_edition_has_concrete_tutoring_result_and_distinct_report(self):
        data = Path(__file__).resolve().parents[1] / 'data'
        rows = json.loads((data / 'public-library.json').read_text())
        tutor = next(row for row in rows if row.get('doi') == '10.1111/bjet.70100')
        report = next(row for row in rows if 'amny.com/politics/googles-ai-push' in row.get('url',''))
        tutoring = reader.article(tutor)['reading']['digest']
        self.assertFalse(tutoring['interpretation'])
        self.assertIn('six problems', tutoring['finding'])
        self.assertIn('one school', tutoring['limitation'])
        reading = reader.article(report)['reading']
        self.assertFalse(reading['reported_findings'])
        self.assertIn('November 19', reading['digest']['longform']['qualification'])
        self.assertNotIn('source checked', json.dumps(reading))
        for doi in ('10.1080/00131857.2026.2733624', '10.3389/fpsyg.2025.1699320', '10.1007/s00146-025-02405-8'):
            row = next(row for row in rows if row.get('doi') == doi)
            reading = reader.article(row)['reading']
            self.assertEqual(reading['findings'], '')
            self.assertTrue(reading['digest']['longform']['reasoning'])
            self.assertTrue(reading['digest']['longform']['thesis'])

    def test_citation_only_input_cannot_enter_reader_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'data'; data.mkdir()
            (data / 'public-library.json').write_text(json.dumps([{'reading': {'level': 'citation_only'}}]))
            with self.assertRaisesRegex(ValueError, 'screened_public_library'):
                reader.build(directory)


if __name__ == '__main__':
    unittest.main()

import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from brief_intake import verify, verify_arxiv
from build_weekly import select
from pipeline_status import build
import build_issue

class PipelineTests(unittest.TestCase):
    def test_reviewing_saved_week_preserves_citations_and_latest_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / 'editorial-queue').mkdir()
            (data / 'approved-issues').mkdir()
            sources = [dict(id=f'10.1234/{n}', title=f'Paper {n}', kind='scholarly', url=f'https://doi.org/10.1234/{n}', reading_level='abstract') for n in range(3)]
            draft = {k: '' for k in ('number','subject','headline','deck','letter','experiment','closer','editorial_note')}
            draft.update(signals=[{'sources':['Paper 0']}], tension={'sources':['Paper 1']})
            def save(name, obj):
                (data / name).write_text(json.dumps(obj), encoding='utf-8')
            save('public-weekly.json', {'run':{'date':'2026-11-02'},'items':[]})
            save('issue-editorial.json', {'2026-10-26':draft})
            save('editorial-queue/2026-10-26.json', {'sources':sources})
            save('approved-issues/2026-11-02.json', {'status':'published','edition_date':'2026-11-02'})
            with patch.object(build_issue, 'DATA', data):
                result = build_issue.build('2026-10-26')
            self.assertEqual(result['signals'][0]['source_ids'], ['10.1234/0'])
            self.assertEqual(json.loads((data/'public-featured-issue.json').read_text())['edition_date'],'2026-11-02')

    def test_complete_week_survives_channel_caps_and_excludes_backfill(self):
        items = [dict(title=f'Paper {n}', lane='AI & cognition', first_seen='2026-10-26') for n in range(65)]
        items += [dict(title='Old anchor', first_seen='2026-10-26', historical_backfill=True),
                  dict(title='Future', first_seen='2026-11-02'),
                  dict(title='Early nomination', lane='Interventions', first_seen='2026-09-01', brief_provenance={'week': '2026-10-26'})]
        result = select(items, '2026-10-26')
        self.assertEqual(len(result), 66)
        self.assertNotIn('Old anchor', {x['title'] for x in result})
        self.assertNotIn('Future', {x['title'] for x in result})

    def test_arxiv_identity_and_preprint_status(self):
        lead = dict(title='AI and attention', url='https://arxiv.org/abs/2610.12345', lane='Interventions', week='2026-10-26', origin='test')
        atom = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <id>http://arxiv.org/abs/2610.12345v1</id><title>AI and attention</title>
          <published>2026-10-20T10:00:00Z</published><summary>Author supplied abstract.</summary>
          <author><name>Example</name></author></entry></feed>'''
        record = verify_arxiv(lead, dt.date(2026,10,26), lambda url: atom)
        self.assertEqual(record['venue'], 'arXiv')
        self.assertNotIn('reading', record)
        with self.assertRaises(ValueError):
            verify_arxiv(lead, dt.date(2026,10,26), lambda url: atom.replace('2610.12345v1', '2610.99999v1'))

    def test_mismatched_registry_identity_is_not_imported(self):
        lead = dict(doi='10.1234/test', title='AI and attention', lane='Interventions', week='2026-10-26', origin='test')
        work = {'DOI': lead['doi'], 'type': 'journal-article', 'title': ['Unrelated machine architecture'], 'published': {'date-parts': [[2026, 10, 20]]}}
        with self.assertRaises(ValueError):
            verify(lead, dt.date(2026, 10, 26), lambda url: {'message': work})

    def test_chat_claims_are_not_source_text(self):
        lead = dict(doi='10.1234/test', title='AI and attention', lane='Interventions', week='2026-10-26', origin='test', findings='Unverified causal claim')
        work = {'DOI': lead['doi'], 'type': 'journal-article', 'title': [lead['title']], 'published': {'date-parts': [[2026, 10, 20]]}}
        record = verify(lead, dt.date(2026, 10, 26), lambda url: {'message': work})
        self.assertNotIn('findings', record)
        self.assertEqual(record['abstract_text'], '')

    @patch('builtins.print', lambda *args, **kwargs: None)
    @patch.dict('os.environ', {'GITHUB_SHA': ''})
    def test_queue_survives_next_collection_and_clears_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data = root / 'data'; data.mkdir()
            def save(name, obj):
                (data / name).write_text(json.dumps(obj), encoding='utf-8')
            save('public-featured-issue.json', {'edition_date': '2026-10-18'})
            for date in ['2026-10-26', '2026-11-02']:
                save('public-weekly.json', {'run': {'date': date}, 'items': []})
                save('public-issue.json', {'edition_date': date, 'status': 'awaiting_editorial_review', 'sources': []})
                status = build(root)
            self.assertEqual(status['pending_editorial_dates'], ['2026-10-26', '2026-11-02'])
            self.assertEqual(status['featured_issue_date'], '2026-10-18')
            (data / 'approved-issues').mkdir()
            save('approved-issues/2026-10-26.json', {'status': 'published'})
            self.assertEqual(build(root)['pending_editorial_dates'], ['2026-11-02'])

"""Strict date membership survives publication, lineage and editorial padding."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from collection_window import window_metadata
import build_public
import build_issue
import build_newsletter


def paper(day='2026-10-28',doi='10.9999/current'):
    return {'kind':'scholarly','doi':doi,'url':'https://example.org/article','title':'Generative AI and cognitive attention in learning',
            'venue':'Computers in Human Behavior','published':day,'source':'Crossref',
            'publication_date_provenance':{'status':'day_known','source':'Crossref publisher metadata','field':'published-online','value':day},
            'abstract_text':'This study investigates generative AI and cognitive attention among students. The results showed differences in reported focus but cannot establish lasting learning.',
            'reading':{'level':'abstract','findings':'The results showed differences in reported focus but cannot establish lasting learning.'},
            'first_seen':'2026-11-02','lane':'AI & cognition'}


class WeeklyPublicationBoundaryTests(unittest.TestCase):
    def test_strict_week_never_pads_with_older_context(self):
        row=paper();old=paper('2026-09-01','10.9999/old')
        weekly={'run':{'date':'2026-11-02','publication_window':window_metadata('2026-11-02')},'items':[row]}
        packet=build_public.editorial_shelf(weekly,[row,old],minimum=8)
        self.assertEqual(packet['items'],[{**row,'editorial_role':'publication_week'}])
        self.assertEqual(packet['run']['context_source_count'],0)
        self.assertIn('no older context',packet['run']['editorial_selection_note'])

    def test_outside_dates_and_changed_window_fail_closed(self):
        for day in ('2026-10-25','2026-11-02','2026-10',''):
            week={'run':{'date':'2026-11-02','publication_window':window_metadata('2026-11-02')},'items':[paper(day)]}
            with self.subTest(day=day),self.assertRaises(ValueError):build_public.editorial_shelf(week,[])
        week={'run':{'date':'2026-11-02','publication_window':{**window_metadata('2026-11-02'),'from':'2026-10-25'}},'items':[]}
        with self.assertRaises(ValueError):build_public.editorial_shelf(week,[])

    def test_new_explainer_cannot_reintroduce_older_original_paper(self):
        row=paper('2026-09-01','10.9999/old')
        incoming={'title':'Current explainer','url':'https://example.org/explainer','companion_to':row['doi'],'published':'2026-10-28'}
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);(data/'library.json').write_text(json.dumps([row]))
            (data/'weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02','publication_window':window_metadata('2026-11-02')},'items':[incoming]}))
            with patch.object(build_public,'DATA',data),patch.object(build_public,'prepare',side_effect=lambda rows:rows):
                selected,weekly=build_public.build()
            self.assertEqual(len(selected),1) # Historical library remains accessible.
            self.assertEqual(weekly['items'],[])
            self.assertEqual(json.loads((data/'editorial-weekly.json').read_text())['items'],[])

    def test_dated_public_projection_without_window_rejects_old_membership_and_padding(self):
        current = paper()
        old = paper('2026-08-13', '10.9999/old')
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / 'library.json').write_text(json.dumps([current, old]))
            (data / 'weekly.json').write_text(json.dumps({
                'run': {'date': '2026-11-02'}, 'items': [current, old]}))
            with patch.object(build_public, 'DATA', data), patch.object(build_public, 'prepare', side_effect=lambda rows: rows):
                selected, weekly = build_public.build()
            shelf = json.loads((data / 'editorial-weekly.json').read_text())
        self.assertEqual({x['doi'] for x in selected}, {current['doi'], old['doi']})
        self.assertEqual([x['doi'] for x in weekly['items']], [current['doi']])
        self.assertEqual(weekly['run']['publication_window'], window_metadata('2026-11-02'))
        self.assertEqual([x['doi'] for x in shelf['items']], [current['doi']])
        self.assertEqual(shelf['run']['context_source_count'], 0)

    def test_saved_queue_retains_window_and_publication_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / 'editorial-queue').mkdir()
            source = dict(paper(), id='10.9999/current', reading_level='abstract')
            (data / 'editorial-queue/2026-11-02.json').write_text(json.dumps({
                'publication_window': window_metadata('2026-11-02'), 'sources': [source]}))
            (data / 'public-weekly.json').write_text(json.dumps({'run': {'date': '2026-11-09'}, 'items': []}))
            (data / 'issue-editorial.json').write_text('{}')
            with patch.object(build_issue, 'DATA', data):
                saved = build_issue.build('2026-11-02')
        self.assertEqual(saved['publication_window'], window_metadata('2026-11-02'))
        self.assertEqual(saved['sources'][0]['publication_date_provenance'], source['publication_date_provenance'])

    def test_saved_queue_cannot_publish_unverified_or_older_sources(self):
        for source in (paper('2026-08-13'), dict(paper(), publication_date_provenance={})):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp:
                data = Path(tmp)
                (data / 'editorial-queue').mkdir()
                (data / 'editorial-queue/2026-11-02.json').write_text(json.dumps({'sources': [source]}))
                (data / 'public-weekly.json').write_text(json.dumps({'run': {'date': '2026-11-09'}, 'items': []}))
                (data / 'issue-editorial.json').write_text('{}')
                with patch.object(build_issue, 'DATA', data), self.assertRaises(ValueError):
                    build_issue.build('2026-11-02')

    def test_saved_queue_cannot_claim_a_different_publication_window(self):
        for mutation in ({'from': '2026-10-25'}, {'to': '2026-11-02'}, {'timezone': 'US/Pacific'}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                data = Path(tmp)
                (data / 'editorial-queue').mkdir()
                (data / 'editorial-queue/2026-11-02.json').write_text(json.dumps({
                    'publication_window': dict(window_metadata('2026-11-02'), **mutation), 'sources': [paper()]}))
                (data / 'public-weekly.json').write_text(json.dumps({'run': {'date': '2026-11-09'}, 'items': []}))
                (data / 'issue-editorial.json').write_text('{}')
                with patch.object(build_issue, 'DATA', data), self.assertRaises(ValueError):
                    build_issue.build('2026-11-02')

    def test_existing_published_issue_not_rewritten_by_new_window_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);(data/'approved-issues').mkdir()
            archive={'edition_date':'2026-11-02','status':'published','headline':'Historical approved issue','sources':[]}
            (data/'approved-issues/2026-11-02.json').write_text(json.dumps(archive))
            (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02','publication_window':window_metadata('2026-11-02')},'items':[paper()]}))
            (data/'issue-editorial.json').write_text(json.dumps({'2026-11-02':{'signals':[{'sources':['Old source not in current window']} ]}}))
            with patch.object(build_issue,'DATA',data):current=build_issue.build()
            self.assertEqual(current['status'],'awaiting_publication')
            self.assertEqual(current['publication_window'],window_metadata('2026-11-02'))
            self.assertEqual(json.loads((data/'public-featured-issue.json').read_text()),archive)
            self.assertEqual(json.loads((data/'approved-issues/2026-11-02.json').read_text()),archive)

    def test_newsletter_and_issue_rss_explain_original_publication_window(self):
        issue={'edition_date':'2026-11-02','headline':'Synthetic','publication_window':window_metadata('2026-11-02')}
        html=build_newsletter.opening(issue);rss=build_newsletter.rss_content(issue)
        for rendered in (html,rss):
            self.assertIn('2026-10-26 through 2026-11-01 (UTC)',rendered)
            self.assertIn('Older background sources are not included',rendered)
        self.assertEqual(build_newsletter.publication_scope({'edition_date':'2026-10-26'}),'')

    def test_workflows_separate_weekly_retrieval_and_historical_backfill(self):
        refresh=(ROOT/'.github/workflows/refresh.yml').read_text()
        self.assertIn("if: env.MODE == 'backfill'\n        run: python scripts/seed_historical.py",refresh)
        self.assertIn("if: env.MODE != 'backfill'\n        run: python scripts/build_weekly.py",refresh)
        self.assertIn("if: env.MODE == 'weekly'\n        run: python scripts/brief_intake.py",refresh)
        workflow=(ROOT/'.github/workflows/weekly-source-acquisition.yml').read_text()
        self.assertIn('scripts/collect_weekly_sources.py --limit 12 --time-budget 540',workflow)
        self.assertIn("('from', 'to', 'timezone')",workflow)
        self.assertNotIn('secrets.',workflow)
        self.assertIn('git add data/weekly-source-acquisition.json',workflow)
        self.assertIn('validate_state(state)',workflow)
        self.assertIn("if: always() && steps.checkpoint.outputs.valid == 'true'",workflow)
        self.assertIn('for attempt in 1 2 3',workflow)
        self.assertIn('actions/upload-artifact@v7.0.2',workflow)
        self.assertIn('validated-weekly-acquisition.json',workflow)
        self.assertIn("|| 'observatory-index' }}",workflow)
        self.assertNotIn("|| 'observatory-weekly-acquisition' }}",workflow)

if __name__=='__main__':unittest.main()

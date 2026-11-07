"""Original summaries cannot turn older sources into this week's evidence."""
from copy import deepcopy
from datetime import date
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from test_original_readings import record, accepted, approve, article_screen
import original_readings as original
import build_public
import build_issue
import compose_issue
import feed
from collection_window import previous_week, weekly_eligible, window_metadata
from condense_readings import annotate


class OriginalWeeklyBoundaryTests(unittest.TestCase):
    def row(self):
        row=record();row['original_reading']=accepted()
        return annotate(row)

    def arxiv(self):
        row=self.row();ident='2610.12345';pinned=ident+'v1'
        row.update(doi='',url='https://arxiv.org/abs/'+ident)
        row['publication_date_provenance']={
            'basis':'arxiv_first_submitted','status':'day_known','field':'published',
            'source':'Official arXiv Atom metadata','value':row['published'],'raw':row['published']+'T12:00:00Z',
            'requested_id':pinned,'version_url':'https://arxiv.org/abs/'+pinned,
            'source_id':'http://arxiv.org/abs/'+pinned,
            'source_url':'https://export.arxiv.org/api/query?id_list='+pinned}
        n=accepted();n.update(doi='',record_url=row['url']);n['source'].update(
            url='https://arxiv.org/pdf/'+pinned,source_doi='',version='arxiv_preprint_v1')
        article_screen(n,row);row['original_reading']=approve(n)
        return annotate(row)

    def test_checked_same_doi_source_still_enters_week(self):
        self.assertTrue(weekly_eligible(self.row(),*previous_week('2026-11-02')))

    def test_old_working_version_is_library_only_and_cannot_pad_week(self):
        row=record();note=accepted();note['source'].update(
            source_doi='10.9999/working-paper',related_journal_doi=row['doi'],version='working_paper')
        article_screen(note,row);approve(note)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';data.mkdir();manifest=data/'original-readings.json'
            manifest.write_text(json.dumps({'articles':[note]}))
            (data/'library.json').write_text(json.dumps([row]))
            (data/'weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[row]}))
            with patch.object(original,'MANIFEST',manifest),patch.object(build_public,'DATA',data):
                library,weekly=build_public.build()
                self.assertTrue(library[0]['reading']['original_summary'])
                self.assertEqual(weekly['items'],[])
                self.assertEqual(json.loads((data/'editorial-weekly.json').read_text())['items'],[])
                with patch.object(feed,'ROOT',root),patch.object(feed,'DATA',data):
                    self.assertEqual(feed.build(),0)

    def test_arxiv_v1_identity_and_provenance_are_bound(self):
        row=self.arxiv();bounds=previous_week('2026-11-02')
        for path in ('abs','pdf','html'):
            n=deepcopy(row);n['original_reading']['source']['url']='https://arxiv.org/'+path+'/2610.12345v1'
            approve(n['original_reading']);self.assertTrue(weekly_eligible(n,*bounds))
        for url in ('https://arxiv.org/pdf/2610.12345v2','https://arxiv.org/pdf/2610.67890v1'):
            n=deepcopy(row);n['original_reading']['source']['url']=url;approve(n['original_reading'])
            self.assertTrue(original.eligible(n['original_reading'],n))
            self.assertFalse(weekly_eligible(n,*bounds))
        for key in ('requested_id','version_url','source_id','source_url','raw'):
            n=deepcopy(row);n['publication_date_provenance'].pop(key)
            self.assertFalse(weekly_eligible(n,*bounds),key)

    def test_arxiv_explicit_version_labels_cannot_contradict_source(self):
        for changed in ('url', 'doi', 'version'):
            row=self.arxiv();note=row['original_reading']
            if changed=='url':row['url']+='v2';note['record_url']=row['url']
            if changed=='doi':
                row['doi']='10.48550/arXiv.2610.12345v2';note['doi']=row['doi'];note['source']['source_doi']=row['doi']
            if changed=='version':note['source']['version']='arxiv_preprint_v2'
            article_screen(note,row);approve(note)
            self.assertTrue(original.eligible(note,row))
            self.assertFalse(weekly_eligible(row,*previous_week('2026-11-02')),changed)

    def test_doi_less_distinct_url_needs_source_version_evidence(self):
        row=record();row['doi']='';n=accepted();n['doi']='';n['source']['source_doi']=''
        n['source']['url']=row['url'];row['original_reading']=approve(n)
        self.assertTrue(weekly_eligible(row,*previous_week('2026-11-02')))
        n['source']['url']='https://example.org/different-edition';approve(n)
        self.assertTrue(original.eligible(n,row))
        self.assertFalse(weekly_eligible(row,*previous_week('2026-11-02')))

    def test_invalid_source_identifiers_and_arxiv_paths_fail_closed(self):
        for url in ('https://www.arxiv.org/pdf/2610.12345','https://arxiv.org/not-a-paper-v1',
                    'https://arxiv.org/pdf/2610.12345v0','https://arxiv.org./pdf/2610.12345',
                    'https://www.arxiv.org./pdf/2610.12345'):
            n=accepted();n['source']['url']=url;approve(n)
            self.assertFalse(original.eligible(n,record()),url)
        for key in ('source_doi','related_journal_doi'):
            n=accepted();n['source'].update(version='working_paper',related_journal_doi=n['doi'])
            n['source'][key]='not-a-doi';approve(n)
            self.assertFalse(original.eligible(n,record()),key)

    def test_synthesis_and_rss_reject_bad_dates_before_model_or_output(self):
        for mutation in ('old','missing','conflicting','wrong_window','working_version'):
            row=self.row();n=row['original_reading'];window=window_metadata('2026-11-02')
            if mutation=='old':row['published']='2026-09-01';row['publication_date_provenance']['value']=row['published']
            if mutation=='missing':row.pop('publication_date_provenance')
            if mutation=='conflicting':row['publication_date_provenance']['status']='unresolved'
            if mutation=='wrong_window':window['from']='2026-10-25'
            if mutation=='working_version':n['source'].update(source_doi='10.9999/older',related_journal_doi=row['doi'],version='working_paper');article_screen(n,row);approve(n)
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);data=root/'data';data.mkdir();manifest=data/'original-readings.json'
                manifest.write_text(json.dumps({'articles':[n]}))
                (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02','publication_window':window},'items':[row]}))
                (data/'issue-editorial.json').write_text('{}');model=Mock()
                with patch.object(original,'MANIFEST',manifest):
                    with self.assertRaises(ValueError):compose_issue.compose(root,model,today=date(2026,11,7))
                    model.create_chat_completion.assert_not_called()
                    with patch.object(feed,'ROOT',root),patch.object(feed,'DATA',data):
                        if mutation=='wrong_window':
                            with self.assertRaises(ValueError):feed.build()
                        else:self.assertEqual(feed.build(),0)
                self.assertEqual((data/'issue-editorial.json').read_text(),'{}')

    def test_saved_queue_cannot_strip_original_marker_to_bypass_receipt(self):
        row=self.row();src={'id':row['doi'],'title':row['title'],'kind':'scholarly','url':row['url'],
            'published':row['published'],'publication_date_provenance':row['publication_date_provenance'],
            'reading_level':'full_text',**build_issue.checked_source_metadata(row)}
        src.pop('original_summary')
        with self.assertRaisesRegex(ValueError,'marker is incomplete'):build_issue.resolve_queued_original(src)

    def test_current_register_change_requires_rebuilt_shelf_before_synthesis(self):
        for existing in (False,True):
            row=self.row() if existing else record()
            note=accepted();note['source'].update(source_doi='10.9999/older',
                related_journal_doi=row['doi'],version='working_paper');article_screen(note,row);approve(note)
            with self.subTest(existing=existing),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);data=root/'data';data.mkdir();manifest=data/'original-readings.json'
                manifest.write_text(json.dumps({'articles':[note]}))
                (data/'library.json').write_text(json.dumps([row]))
                (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[row]}))
                (data/'issue-editorial.json').write_text('{}');model=Mock()
                with patch.object(original,'MANIFEST',manifest):
                    with self.assertRaisesRegex(ValueError,'before synthesis'):
                        compose_issue.compose(root,model,today=date(2026,11,7))
                model.create_chat_completion.assert_not_called()
                self.assertEqual((data/'issue-editorial.json').read_text(),'{}')

    def test_preflight_withholds_thin_week_without_inference_or_publication(self):
        row=self.row()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';data.mkdir();manifest=data/'original-readings.json'
            manifest.write_text(json.dumps({'articles':[row['original_reading']]}))
            (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[row]}))
            (data/'issue-editorial.json').write_text('{}')
            env={'GITHUB_OUTPUT':str(root/'output'),'GITHUB_STEP_SUMMARY':str(root/'summary')}
            with patch.object(original,'MANIFEST',manifest),patch.dict(os.environ,env):
                result=compose_issue.check(root,today=date(2026,11,7))
            self.assertFalse(result['needed']);self.assertEqual(result['status'],'awaiting_substantive_sources')
            self.assertEqual(result['eligible_sources'],1)
            self.assertIn('needed=false',(root/'output').read_text())
            self.assertIn('last published edition remains visible',(root/'summary').read_text())
            self.assertEqual((data/'issue-editorial.json').read_text(),'{}')
            self.assertFalse((data/'edition-audits').exists())


if __name__=='__main__':unittest.main()

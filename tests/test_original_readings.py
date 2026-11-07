"""Synthetic fixtures only; no private reading draft is approved by these tests."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import original_readings as original
from build_readings import make_note
from condense_readings import annotate
import build_public
import compose_issue
import feed
import source_audit
import build_issue
import build_newsletter
from build_visuals import visual_spec


def record():
    return {'kind':'scholarly','doi':'10.9999/synthetic-attention','url':'https://example.org/article',
            'title':'Generative AI and attention: a synthetic fixture',
            'venue':'Computers in Human Behavior','published':'2026-10-30','lane':'AI & cognition',
            'publication_date_provenance':{'status':'day_known','basis':'editor_verified_original_publication_date','value':'2026-10-30'},
            'abstract_text':'This synthetic abstract describes an experiment about generative AI and attention. The results showed differences in reported effort but not retention.',
            'analysis':{'fulltext_url':'https://example.org/licensed.xml','license':'CC BY',
                        'provenance':'Machine-extracted licensed XML sections',
                        'methods':'ORIGINAL MACHINE METHODS','results':'ORIGINAL MACHINE RESULTS',
                        'discussion':'ORIGINAL MACHINE DISCUSSION','limitations':'ORIGINAL MACHINE LIMITATIONS'}}


def article_screen(note, row):
    from checked_reading_types import record_digest
    note['article_screen'] = {
        'record_sha256': record_digest(row), 'decision': 'acceptable',
        'reviewer': 'synthetic article screener', 'checked_on': '2026-11-06',
        'topic_fit': 'Synthetic article examines human attention with generative AI tools.',
        'methodological_assessment': 'Synthetic short comparison has limited scope and uncertain generalization.',
        'limitations_assessment': 'Synthetic design does not establish strong causal or lasting effects.',
        'peer_review_claimed': False, 'strong_causal_evidence_claimed': False}
    return note


def approve(note):
    note['review']['payload_sha256']=original.payload_digest(note)
    note['publication']['payload_sha256']=original.publication_digest(note)
    return note


def accepted():
    r=record()
    return approve({'id':'synthetic-only','doi':r['doi'],'record_url':r['url'],'title':r['title'],
      'author':'synthetic author',
      'source':{'url':'https://example.org/article-v2.pdf','version':'published_version', 'format':'pdf',
                'source_doi':r['doi'],'related_journal_doi':'','journal_version_equivalence_claimed':False,
                'source_sha256':'a'*64,'review_scope':'Synthetic whole article text; figures and supplements not inspected.'},
      'summary':{
        'idea':'An easier task did not establish more lasting learning.',
        'explain':'This fictional fixture separates perceived effort from performance and long term learning.',
        'approach':'A synthetic randomized experiment compared two study tools during one short session.',
        'finding':'The fictional groups reported different effort, while the retention comparison was inconclusive.',
        'interpretation':'The synthetic authors interpret these results as a distinction between experience and learning.',
        'limitation':'The short session cannot establish lasting effects, and the fictional comparison is not equivalence evidence.'},
      'evidence':{key:[{'section':'Synthetic '+key,'page':2}] for key in original.FIELDS},
      'rights':{'original_paraphrases_only':True,'source_text_redistribution':False,
                'license_context':'Synthetic metadata, no article prose.'},
      'quality':{'decision':'acceptable','note':'Synthetic source-specific assessment for regression testing only.'},
      'review':{'kind':'ai_source_check','status':'passed','reviewer':'synthetic checker','checked_on':'2026-11-06','payload_sha256':''},
      'publication':{'decision':'approved','approved_by':'synthetic fixture only','approved_on':'2026-11-07','payload_sha256':''}})


class OriginalSummaryTests(unittest.TestCase):
    def test_attach_beside_machine_excerpts_without_changing_identity_or_counts(self):
        row=record(); old=deepcopy(row)
        self.assertEqual(original.apply([row],{'articles':[accepted()]}),1)
        self.assertEqual(row['analysis'],old['analysis'])
        self.assertEqual(row['doi'],old['doi']);self.assertEqual(row['url'],old['url'])
        self.assertNotIn('full_text_extracted',row)
        row['reading']=make_note(row);projected=annotate(row)
        self.assertEqual(projected['reading']['digest']['idea'],accepted()['summary']['idea'])
        self.assertEqual(projected['reading']['digest']['status'],original.STATUS)
        self.assertEqual(projected['reading']['methods'],accepted()['summary']['approach'])
        self.assertTrue(build_public.readable(projected))
        self.assertEqual(visual_spec(projected)['kind'],'illustration_only')
        self.assertIn('not human review',projected['reading']['notice'])
        self.assertNotIn('Full publisher',projected['reading']['notice'])

    def test_original_summary_needs_no_machine_extraction(self):
        row=record();row.pop('analysis');row.pop('abstract_text')
        original.apply([row],{'articles':[accepted()]})
        row['reading']=make_note(row)
        self.assertTrue(build_public.readable(row));self.assertEqual(row['reading']['sample'],'')

    def test_every_hold_and_missing_receipt_fails_closed(self):
        for section,key,value in [('quality','decision','hold'),('quality','decision','review_needed'),
                ('review','status','revise'),('review','kind','human_review'),
                ('publication','decision','pending'),('rights','source_text_redistribution',True),
                ('source','journal_version_equivalence_claimed',True)]:
            n=accepted();n[section][key]=value;approve(n)
            with self.subTest(section=section,key=key,value=value):self.assertFalse(original.eligible(n,record()))
        for field in ('review','publication','quality','evidence','source'):
            n=accepted();n.pop(field)
            self.assertFalse(original.eligible(n,record()))

    def test_changed_content_or_source_invalidates_review(self):
        for section,key,value in [('summary','finding','Changed unsupported finding.'),('source','version','preprint_v3'),
                ('source','source_sha256','b'*64),('quality','note','Changed quality assessment.'),
                ('rights','license_context','Changed rights.')]:
            n=accepted();n[section][key]=value
            self.assertFalse(original.eligible(n,record()))
        n=accepted();n['evidence']['finding'][0]['page']=4
        self.assertFalse(original.eligible(n,record()))

    def test_recheck_does_not_reuse_old_publication_acceptance(self):
        n=accepted();n['review']['reviewer']='different checker'
        self.assertFalse(original.eligible(n,record()))

    def test_author_cannot_self_attest_as_separate_checker(self):
        n=accepted();n['review']['reviewer']='  SYNTHETIC   AUTHOR ';approve(n)
        self.assertFalse(original.eligible(n,record()))

    def test_bad_source_urls_and_locators_fail_closed(self):
        for url in ('http://example.org/a','https://user:password@example.org/a','https://example.org/a?key=secret',
                    'https://example.org/a#token','https://127.0.0.1/a','https://localhost/a','https://example.org/\\bad'):
            n=accepted();n['source']['url']=url;approve(n)
            self.assertFalse(original.eligible(n,record()),url)
        for page in (True,0,-1,'2'):
            n=accepted();n['evidence']['finding'][0]['page']=page;approve(n)
            self.assertFalse(original.eligible(n,record()))
        n=accepted();n['evidence']['finding'][0]['source_quote']='must not ship';approve(n)
        self.assertFalse(original.eligible(n,record()))

    def test_identity_mismatch_duplicate_and_unversioned_arxiv(self):
        n=accepted();n['doi']='10.9999/other';approve(n)
        self.assertFalse(original.eligible(n,record()))
        n=accepted();n['title']='A different paper';approve(n)
        self.assertFalse(original.eligible(n,record()))
        n=accepted();n['source']['url']='https://arxiv.org/pdf/2601.12345';approve(n)
        self.assertFalse(original.eligible(n,record()))
        row=record();self.assertEqual(original.apply([row],{'articles':[accepted(),accepted()]}),0)

    def test_working_paper_doi_not_silently_promoted_to_journal_version(self):
        n=accepted();n['source'].update(source_doi='10.9999/working-paper',related_journal_doi=n['doi'],version='working_paper_not_journal_version');article_screen(n,record());approve(n)
        row=record();row['original_reading']=n
        self.assertTrue(original.eligible(n,row))
        note=make_note(row)
        self.assertEqual(note['source_doi'],'10.9999/working-paper')
        self.assertEqual(note['related_journal_doi'],row['doi'])
        n['source']['version']='published_version';approve(n)
        self.assertFalse(original.eligible(n,row))

    def test_doi_less_exact_source_record(self):
        row=record();row['doi']=''
        n=accepted();n['doi']='';n['source']['source_doi']='';approve(n)
        self.assertTrue(original.eligible(n,row))
        row['url']='https://example.org/unrelated'
        self.assertFalse(original.eligible(n,row))

    def test_revocation_strips_old_prose_but_preserves_machine_source(self):
        row=record();original.apply([row],{'articles':[accepted()]});row=annotate(row)
        self.assertTrue(row['reading']['original_summary'])
        self.assertEqual(original.apply([row],{'articles':[]}),0)
        result=annotate(row)
        self.assertNotIn('original_reading',result)
        self.assertNotIn(accepted()['summary']['idea'],json.dumps(result))
        self.assertEqual(result['analysis'],record()['analysis'])

    def test_direct_stale_snapshot_is_rebuilt_at_downstream_boundaries(self):
        row=record();row['original_reading']=accepted();row=annotate(row)
        row['original_reading']['quality']['decision']='hold'
        safe=original.public_record(row)
        self.assertNotIn('original_reading',safe)
        self.assertNotIn(accepted()['summary']['idea'],json.dumps(safe))
        self.assertNotIn(accepted()['summary']['idea'],json.dumps(compose_issue.evidence([row])))

    def test_cached_marker_without_original_is_never_authority(self):
        row=record();row['reading']=make_note({**row,'original_reading':accepted()})
        self.assertFalse(build_public.readable(row))
        safe=annotate(row)
        self.assertNotIn(accepted()['summary']['idea'],json.dumps(safe))

    def test_weekly_evidence_keeps_exact_source_review_and_version(self):
        row=record();row['original_reading']=accepted();row=annotate(row)
        with tempfile.TemporaryDirectory() as tmp:
            manifest=Path(tmp)/'manifest.json';manifest.write_text(json.dumps({'articles':[accepted()]}))
            with patch.object(original,'MANIFEST',manifest):
                packet=compose_issue.evidence([row])[0]
        self.assertEqual(packet['source_url'],accepted()['source']['url'])
        self.assertEqual(packet['review_kind'],'ai_source_check')
        self.assertIn('not human review',packet['review_label'])
        self.assertNotIn('ORIGINAL MACHINE',packet['evidence'])

    def test_actual_public_projection_and_rss_preserve_or_withhold(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';data.mkdir()
            row=record();row['reading']=make_note(row)
            (data/'library.json').write_text(json.dumps([row]))
            (data/'weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[row]}))
            manifest=data/'original-readings.json';manifest.write_text(json.dumps({'articles':[accepted()]}))
            with patch.object(build_public,'DATA',data),patch.object(original,'MANIFEST',manifest):
                selected,weekly=build_public.build()
                self.assertEqual(len(selected),1)
                self.assertEqual(selected[0]['analysis'],row['analysis'])
                self.assertEqual(weekly['run']['original_summary_count'],1)
                self.assertEqual(weekly['run']['machine_sections_count'],1)
                with patch.object(feed,'ROOT',Path(tmp)),patch.object(feed,'DATA',data):feed.build()
                rss=ET.parse(Path(tmp)/'feed.xml').getroot();item=rss.find('./channel/item')
                self.assertIn('AI source-checked summary',item.findtext('description'))
                self.assertIn('not human review',item.findtext('description'))
                self.assertEqual(item.find('source').get('url'),accepted()['source']['url'])
                hold=accepted();hold['quality']['decision']='hold';approve(hold)
                manifest.write_text(json.dumps({'articles':[hold]}))
                selected,weekly=build_public.build()
                for file in ('public-library.json','public-weekly.json','editorial-weekly.json'):
                    self.assertNotIn(accepted()['summary']['idea'],(data/file).read_text())
                self.assertEqual(weekly['run']['original_summary_count'],0)
                with patch.object(feed,'ROOT',Path(tmp)),patch.object(feed,'DATA',data):feed.build()
                self.assertNotIn(accepted()['summary']['idea'],(Path(tmp)/'feed.xml').read_text())

    def test_quality_screen_still_holds_unverified_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);row=record();row['venue']='Unverified venue'
            (data/'library.json').write_text(json.dumps([row]))
            (data/'weekly.json').write_text(json.dumps({'run':{},'items':[row]}))
            with patch.object(build_public,'DATA',data),patch.object(original,'MANIFEST',data/'notes.json'):
                (data/'notes.json').write_text(json.dumps({'articles':[accepted()]}))
                selected,_=build_public.build()
            self.assertEqual(selected,[])

    def test_case_sensitive_url_paths_unknown_versions_and_impossible_dates(self):
        row=record();row.update(doi='',url='https://example.org/Article')
        n=accepted();n.update(doi='',record_url='https://example.org/article');n['source']['source_doi']='';approve(n)
        self.assertFalse(original.eligible(n,row))
        for version in ('UNKNOWN','unknown ','Unspecified'):
            n=accepted();n['source']['version']=version;approve(n)
            self.assertFalse(original.eligible(n,record()))
        for section,key,value in [('review','checked_on','2099-01-01'),('publication','approved_on','2099-01-02'),('publication','approved_on','2000-01-01')]:
            n=accepted();n[section][key]=value;approve(n)
            self.assertFalse(original.eligible(n,record()))

    def test_audit_does_not_count_paraphrases_as_extracted_source(self):
        row=record();row.pop('analysis');row['original_reading']=accepted();row=annotate(row)
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);(data/'public-library.json').write_text(json.dumps([row]))
            with patch.object(source_audit,'DATA',data):report=source_audit.report()
        self.assertEqual(report['full_text_extracted'],0)
        self.assertEqual(report['original_summaries'],1)
        self.assertEqual(report['full_text_reading_depth'],1)

    def test_library_and_archived_newsletter_keep_working_version_not_new_week(self):
        row=record();n=accepted()
        n['source'].update(source_doi='10.9999/working-paper',related_journal_doi=n['doi'],version='working_paper_not_journal_version');article_screen(n,record());approve(n)
        row['original_reading']=n;row=annotate(row)
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);manifest=data/'manifest.json';manifest.write_text(json.dumps({'articles':[n]}))
            (data/'library.json').write_text(json.dumps([row]))
            (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[row]}))
            (data/'issue-editorial.json').write_text('{}')
            with patch.object(original,'MANIFEST',manifest),patch.object(build_issue,'DATA',data):
                with self.assertRaisesRegex(ValueError,'previous-week'):build_issue.build()
        self.assertTrue(original.eligible(n,row))
        issue={'sources':[{'id':row['doi'],'url':row['url'],**build_issue.checked_source_metadata(row)}]}
        shelf=issue['sources'][0]
        self.assertEqual(shelf['source_url'],n['source']['url'])
        self.assertEqual(shelf['source_doi'],'10.9999/working-paper')
        self.assertEqual(shelf['related_journal_doi'],row['doi'])
        self.assertEqual(shelf['review_kind'],'ai_source_check')
        html=build_newsletter.source_links(issue,[row['doi']])
        self.assertIn(n['source']['url'],html);self.assertIn('working_paper_not_journal_version',html)
        self.assertIn('not human review',html);self.assertIn('Related journal DOI (different version)',html)
        issue.update(headline='Synthetic issue',signals=[{'source_ids':[row['doi']]}])
        self.assertIn(n['source']['url'],build_newsletter.rss_content(issue))

    def test_issue_rejects_revoked_or_changed_original_snapshot(self):
        row=record();row.pop('analysis');row.pop('abstract_text');row['original_reading']=accepted();row=annotate(row)
        for articles in ([],[approve({**accepted(),'quality':{'decision':'acceptable','note':'Changed source assessment.'}})]):
            with tempfile.TemporaryDirectory() as tmp:
                data=Path(tmp);manifest=data/'manifest.json';manifest.write_text(json.dumps({'articles':articles}))
                (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[row]}))
                (data/'issue-editorial.json').write_text('{}')
                with patch.object(original,'MANIFEST',manifest),patch.object(build_issue,'DATA',data):
                    with self.assertRaisesRegex(ValueError,'revalidate the issue'):build_issue.build()
                self.assertFalse((data/'public-issue.json').exists())

    def test_unpublished_queue_needs_current_bound_original_receipt(self):
        row=record();row['original_reading']=accepted();row=annotate(row)
        source={'id':row['doi'],'title':row['title'],'kind':'scholarly','url':row['url'],
                'reading_level':'full_text','published':row['published'],
                'publication_date_provenance':row['publication_date_provenance'],
                **build_issue.checked_source_metadata(row)}
        for articles,allowed in (([],False),([accepted()],True)):
            with tempfile.TemporaryDirectory() as tmp:
                data=Path(tmp);(data/'editorial-queue').mkdir()
                manifest=data/'manifest.json';manifest.write_text(json.dumps({'articles':articles}))
                (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[]}))
                (data/'issue-editorial.json').write_text('{}')
                (data/'editorial-queue/2026-11-02.json').write_text(json.dumps({'sources':[source]}))
                with patch.object(original,'MANIFEST',manifest),patch.object(build_issue,'DATA',data):
                    if allowed:self.assertTrue(build_issue.build('2026-11-02')['sources'][0]['original_summary'])
                    else:
                        with self.assertRaisesRegex(ValueError,'revalidate the issue'):build_issue.build('2026-11-02')

    def test_current_register_revokes_cached_weekly_and_rss(self):
        row=record();row['original_reading']=accepted();row=annotate(row)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest=root/'manifest.json';manifest.write_text(json.dumps({'articles':[]}))
            (root/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[row]}))
            with patch.object(original,'MANIFEST',manifest):
                self.assertNotIn(accepted()['summary']['idea'],json.dumps(compose_issue.evidence([row])))
                with patch.object(feed,'ROOT',root),patch.object(feed,'DATA',root):feed.build()
                self.assertNotIn(accepted()['summary']['idea'],(root/'feed.xml').read_text())

    def test_conceptual_paper_cannot_promote_empirical_results(self):
        row=record();row['research_type']='conceptual_framework'
        n=accepted();self.assertFalse(original.eligible(n,row))
        n['summary']['finding']='';approve(n)
        self.assertTrue(original.eligible(n,row))
        row['original_reading']=n;reading=make_note(row)
        self.assertEqual(reading['findings'],'');self.assertFalse(reading['reported_findings'])

    def test_accepted_register_change_rechecks_weekly_edition(self):
        workflow=(ROOT/'.github/workflows/weekly-edition.yml').read_text()
        push=workflow.split('  push:',1)[1].split('  pull_request:',1)[0]
        pull_request=workflow.split('  pull_request:',1)[1].split('  # Recovery',1)[0]
        for trigger in (push,pull_request):
            self.assertIn("'data/original-readings.json'",trigger)
        self.assertIn("if: github.event_name != 'pull_request'",workflow)
        self.assertIn('python scripts/compose_issue.py --check',workflow)
        self.assertIn('python scripts/build_public.py',workflow)
        self.assertLess(workflow.index('python scripts/build_public.py'),workflow.index('python scripts/compose_issue.py --check'))
        self.assertNotIn('update.py',workflow)
        self.assertNotIn('discover_editorial.py',workflow)

    def test_public_manifest_contains_only_accepted_content_bound_readings(self):
        # Real accepted readings arrive separately from the adapter. A metadata
        # change may quarantine an old receipt, but no draft/hold belongs here.
        notes=json.loads((ROOT/'data/original-readings.json').read_text())['articles']
        self.assertEqual(len({n['id'] for n in notes}),len(notes))
        self.assertEqual(len({original.identifier(n) for n in notes}),len(notes))
        for note in notes:
            with self.subTest(id=note['id']):
                self.assertEqual(note['review']['kind'],'ai_source_check')
                self.assertEqual(note['review']['status'],'passed')
                self.assertEqual(note['review']['payload_sha256'],original.payload_digest(note))
                self.assertEqual(note['publication']['decision'],'approved')
                self.assertTrue(note['publication']['approved_by'])
                self.assertGreaterEqual(note['publication']['approved_on'],note['review']['checked_on'])
                self.assertEqual(note['publication']['payload_sha256'],original.publication_digest(note))
                self.assertTrue(note['rights']['original_paraphrases_only'])
                self.assertFalse(note['rights']['source_text_redistribution'])

if __name__=='__main__':unittest.main()

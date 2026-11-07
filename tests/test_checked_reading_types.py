"""Synthetic receipt adapters: no real article draft or approval is committed."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_original_readings import record, accepted, approve, article_screen
import original_readings as original
from checked_reading_types import COMMENTARY_FIELDS, record_digest
from source_quality import screen
from build_readings import make_note
from condense_readings import annotate
from collection_window import weekly_eligible, previous_week
import build_public
import compose_issue
import build_issue
import feed


def commentary():
    row = record(); row.update(kind='nonacademic', doi='', venue='Synthetic policy publisher')
    row.pop('analysis'); row.pop('abstract_text')
    n = accepted(); n.update(doi='', record_url=row['url'])
    n['source'].update(url=row['url'], version='publisher_article', format='html', source_doi='')
    n['summary'] = {
        'thesis': 'The synthetic author argues that human oversight should accompany automated decisions.',
        'reasoning': 'The author reasons that context can change the meaning of an automated decision and that review offers an opportunity to challenge mistakes.',
        'examples': 'A fictional appeal process illustrates how a person could supply missing context without demonstrating that every appeal would improve outcomes.',
        'tension': 'The synthetic essay describes a tension between handling many decisions quickly and making room for individual context and accountability.',
        'qualification': 'This is a fictional policy argument, not an experiment, and the proposed safeguards have not been tested in this fixture.'}
    n['evidence'] = {k:[{'section':'Synthetic main argument', 'paragraph':i+1}] for i,k in enumerate(COMMENTARY_FIELDS)}
    n['commentary'] = {'genre':'policy_analysis','attributed_to':'Synthetic policy author',
        'source_depth':'main_argument_html','html_completeness':'not_verified',
        'semantic_completeness':'not_verified','figures_checked':False,
        'supplements_checked':False,'linked_claims_independently_verified':False,
        'temporal':{'original_published':row['published'],'reported_modified':None,
                    'checked_on':'2026-11-06','historical_snapshot_verified':False}}
    article_screen(n,row)
    return row, approve(n)


class CheckedTypesTests(unittest.TestCase):
    def test_commentary_has_no_study_methods_findings_or_fulltext_claim(self):
        row,n=commentary(); self.assertTrue(original.eligible(n,row))
        row['original_reading']=n
        note=make_note(row); self.assertEqual(note,annotate(row)['reading'])
        self.assertEqual(note['level'],'curated')
        for k in ('methods','findings','sample'): self.assertEqual(note[k],'')
        self.assertFalse(note['reported_findings'])
        for k in COMMENTARY_FIELDS: self.assertIn(k,note['digest']['longform'])
        self.assertIn('not verified',note['notice']); self.assertIn('Synthetic policy author',note['notice'])

    def test_typed_renderer_payload_contract_not_ui_acceptance(self):
        # Current UI needs a separate typed branch; this verifies its backend input,
        # not that the existing original-summary renderer supports commentary.
        row,n=commentary();row['original_reading']=n
        payload=original.public_record(annotate(row))['reading']
        self.assertEqual(payload['research_type'],'attributed_commentary')
        longform=payload['digest']['longform']
        for field in COMMENTARY_FIELDS:
            self.assertIn(n['summary'][field],longform[field])
        self.assertEqual(longform['genre'],'policy_analysis')
        self.assertEqual(longform['attributed_to'],'Synthetic policy author')
        self.assertEqual(longform['source_depth'],'main_argument_html')
        self.assertEqual(payload['digest']['approach'],'')
        self.assertEqual(payload['digest']['finding'],'')

    def test_commentary_current_version_dates_are_bound_and_not_backdated(self):
        row,n=commentary();n['commentary']['temporal']['reported_modified']='2026-11-05';approve(n)
        row['original_reading']=n;self.assertTrue(original.eligible(n,row))
        note=make_note(row);self.assertIn('2026-11-05',note['notice'])
        self.assertIn('No historical snapshot',note['notice'])
        self.assertFalse(weekly_eligible(row,*previous_week('2026-11-02')))
        same=deepcopy(row);same['original_reading']['commentary']['temporal']['reported_modified']='2026-11-01';approve(same['original_reading'])
        self.assertTrue(weekly_eligible(same,*previous_week('2026-11-02')))
        for key,value in [('original_published','2026-10-29'),('reported_modified','2099-01-01'),
                          ('checked_on','2026-11-01'),('historical_snapshot_verified',True)]:
            bad=deepcopy(n);bad['commentary']['temporal'][key]=value;approve(bad)
            self.assertFalse(original.eligible(bad,row))

    def test_commentary_missing_layers_or_rss_scope_fails(self):
        row,n=commentary()
        for key in COMMENTARY_FIELDS:
            bad=deepcopy(n); bad['summary'].pop(key); approve(bad)
            self.assertFalse(original.eligible(bad,row))
        for section,key,value in [('commentary','source_depth','rss_description'),
                ('commentary','html_completeness','complete'),('source','version','feed_snippet'),
                ('source','url','https://example.org/other'),('commentary','genre','experiment'),
                ('article_screen','decision','hold'),('article_screen','strong_causal_evidence_claimed',True)]:
            bad=deepcopy(n);bad[section][key]=value;approve(bad)
            self.assertFalse(original.eligible(bad,row),(section,key))

    def test_practical_and_product_control_genres_remain_nonempirical(self):
        for genre in ('practical_advice','product_control_guidance'):
            row,n=commentary();n['commentary']['genre']=genre;approve(n)
            self.assertTrue(original.eligible(n,row));row['original_reading']=n
            reading=make_note(row);self.assertEqual(reading['genre'],genre)
            self.assertEqual(reading['methods'],'');self.assertEqual(reading['findings'],'')
            self.assertIn('not a study',reading['notice'])

    def test_source_check_alone_is_not_acceptance(self):
        row,n=commentary()
        for section in ('article_screen','quality','publication'):
            bad=deepcopy(n);bad.pop(section);approve(bad) if section != 'publication' else None
            self.assertFalse(original.eligible(bad,row))
        for section,key,value in [('quality','decision','hold'),('publication','decision','pending')]:
            bad=deepcopy(n);bad[section][key]=value;approve(bad)
            self.assertFalse(original.eligible(bad,row))

    def test_all_preprint_identity_signals_require_article_screen(self):
        for mutation in ('url','source_doi','source_version','provenance'):
            row=record();n=accepted()
            if mutation=='url': row['url']='https://arxiv.org/abs/2610.12345';n['record_url']=row['url']
            if mutation=='source_doi': n['source'].update(source_doi='10.48550/arXiv.2610.12345',related_journal_doi=n['doi'],version='accepted_manuscript')
            if mutation=='source_version': row['source_version']='preprint_v1'
            if mutation=='provenance': row['publication_date_provenance']['basis']='arxiv_first_submitted'
            approve(n);row['original_reading']=n
            self.assertFalse(original.eligible(n,row),mutation)
            self.assertEqual(screen(row)['decision'],'hold',mutation)

    def test_preprint_synthesis_requires_qualification_and_no_positive_claim(self):
        packet=[{'kind':'scholarly','level':'full_text','preprint':True}]
        for prose in ('This peer-reviewed experiment proves AI causes lasting improvements.',
                      'This preprint suggests a useful approach.',
                      'This preprint is not peer reviewed and does not establish causality. It proves AI causes learning.'):
            with self.assertRaises(ValueError): compose_issue.qualify_section({'text':prose},packet)
        compose_issue.qualify_section({'text':'This preprint is not peer reviewed and does not establish causality. Its small comparison motivates further work.'},packet)

    def test_current_metadata_and_date_binding(self):
        row,n=commentary()
        for key,value in [('published','2026-10-29'),('kind','scholarly'),('venue','Different publisher'),
                          ('research_type','experiment'),('source_version','changed')]:
            changed=deepcopy(row);changed[key]=value
            self.assertFalse(original.eligible(n,changed),key)
        badrow=deepcopy(row);badrow['publication_date_provenance']['value']='2026-10-29'
        bad=deepcopy(n);article_screen(bad,badrow);approve(bad)
        self.assertFalse(original.eligible(bad,badrow))
        n['article_screen']['checked_on']='2026-10-01';approve(n)
        self.assertFalse(original.eligible(n,row))

    def test_preprint_requires_explicit_bound_article_screen(self):
        row=record();row['venue']='arXiv';n=accepted()
        self.assertFalse(original.eligible(n,row)); self.assertEqual(screen(row)['decision'],'hold')
        article_screen(n,row);approve(n);row['original_reading']=n
        self.assertTrue(original.eligible(n,row));self.assertEqual(screen(row)['decision'],'include')
        note=make_note(row);self.assertIn('not verified peer-reviewed',note['notice'])
        self.assertIn('strong causal',note['limitations'])
        row['title']='Cross-attention transformer for object detection';row['abstract_text']=''
        n['title']=row['title'];article_screen(n,row);approve(n)
        self.assertFalse(original.eligible(n,row));self.assertEqual(screen(row)['decision'],'hold')

    def test_preprint_conceptual_marker_cannot_bypass_gate(self):
        row=record();row.update(venue='arXiv',research_type='conceptual_framework',source='Editorially verified')
        self.assertEqual(screen(row)['decision'],'hold')

    def test_changed_revoked_duplicate_receipts_remove_commentary(self):
        row,n=commentary();original.apply([row],{'articles':[n]});row=annotate(row)
        for articles in ([],[n,n],[{**n,'publication':{**n['publication'],'decision':'revoked'}}]):
            current=deepcopy(row);original.apply([current],{'articles':articles});current=annotate(current)
            self.assertNotIn(n['summary']['thesis'],json.dumps(current))
        changed=deepcopy(n);changed['article_screen']['limitations_assessment']='Changed limitation requires another source check and acceptance.'
        self.assertFalse(original.eligible(changed,row))

    def test_queued_context_roundtrip_and_adversarial_changes(self):
        row,n=commentary();row['original_reading']=n;row=annotate(row)
        src={'id':row['url'],'title':row['title'],'kind':row['kind'],'url':row['url'],
             'venue':row['venue'],'published':row['published'],
             'publication_date_provenance':row['publication_date_provenance'],
             'research_type':row['reading']['research_type'],
             **build_issue.checked_source_metadata(row)}
        with tempfile.TemporaryDirectory() as tmp:
            manifest=Path(tmp)/'register.json';manifest.write_text(json.dumps({'articles':[n]}))
            (Path(tmp)/'library.json').write_text(json.dumps([row]))
            with patch.object(original,'MANIFEST',manifest),patch.object(build_issue,'DATA',Path(tmp)):
                resolved=build_issue.resolve_queued_original(src)
                self.assertEqual(resolved['reading'],row['reading'])
                for key,value in [('venue','changed'),('research_type','experiment'),
                        ('source_version','changed'),('published','2026-10-29'),
                        ('doi','10.9999/changed'),('url','https://example.org/changed')]:
                    bad=deepcopy(src);bad['original_record_context'][key]=value
                    with self.assertRaises(ValueError):build_issue.resolve_queued_original(bad)
                bad=deepcopy(src);bad['published']='2026-10-29'
                with self.assertRaises(ValueError):build_issue.resolve_queued_original(bad)
                manifest.write_text(json.dumps({'articles':[]}))
                with self.assertRaises(ValueError):build_issue.resolve_queued_original(src)

    def test_extended_queue_cannot_omit_context_to_bypass_current_index(self):
        row,n=commentary();row['original_reading']=n;row=annotate(row)
        src={**row,'id':row['url'],**build_issue.checked_source_metadata(row)}
        src.pop('original_record_context');src.pop('original_reading')
        src['source_version']=None;src['research_type']=None
        with tempfile.TemporaryDirectory() as tmp:
            manifest=Path(tmp)/'register.json';manifest.write_text(json.dumps({'articles':[n]}))
            with patch.object(original,'MANIFEST',manifest),patch.object(build_issue,'DATA',Path(tmp)):
                with self.assertRaisesRegex(ValueError,'context is missing'):
                    build_issue.resolve_queued_original(src)

    def test_queue_cannot_drop_late_modification_caveat(self):
        row,n=commentary();n['commentary']['temporal']['reported_modified']='2026-11-05';approve(n)
        row['original_reading']=n;row=annotate(row)
        src={'id':row['url'],'title':row['title'],'kind':row['kind'],'url':row['url'],
             'venue':row['venue'],'published':row['published'],
             'publication_date_provenance':row['publication_date_provenance'],
             **build_issue.checked_source_metadata(row)}
        src.pop('temporal');src.pop('temporal_notice')
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);manifest=data/'register.json';manifest.write_text(json.dumps({'articles':[n]}))
            (data/'library.json').write_text(json.dumps([row]))
            with patch.object(original,'MANIFEST',manifest),patch.object(build_issue,'DATA',data):
                resolved=build_issue.resolve_queued_original(src)
                self.assertEqual(resolved['reading']['temporal']['reported_modified'],'2026-11-05')
                self.assertFalse(weekly_eligible(resolved,*previous_week('2026-11-02')))

    def test_preprint_queued_metadata_roundtrip(self):
        row=record();row['venue']='arXiv';n=accepted();article_screen(n,row);approve(n)
        row['original_reading']=n;row=annotate(row)
        src={'id':row['doi'],'title':row['title'],'kind':row['kind'],'url':row['url'],
             'venue':row['venue'],'published':row['published'],
             'publication_date_provenance':row['publication_date_provenance'],
             'research_type':'unclassified',**build_issue.checked_source_metadata(row)}
        self.assertNotIn('abstract_text',json.dumps(src))
        with tempfile.TemporaryDirectory() as tmp:
            manifest=Path(tmp)/'register.json';manifest.write_text(json.dumps({'articles':[n]}))
            (Path(tmp)/'library.json').write_text(json.dumps([row]))
            with patch.object(original,'MANIFEST',manifest),patch.object(build_issue,'DATA',Path(tmp)):
                resolved=build_issue.resolve_queued_original(src)
                self.assertEqual(resolved['reading'],row['reading'])

    def test_preprint_queue_reads_current_topic_without_storing_abstract(self):
        row=record();row.update(venue='arXiv',title='Generative AI in higher education')
        row['abstract_text']='This synthetic research examines cognitive effort and sustained attention among students using generative AI in higher education. Its comparison separates subjective workload from later task performance.'
        n=accepted();n['title']=row['title'];article_screen(n,row);approve(n)
        raw=deepcopy(row);row['original_reading']=n;row=annotate(row)
        src={'id':row['doi'],'title':row['title'],'kind':row['kind'],'url':row['url'],
             'venue':row['venue'],'published':row['published'],
             'publication_date_provenance':row['publication_date_provenance'],
             'research_type':'unclassified',**build_issue.checked_source_metadata(row)}
        self.assertNotIn('abstract_text',json.dumps(src))
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);manifest=data/'register.json';manifest.write_text(json.dumps({'articles':[n]}))
            (data/'library.json').write_text(json.dumps([raw]))
            with patch.object(original,'MANIFEST',manifest),patch.object(build_issue,'DATA',data):
                self.assertEqual(build_issue.resolve_queued_original(src)['reading'],row['reading'])
                raw['venue']='Changed venue';(data/'library.json').write_text(json.dumps([raw]))
                with self.assertRaises(ValueError):build_issue.resolve_queued_original(src)

    def test_normal_cache_synthesis_feed_recheck_authoritative_current_index(self):
        cases=('venue','published','source_version','research_type','kind','topic',
               'missing','duplicate','missing_file')
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                data=Path(tmp);row,n=commentary()
                if case=='topic':
                    row=record();row['venue']='arXiv';row['title']='Generative AI in higher education'
                    row['abstract_text']='This synthetic study examines cognitive effort and sustained attention while students use generative AI. Its comparison separates perceived workload from performance and later retention in a short educational task.'
                    n=accepted();n['title']=row['title'];article_screen(n,row);approve(n)
                raw=deepcopy(row);row['original_reading']=n;cached=annotate(row)
                manifest=data/'register.json';manifest.write_text(json.dumps({'articles':[n]}))
                library=data/'library.json';library.write_text(json.dumps([raw]))
                (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[cached]}))
                with patch.object(original,'MANIFEST',manifest),patch.object(feed,'ROOT',data),patch.object(feed,'DATA',data):
                    self.assertTrue(original.public_record(cached,require_current=True)['reading']['original_summary'])
                    self.assertEqual(len(compose_issue.evidence([cached])),1)
                    self.assertEqual(feed.build(),1)
                    if case=='missing_file':library.unlink()
                    else:
                        if case=='venue':raw['venue']='Changed publisher'
                        if case=='published':raw['published']='2026-10-29'
                        if case=='source_version':raw['source_version']='changed'
                        if case=='research_type':raw['research_type']='experiment'
                        if case=='kind':raw['kind']='scholarly'
                        if case=='topic':raw['abstract_text']='This article discusses unrelated university administration and funding.'
                        library.write_text(json.dumps([] if case=='missing' else [raw,raw] if case=='duplicate' else [raw]))
                    checked=original.public_record(cached,require_current=True)
                    self.assertEqual(checked['reading']['level'],'citation_only')
                    self.assertNotIn('original_reading',checked)
                    self.assertEqual(compose_issue.evidence([cached]),[])
                    stripped=deepcopy(cached);stripped.pop('original_reading')
                    self.assertEqual(original.public_record(stripped,require_current=True)['reading']['level'],'citation_only')
                    self.assertEqual(compose_issue.evidence([stripped]),[])
                    self.assertEqual(feed.build(),0)
                    self.assertNotIn(n['summary'].get('thesis',n['summary'].get('idea')),(data/'feed.xml').read_text())

    def test_public_weekly_commentary_boundary_and_revocation(self):
        row,n=commentary()
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp);manifest=data/'manifest.json';manifest.write_text(json.dumps({'articles':[n]}))
            (data/'library.json').write_text(json.dumps([row]))
            (data/'weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[row]}))
            with patch.object(original,'MANIFEST',manifest),patch.object(build_public,'DATA',data):
                public,weekly=build_public.build();self.assertEqual(len(public),1);self.assertEqual(len(weekly['items']),1)
                self.assertTrue(weekly_eligible(public[0],*previous_week('2026-11-02')))
                self.assertFalse(weekly_eligible(public[0],*previous_week('2026-11-09')))
                packet=compose_issue.evidence(public);self.assertEqual(len(packet),1)
                self.assertIn('not a study',packet[0]['review_label'])
                self.assertNotIn('methods:',packet[0]['evidence'])
                self.assertIn('examples:',packet[0]['evidence']);self.assertIn('tension:',packet[0]['evidence'])
                self.assertEqual(packet[0]['genre'],'policy_analysis')
                self.assertEqual(packet[0]['attributed_to'],'Synthetic policy author')
                with patch.object(feed,'ROOT',data),patch.object(feed,'DATA',data):
                    self.assertEqual(feed.build(),1)
                self.assertIn('Attributed commentary',(data/'feed.xml').read_text())
                manifest.write_text(json.dumps({'articles':[]}))
                self.assertEqual(compose_issue.evidence(public),[])
                with patch.object(feed,'ROOT',data),patch.object(feed,'DATA',data):
                    self.assertEqual(feed.build(),0)
                self.assertNotIn(n['summary']['thesis'],(data/'feed.xml').read_text())
                selected,_=build_public.build();self.assertEqual(selected,[])

if __name__=='__main__':unittest.main()

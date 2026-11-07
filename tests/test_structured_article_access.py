"""Offline source-routing and all-XML-text coverage tests; no network/model calls."""
import gzip
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import full_document_access as access
import structured_article_access as xml
import comprehensive_readings as reading

TITLE='An exact scholarly article about cognitive learning and attention'
DOI='10.5555/test-article'
RECORD={'title':TITLE,'doi':DOI,'kind':'scholarly'}
PARA='The comparison measured task performance and did not establish durable independent learning. '

def jats(license=True,doi=DOI,title=TITLE):
    rights='<permissions><license href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</license></permissions>' if license else ''
    return (f'<article><front><article-meta><article-id pub-id-type="doi">{doi}</article-id>'
            f'<title-group><article-title>{title}</article-title></title-group>{rights}</article-meta></front>'
            f'<body><sec><title>Introduction</title><p>{PARA*100}</p></sec>'
            f'<sec><title>Results</title><p>{PARA*100}</p><table-wrap><label>Table 1</label><table><tr><td>42</td></tr></table></table-wrap></sec>'
            f'<sec><title>Limitations</title><p>TAIL_QUALIFICATION {PARA*50}</p></sec></body>'
            '<back><ref-list><ref>END_REFERENCE</ref></ref-list></back></article>').encode()

def tei(legacy=False):
    body=f'<div><head>Introduction</head><p>{PARA*100}</p></div><div><head>Limitations</head><p>TAIL_QUALIFICATION {PARA*50}</p></div>'
    if not legacy: body='<body>'+body+'</body>'
    paper=f'<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc><titleStmt><title>{TITLE}</title></titleStmt><sourceDesc><biblStruct><idno type="DOI">{DOI}</idno></biblStruct></sourceDesc></fileDesc></teiHeader><text>{body}<back>END_REFERENCE</back></text></TEI>'
    return ('<html><body>'+paper+'</body></html>' if legacy else paper).encode()

class XMLParsingTests(unittest.TestCase):
    def test_complete_jats_includes_intro_tables_tail_and_references_without_duplicate_text(self):
        doc=xml.document_from_xml(jats(),RECORD,'https://www.ebi.ac.uk/test',format='jats')
        text=' '.join(u['text'] for u in doc.units)
        for word in ('Introduction','Table 1','42','TAIL_QUALIFICATION','END_REFERENCE'): self.assertIn(word,text)
        self.assertEqual(text.count('TAIL_QUALIFICATION'),1)
        self.assertGreater(len(text),16000)
        chunks=reading.chunk_document(doc)
        self.assertTrue(reading.coverage_is_complete(doc,chunks))
        self.assertIn('END_REFERENCE',chunks[-1]['text'])
        self.assertEqual(doc.coverage['structured_text_coverage'],'all_text_in_supplied_article_xml')
        self.assertEqual(doc.coverage['source_document_equivalence'],'not_verified')
        self.assertFalse(doc.manifest()['source_text_saved'])
        self.assertNotIn('TAIL_QUALIFICATION',json.dumps(doc.manifest()))

    def test_standard_and_legacy_tei_both_keep_tail(self):
        for legacy in (False,True):
            doc=xml.document_from_xml(tei(legacy),RECORD,'https://content.openalex.org/works/W1.grobid-xml',format='tei')
            self.assertIn('END_REFERENCE',doc.units[-1]['text'])
            self.assertTrue(reading.coverage_is_complete(doc,reading.chunk_document(doc)))

    def test_gzip_is_decoded_without_truncation(self):
        doc=xml.document_from_xml(gzip.compress(jats()),RECORD,'https://www.ebi.ac.uk/test',format='jats')
        self.assertIn('END_REFERENCE',doc.units[-1]['text'])

    def test_gzip_expansion_limit_is_enforced(self):
        with patch.object(xml,'MAX_XML_BYTES',100):
            with self.assertRaisesRegex(ValueError,'too_large'):xml.decoded_xml(gzip.compress(jats()))

    def test_non_gzip_limit_is_enforced(self):
        with patch.object(xml,'MAX_XML_BYTES',100):
            with self.assertRaisesRegex(ValueError,'too_large'):xml.decoded_xml(jats())

    def test_entities_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'entities_disallowed'):
            xml.decoded_xml(b'<!DOCTYPE a [<!ENTITY x "bad">]><a>&x;</a>')

    def test_external_jats_doctype_does_not_load_a_resource(self):
        raw=b'<!DOCTYPE article SYSTEM "https://untrusted.example/dtd">'+jats()
        self.assertEqual(xml.decoded_xml(raw).tag,'article')

    def test_jats_requires_article_level_license(self):
        raw=jats(False).replace(b'<table-wrap>',b'<table-wrap><license href="https://creativecommons.org/licenses/by/4.0/">CC BY</license>')
        with self.assertRaisesRegex(ValueError,'license_unverified'):
            xml.document_from_xml(raw,RECORD,'https://www.ebi.ac.uk/test',format='jats')

    def test_restrictive_jats_license_not_promoted_by_cc_by_substring(self):
        raw=jats().replace(b'licenses/by/',b'licenses/by-nc-nd/').replace(b'CC BY 4.0',b'CC BY-NC-ND 4.0')
        with self.assertRaisesRegex(ValueError,'license_unverified'):
            xml.document_from_xml(raw,RECORD,'https://www.ebi.ac.uk/test',format='jats')

    def test_body_reference_doi_cannot_validate_wrong_header(self):
        raw=jats(doi='10.5555/wrong').replace(b'END_REFERENCE',DOI.encode())
        with self.assertRaisesRegex(ValueError,'identity_unverified'):
            xml.document_from_xml(raw,RECORD,'https://www.ebi.ac.uk/test',format='jats')

    def test_doi_without_matching_title_is_not_enough(self):
        with self.assertRaisesRegex(ValueError,'identity_unverified'):
            xml.document_from_xml(jats(title='Another paper with the same erroneous identifier'),RECORD,'https://www.ebi.ac.uk/test',format='jats')

    def test_abstract_only_xml_is_rejected(self):
        raw=f'<article><front><article-meta><abstract>{PARA*200}</abstract></article-meta></front></article>'.encode()
        with self.assertRaisesRegex(ValueError,'body_missing'):
            xml.document_from_xml(raw,RECORD,'https://www.ebi.ac.uk/test',format='jats')

    def test_restrictive_plain_license_without_uri_is_rejected(self):
        for license in ('CC BY-NC-ND 4.0','CC-BY-NC 4.0','CC BY ND 4.0'):
            raw=jats().replace(b'<license href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</license>',
                               ('<license>'+license+'</license>').encode())
            with self.subTest(license=license),self.assertRaisesRegex(ValueError,'license_unverified'):
                xml.document_from_xml(raw,RECORD,'https://www.ebi.ac.uk/test',format='jats')

    def test_utf16_internal_entity_is_rejected_before_parsing(self):
        raw='<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE article [<!ENTITY e "EXPANDED">]><article>&e;</article>'.encode('utf-16')
        with self.assertRaisesRegex(ValueError,'encoding_unsupported'):xml.decoded_xml(raw)

    def test_source_registry_versions_match_verified_pilot(self):
        root=Path(__file__).resolve().parents[1]
        records=json.loads((root/'data/free-access-candidates.json').read_text())['records']
        self.assertEqual(len(records),11)
        for record in records:
            # Remove manifest candidates so this exercises the persisted source
            # register rather than merely echoing the supplied candidate.
            source={k:v for k,v in record.items() if k!='fulltext_candidates'}
            rows=access.known_candidates(source)
            self.assertEqual(rows[0]['url'],record['fulltext_candidates'][0]['url'])
            self.assertFalse(record['web_retrieval']['runner_extraction_verified'])
            self.assertFalse(record['web_retrieval']['summary_completed'])
            if 'arxiv.org' in rows[0]['url']:self.assertRegex(rows[0]['url'],r'v[1-9][0-9]*$')

class StructuredRouteTests(unittest.TestCase):
    def test_europe_pmc_uses_exact_doi_open_access_and_pmcid(self):
        get=Mock(return_value={'resultList':{'result':[
            {'doi':DOI,'pmcid':'PMC123','isOpenAccess':'Y'},
            {'doi':'10.5555/other','pmcid':'PMC456','isOpenAccess':'Y'},
            {'doi':DOI,'pmcid':'PMC789','isOpenAccess':'N'}]}})
        rows=xml.europe_pmc_candidates(DOI,get)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['url'],xml.EPMC+'PMC123/fullTextXML')
        self.assertNotIn('email=',get.call_args.args[0])

    def test_openalex_uses_only_existing_configured_key_and_exact_source_url(self):
        get=Mock(return_value={'doi':'https://doi.org/'+DOI,'id':'https://openalex.org/W123',
            'open_access':{'is_oa':True},'content_urls':{'grobid_xml':'https://content.openalex.org/works/W123.grobid-xml'}})
        with patch.dict('os.environ',{'OPENALEX_API_KEY':'PRIVATE_KEY'},clear=True):
            rows=xml.openalex_candidates(DOI,get)
        self.assertEqual(len(rows),1)
        self.assertNotIn('PRIVATE_KEY',json.dumps(rows))
        self.assertIn('api_key=PRIVATE_KEY',get.call_args.args[0])
        get.return_value['content_urls']['grobid_xml']='https://untrusted.example/W123.grobid-xml'
        with patch.dict('os.environ',{'OPENALEX_API_KEY':'PRIVATE_KEY'},clear=True):
            self.assertEqual(xml.openalex_candidates(DOI,get),[])

    def test_missing_openalex_key_is_explicit_no_network(self):
        get=Mock()
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(ValueError,'key_not_configured'):xml.openalex_candidates(DOI,get)
        get.assert_not_called()

    def test_closed_openalex_work_is_not_fetched(self):
        get=Mock(return_value={'doi':DOI,'id':'https://openalex.org/W1','open_access':{'is_oa':False}})
        with patch.dict('os.environ',{'OPENALEX_API_KEY':'PRIVATE_KEY'},clear=True):
            self.assertEqual(xml.openalex_candidates(DOI,get),[])

    def test_wrong_openalex_doi_is_rejected(self):
        with patch.dict('os.environ',{'OPENALEX_API_KEY':'PRIVATE_KEY'},clear=True):
            with self.assertRaisesRegex(ValueError,'identity_mismatch'):
                xml.openalex_candidates(DOI,Mock(return_value={'doi':'10.5555/wrong'}))

    def test_api_fetch_never_puts_key_or_source_prose_in_manifest(self):
        url='https://content.openalex.org/works/W123.grobid-xml'
        def fake_request(target,*args):return tei(),target,'application/xml'
        with patch.dict('os.environ',{'OPENALEX_API_KEY':'PRIVATE_KEY'},clear=True),patch.object(access,'request',side_effect=fake_request):
            doc=access.fetch_candidate({'url':url,'structured_format':'tei'},RECORD)
        self.assertEqual(doc.url,url)
        self.assertNotIn('PRIVATE_KEY',json.dumps(doc.manifest()))
        self.assertNotIn('TAIL_QUALIFICATION',json.dumps(doc.manifest()))

    def test_structured_flag_cannot_allow_arbitrary_url_or_token(self):
        for url in ('https://evil.example/x','https://content.openalex.org/works/W123.grobid-xml?api_key=BAD',
                    'https://www.ebi.ac.uk/anything','https://content.openalex.org/works/W123.pdf'):
            with self.subTest(url=url),self.assertRaisesRegex(ValueError,'endpoint_invalid'):
                xml.fetch_structured({'url':url,'structured_format':'tei'},RECORD)

    def test_provider_api_failure_falls_through_to_next_source(self):
        first=Mock(side_effect=HTTPError('https://www.ebi.ac.uk',503,'temporary',{},None))
        second=Mock(return_value=[])
        with patch.object(access.time,'sleep'):
            _,log=access.retrieve(RECORD,providers=[('XML',first),('next',second)])
        second.assert_called_once()
        self.assertEqual(log[0]['status'],'http_503')

class PublisherLinkTests(unittest.TestCase):
    def page(self,links):return f'<meta name="citation_doi" content="{DOI}"><meta name="citation_title" content="{TITLE}">{links}'
    def test_reference_pdf_discovered_from_actual_download_link(self):
        links='<a href="/content/pdf/test_reference.pdf"><span>Download PDF</span></a>'
        self.assertEqual(access.publisher_pdf_links(self.page(links),'https://link.springer.com/article/test',RECORD),
                         ['https://link.springer.com/content/pdf/test_reference.pdf'])
    def test_ojs_pdf_url_without_pdf_suffix(self):
        links='<meta name="citation_pdf_url" content="https://ijlter.org/index.php/ijlter/article/download/17548/pdf">'
        self.assertEqual(len(access.publisher_pdf_links(self.page(links),'https://ijlter.org/index.php/ijlter/article/view/17548',RECORD)),1)
    def test_wrong_article_or_generic_cross_host_link_not_followed(self):
        links='<a href="https://www.econstor.eu/unrelated.pdf">Download PDF</a>'
        self.assertEqual(access.publisher_pdf_links(self.page(links),'https://link.springer.com/article/test',RECORD),[])
        self.assertEqual(access.publisher_pdf_links(self.page('<a href="/x.pdf">Download PDF</a>'),'https://link.springer.com/article/test',
                         {**RECORD,'title':'Completely different article title about other findings','doi':'10.5555/wrong'}),[])
    def test_supplement_does_not_precede_the_main_article(self):
        links='<a href="/supplementary-material.pdf">Download supplementary PDF</a><a href="/full.pdf">Download PDF</a>'
        self.assertEqual(access.publisher_pdf_links(self.page(links),'https://link.springer.com/article/test',RECORD),
                         ['https://link.springer.com/full.pdf'])
        for href in ('/ESM_1.pdf','/appendix.pdf','/%73upplement.pdf'):
            self.assertEqual(access.publisher_pdf_links(self.page('<a href="'+href+'">Download PDF</a>'),'https://link.springer.com/article/test',RECORD),[])

    def test_link_budget_is_bounded(self):
        links=''.join(f'<a href="/{n}.pdf">Download PDF</a>' for n in range(10))
        self.assertEqual(len(access.publisher_pdf_links(self.page(links),'https://link.springer.com/article/test',RECORD)),2)

    def test_partial_pdf_does_not_hide_richer_html_or_later_complete_pdf(self):
        url='https://link.springer.com/article/test'
        page=self.page('<a href="/one.pdf">Download PDF</a><a href="/two.pdf">Download PDF</a>').encode()
        partial=access.Document([{'location':'page:1','text':'Short extract. '*150}],url,coverage={'evidence_status':'partial_full_text'})
        html=access.Document([{'location':'paragraph:1','text':'Complete accessible HTML paragraph. '*500}],url,coverage={'evidence_status':'partial_full_text'})
        complete=access.Document([{'location':'page:1','text':'Complete PDF text. '*500}],url,coverage={'evidence_status':'full_document_retrieved'})
        with patch.object(access,'robots_allowed',return_value=True),patch.object(access,'request',side_effect=[(page,url,'text/html'),(b'%PDF-1',url,'application/pdf'),(b'%PDF-2',url,'application/pdf')]),patch.object(access,'document_from_pdf',side_effect=[partial,partial]),patch.object(access,'document_from_html',return_value=html) as parse:
            doc=access.fetch_candidate({'url':url},RECORD)
        self.assertIs(doc,html);parse.assert_called_once()
        with patch.object(access,'robots_allowed',return_value=True),patch.object(access,'request',side_effect=[(page,url,'text/html'),(b'%PDF-1',url,'application/pdf'),(b'%PDF-2',url,'application/pdf')]),patch.object(access,'document_from_pdf',side_effect=[partial,complete]),patch.object(access,'document_from_html') as parse:
            doc=access.fetch_candidate({'url':url},RECORD)
        self.assertIs(doc,complete);parse.assert_not_called()

    def test_access_challenge_does_not_follow_embedded_pdf_link(self):
        url='https://link.springer.com/article/test'
        page=self.page('<h1>Verify you are human</h1><a href="/x.pdf">Download PDF</a>').encode()
        with patch.object(access,'robots_allowed',return_value=True),patch.object(access,'request',return_value=(page,url,'text/html')) as request:
            with self.assertRaisesRegex(ValueError,'access_challenge'):
                access.fetch_candidate({'url':url},RECORD)
        self.assertEqual(request.call_count,1)

class LivePilotBoundaryTests(unittest.TestCase):
    def test_pilot_is_bounded_and_reports_no_summary_or_source_text(self):
        import article_access_trials as trials
        doc=access.Document([{'location':'page:1','text':'PRIVATE_SOURCE_SENTINEL '*100}],
                            'https://arxiv.org/pdf/2610.31335v1',coverage={'evidence_status':'full_document_retrieved'})
        with patch.object(trials,'fetch_candidate',return_value=doc) as fetch:
            report=trials.free_source_pilot()
        self.assertEqual(fetch.call_count,6)
        self.assertEqual(len(report),6)
        self.assertTrue(all(x['fulltext_retrieved'] and x['all_retrieved_text_retained'] for x in report))
        self.assertTrue(all(x['summary_completed'] is False for x in report))
        self.assertNotIn('PRIVATE_SOURCE_SENTINEL',json.dumps(report))

    def test_pilot_isolates_provider_failures_and_redacts_exception_text(self):
        import article_access_trials as trials
        with patch.object(trials,'fetch_candidate',side_effect=ValueError('https://source/?secret=PRIVATE_KEY')):
            report=trials.free_source_pilot()
        self.assertEqual(len(report),6)
        self.assertTrue(all(not x['fulltext_retrieved'] for x in report))
        self.assertNotIn('PRIVATE_KEY',json.dumps(report))

if __name__=='__main__':unittest.main()

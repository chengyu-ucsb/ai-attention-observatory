"""Offline checks of source routing, identity, retries and private PDF handoff."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import full_document_access as access


def document(url,complete=True):
    return access.Document([{'location':'page:1','text':'Evidence text. '*200}],url,
                           'publishedVersion',{'evidence_status':
                           'full_document_retrieved' if complete else 'partial_full_text'})


class RetrievalRouteTests(unittest.TestCase):
    def setUp(self):
        self.record={'doi':'10.5555/retrieval-test','kind':'scholarly',
                     'title':'A carefully matched scholarly research article'}

    def test_known_pdf_succeeds_without_calling_any_locator(self):
        url='https://www.microsoft.com/en-us/research/paper.pdf'
        record={**self.record,'fulltext_candidates':[{'url':url,'provider':'verified_author'}]}
        provider=Mock()
        with patch.object(access,'fetch_candidate',return_value=document(url)) as fetch:
            result,log=access.retrieve(record,providers=[('unused',provider)])
        provider.assert_not_called()
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(result.url,url)
        self.assertEqual(log[0]['status'],'full_document_retrieved')
        self.assertEqual(log[0]['url'],url)

    def test_empty_providers_disables_defaults(self):
        with patch.object(access,'default_providers') as defaults:
            options,log=access.discover(self.record,providers=[])
            result,attempts=access.retrieve(self.record,providers=[])
        defaults.assert_not_called()
        self.assertEqual(options,[])
        self.assertEqual(log,[])
        self.assertIsNone(result)
        self.assertEqual(attempts,[])

    def test_scholarly_open_access_and_original_urls_are_tried(self):
        record={**self.record,'open_access_url':'https://www.econstor.eu/paper.pdf',
                'url':'https://www.nature.com/articles/test'}
        options=access.known_candidates(record)
        self.assertEqual([x['url'] for x in options],
                         [record['open_access_url'],record['url']])
        resolver=access.known_candidates({**self.record,'url':'https://doi.org/'+self.record['doi']})
        self.assertEqual(resolver,[])

    def test_arxiv_without_doi_attempts_pdf_first(self):
        record={'title':self.record['title'],'kind':'scholarly',
                'url':'https://arxiv.org/abs/2409.16708v2'}
        options=access.known_candidates(record)
        self.assertEqual(options[0]['url'],'https://arxiv.org/pdf/2409.16708v2')
        self.assertEqual(options[0]['version'],'arxiv_preprint_v2')
        provider=Mock()
        with patch.object(access,'fetch_candidate',return_value=document(options[0]['url'])):
            result,_=access.retrieve(record,providers=[('unused',provider)])
        provider.assert_not_called()
        self.assertIsNotNone(result)

    def test_complete_pdf_beats_first_partial_html(self):
        urls=['https://www.econstor.eu/landing','https://www.econstor.eu/paper.pdf']
        record={**self.record,'fulltext_candidates':[{'url':u} for u in urls]}
        with patch.object(access,'fetch_candidate',side_effect=[document(urls[0],False),document(urls[1])]):
            result,log=access.retrieve(record,providers=[])
        self.assertEqual(result.url,urls[1])
        self.assertEqual([x['status'] for x in log],['partial_full_text','full_document_retrieved'])

    def test_partial_input_survives_provider_failure_and_next_provider_can_succeed(self):
        url='https://www.econstor.eu/landing'
        pdf='https://www.econstor.eu/full.pdf'
        record={**self.record,'open_access_url':url}
        limited=Mock(side_effect=HTTPError('https://api.core.ac.uk',429,'limited',
                                         {'Retry-After':'900'},None))
        working=Mock(return_value=[access.candidate(pdf,'working',self.record['doi'])])
        with patch.object(access,'fetch_candidate',side_effect=[document(url,False),document(pdf)]), \
             patch.object(access.time,'sleep'):
            result,log=access.retrieve(record,providers=[('limited',limited),('working',working)])
        self.assertEqual(result.url,pdf)
        failure=next(x for x in log if x['status']=='http_429')
        self.assertTrue(failure['retryable'])
        self.assertEqual(failure['retry_after_seconds'],900)
        self.assertEqual(working.call_count,1)

    def test_no_complete_candidate_returns_partial_without_promoting_it(self):
        url='https://www.econstor.eu/landing'
        with patch.object(access,'fetch_candidate',return_value=document(url,False)):
            result,_=access.retrieve({**self.record,'open_access_url':url},providers=[])
        self.assertEqual(result.coverage['evidence_status'],'partial_full_text')

    def test_sparse_partial_pdf_does_not_displace_richer_html(self):
        html_url='https://www.econstor.eu/landing'
        pdf_url='https://www.econstor.eu/scanned.pdf'
        html=access.Document([{'location':'p:1','text':'Useful article body. '*950}],html_url,
                             coverage={'evidence_status':'partial_full_text'})
        scanned=access.Document([{'location':'page:1','text':'Sparse extract. '*120}],pdf_url,
                                coverage={'evidence_status':'partial_full_text','pages_total':20,
                                          'pages_with_text':1})
        record={**self.record,'fulltext_candidates':[{'url':html_url},{'url':pdf_url}]}
        with patch.object(access,'fetch_candidate',side_effect=[html,scanned]):
            result,_=access.retrieve(record,providers=[])
        self.assertEqual(result.url,html_url)
        self.assertEqual(result.coverage['evidence_status'],'partial_full_text')

    def test_known_and_provider_duplicate_is_fetched_once(self):
        url='https://www.econstor.eu/blocked.pdf'
        provider=Mock(return_value=[access.candidate(url,'same',self.record['doi'])])
        with patch.object(access,'fetch_candidate',side_effect=HTTPError(url,403,'denied',{},None)) as fetch, \
             patch.object(access.time,'sleep'):
            result,log=access.retrieve({**self.record,'open_access_url':url},providers=[('same',provider)])
        self.assertIsNone(result)
        self.assertEqual(fetch.call_count,1)
        failure=next(x for x in log if x['status']=='article_http_403')
        self.assertFalse(failure['retryable'])

    def test_locator_pdf_precedes_doi_resolver_under_small_budget(self):
        pdf='https://epub.ub.uni-muenchen.de/125262/paper.pdf'
        provider=Mock(return_value=[
            access.candidate('https://doi.org/'+self.record['doi'],'lookup',self.record['doi']),
            access.candidate('https://unreviewed.example/paper.pdf','lookup',self.record['doi']),
            access.candidate(pdf,'lookup',self.record['doi'])])
        with patch.object(access,'fetch_candidate',return_value=document(pdf)) as fetch:
            result,_=access.retrieve(self.record,max_candidates=1,providers=[('lookup',provider)])
        self.assertEqual(result.url,pdf)
        self.assertEqual(fetch.call_args.args[0]['url'],pdf)

    def test_unpaywall_never_invents_contact_information(self):
        get=Mock()
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(ValueError,'contact_not_configured'):
                access.unpaywall_candidates(self.record['doi'],get=get)
            _,status=access.provider_candidates('Unpaywall',access.unpaywall_candidates,self.record['doi'])
        get.assert_not_called()
        self.assertEqual(status['status'],'contact_not_configured')

    def test_diagnostics_remove_credentials_and_queries(self):
        url='https://user:password@www.econstor.eu/paper.pdf?token=SECRET#secret'
        self.assertEqual(access.diagnostic_url(url),'https://www.econstor.eu/paper.pdf')
        error=HTTPError(url,403,'secret echoed by server',{},None)
        self.assertNotIn('secret',json.dumps(access.failure_diagnostic(error)).lower())
        self.assertNotIn('SECRET',json.dumps(document(url).manifest()))

    def test_source_register_is_doi_scoped_and_does_not_change_record(self):
        file=Mock()
        file.exists.return_value=True
        file.stat.return_value=SimpleNamespace(st_size=500)
        source={'url':'https://www.econstor.eu/verified.pdf','provider':'verified_source'}
        file.read_text.return_value=json.dumps({'version':1,'records':[
            {'doi':self.record['doi'],'fulltext_candidates':[source]},
            {'doi':'10.5555/other','fulltext_candidates':[{'url':'https://www.econstor.eu/other.pdf'}]}]})
        original=dict(self.record)
        with patch.object(access,'SOURCE_HINTS',file):
            options=access.known_candidates(self.record)
        self.assertEqual([x['url'] for x in options],[source['url']])
        self.assertEqual(self.record,original)

    def test_pdf_bytes_are_returned_only_after_identity_validation(self):
        raw=b'%PDF-1.7 PRIVATE_BINARY_SOURCE'
        text=self.record['title']+'\n'+'Results and qualifications from the paper. '*100
        reader=SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:text)])
        module=SimpleNamespace(PdfReader=Mock(return_value=reader))
        with patch.dict(sys.modules,{'pypdf':module}):
            doc=access.document_from_pdf(raw,self.record,'https://www.econstor.eu/p.pdf')
            with self.assertRaisesRegex(ValueError,'identity_unverified'):
                access.document_from_pdf(raw,{**self.record,'title':'An entirely different scholarly publication'},
                                         'https://www.econstor.eu/p.pdf')
        manifest=doc.manifest()
        self.assertIs(doc.source_bytes,raw)
        self.assertEqual(manifest['source_bytes_sha256'],sha256(raw).hexdigest())
        self.assertEqual(manifest['source_byte_count'],len(raw))
        self.assertNotIn('PRIVATE_BINARY_SOURCE',json.dumps(manifest))
        self.assertFalse(manifest['source_text_saved'])


class RelatedVersionIdentityTests(unittest.TestCase):
    def setUp(self):
        self.record={'doi':'10.1016/j.chb.2025.108779',
                     'title':'AI makes you smarter but none the wiser: The disconnect between performance and metacognition'}
        self.option={
            'url':'https://arxiv.org/pdf/2409.16708v2','provider':'verified_preprint',
            'doi':'10.48550/arxiv.2409.16708','version':'arxiv_preprint_v2',
            'title':'Performance and Metacognition Disconnect when Reasoning in Human-AI Interaction',
            'related_doi':self.record['doi'],
            'identity_verification_url':'https://arxiv.org/abs/2409.16708'}
        self.html=(f'<meta name="citation_title" content="{self.option["title"]}">'
                   f'<meta name="citation_doi" content="{self.record["doi"]}">'
                   '<meta name="citation_arxiv_id" content="2409.16708">').encode()

    def test_verified_related_version_preserves_parent_and_preprint_identities(self):
        with patch.object(access,'robots_allowed',return_value=True), \
             patch.object(access,'request',return_value=(self.html,self.option['identity_verification_url'],'text/html')):
            identity,target,provenance=access.candidate_identity(self.option,self.record)
        self.assertEqual(identity['title'],self.option['title'])
        self.assertEqual(target,self.record['doi'])
        self.assertEqual(provenance['record_doi'],self.record['doi'])
        self.assertEqual(provenance['source_doi'],self.option['doi'])
        self.assertEqual(provenance['source_relation'],'related_preprint')
        self.assertNotEqual(identity['title'],self.record['title'])

    def test_title_alias_without_parent_evidence_is_rejected(self):
        option={**self.option,'related_doi':'10.5555/wrong'}
        with patch.object(access,'request') as request:
            with self.assertRaisesRegex(ValueError,'parent_mismatch'):
                access.candidate_identity(option,self.record)
        request.assert_not_called()

    def test_evidence_for_another_arxiv_paper_is_rejected(self):
        option={**self.option,'url':'https://arxiv.org/pdf/2409.99999v2'}
        with self.assertRaisesRegex(ValueError,'verification_required'):
            access.candidate_identity(option,self.record)

    def test_verification_page_must_name_the_exact_parent_doi(self):
        html=self.html.replace(self.record['doi'].encode(),b'10.5555/not-the-parent')
        with patch.object(access,'robots_allowed',return_value=True), \
             patch.object(access,'request',return_value=(html,self.option['identity_verification_url'],'text/html')):
            with self.assertRaisesRegex(ValueError,'identity_unverified'):
                access.candidate_identity(self.option,self.record)

    def test_global_document_identity_matching_is_not_relaxed(self):
        self.assertFalse(access.identity_matches(self.record,self.option['title']))
        self.assertFalse(access.identity_matches(self.record,'References: '+self.record['doi']))


if __name__=='__main__': unittest.main()

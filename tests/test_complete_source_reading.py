"""Offline regression tests. No article access, keys or model downloads."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import full_document_access as access
import comprehensive_readings as reading


class CompleteSourceTests(unittest.TestCase):
    def test_text_beyond_old_cutoff_and_document_tail_are_preserved(self):
        text=('Substantive article paragraph with limitations and results. '*800)+'END_OF_ARTICLE'
        doc=access.Document([{'location':'page:1','text':text}], 'https://www.econstor.eu/paper.pdf')
        chunks=reading.chunk_document(doc)
        self.assertGreater(len(chunks),3)
        self.assertIn('END_OF_ARTICLE',chunks[-1]['text'])
        self.assertTrue(reading.coverage_is_complete(doc,chunks))
        self.assertEqual(sum(r['end']-r['start'] for c in chunks for r in c['ranges']),len(text))
        self.assertTrue(all(len(c['text'])<=5500 for c in chunks))

    def test_page_ranges_preserve_blank_pages_and_every_character(self):
        doc=access.Document([{'location':'page:1','text':'A'*5601},
                             {'location':'page:2','text':''},
                             {'location':'page:3','text':'B'*2900}], 'https://www.econstor.eu/paper.pdf')
        chunks=reading.chunk_document(doc)
        self.assertTrue(reading.coverage_is_complete(doc,chunks))
        chunks[0]['ranges'][0]['start']=1
        self.assertFalse(reading.coverage_is_complete(doc,chunks))

    def test_claim_requires_matching_anchor_and_numbers(self):
        chunk={'text':'The classroom comparison included 47 students and did not establish independent transfer.'}
        good={'field':'limitations','text':'Independent learning beyond the classroom was not established in this comparison.',
              'quote':'did not establish independent transfer'}
        reading.validate_claim(good,chunk,'scholarly')
        with self.assertRaisesRegex(ValueError,'numeric'):
            reading.validate_claim({**good,'text':'The comparison established learning gains in 500 students.'},chunk,'scholarly')
        with self.assertRaisesRegex(ValueError,'anchor_absent'):
            reading.validate_claim({**good,'quote':'These words never appeared in the source'},chunk,'scholarly')

    def test_conceptual_article_does_not_require_empirical_results(self):
        chunk={'text':'The authors propose a framework for gradually transferring responsibility without testing its effects.'}
        claim={'field':'authors_interpretation',
               'text':'This conceptual proposal describes staged responsibility rather than demonstrating an intervention effect.',
               'quote':'propose a framework for gradually transferring responsibility'}
        reading.validate_claim(claim,chunk,'scholarly')

    def test_source_copying_is_rejected(self):
        text='The classroom comparison examined how learners checked advice and revised their decisions without external support.'
        with self.assertRaisesRegex(ValueError,'copied'):
            reading.validate_claim({'field':'study_design','text':text,
                'quote':'classroom comparison examined how learners checked'}, {'text':text},'scholarly')

    def test_partial_indexed_sections_are_not_called_full_document(self):
        text='Retained results and qualification. '*300
        doc=reading.indexed_sections({'analysis':{'fulltext_url':'https://www.econstor.eu/paper.pdf','discussion':text}})
        self.assertEqual(doc.units[0]['text'],text)
        self.assertEqual(doc.manifest()['evidence_status'],'partial_full_text')
        self.assertTrue(doc.manifest()['upstream_truncation_possible'])

    def test_oversized_document_is_deferred_not_shortened(self):
        doc=access.Document([{'location':'p1','text':'word '*3000}], 'https://www.econstor.eu/paper.pdf')
        model=Mock()
        with self.assertRaisesRegex(ValueError,'chunk_budget'):
            reading.synthesize(doc,model,'scholarly','A title',max_chunks=1)
        model.create_chat_completion.assert_not_called()

    def test_manifest_does_not_save_article_text(self):
        doc=access.Document([{'location':'p1','text':'PRIVATE_SOURCE_SENTINEL'}],'https://www.econstor.eu/paper.pdf')
        self.assertNotIn('PRIVATE_SOURCE_SENTINEL',json.dumps(doc.manifest()))
        self.assertFalse(doc.manifest()['source_text_saved'])

    def test_provider_failure_does_not_block_next_locator(self):
        def broken(identifier):
            raise HTTPError('https://api.core.ac.uk',429,'rate limited',{},None)
        def working(identifier):
            return [access.candidate('https://www.econstor.eu/a.pdf','working',identifier)]
        options,diagnostics=access.discover({'doi':'10.5555/test'},providers=[('broken',broken),('working',working)])
        self.assertEqual(len(options),1)
        self.assertEqual(diagnostics[0]['status'],'http_429')
        self.assertEqual(diagnostics[1]['status'],'candidates')

    def test_unpaywall_retains_all_pdf_and_html_alternatives(self):
        data={'doi':'10.5555/test','oa_locations':[{'url_for_pdf':'https://www.econstor.eu/a.pdf',
               'url_for_landing_page':'https://www.econstor.eu/handle/1','version':'acceptedVersion','license':'cc-by-nc'}]}
        options=access.unpaywall_candidates('10.5555/test',get=lambda url:data)
        self.assertEqual(len(options),2)
        self.assertEqual(options[0]['version'],'acceptedVersion')
        self.assertFalse(options[0]['redistribution_granted'])
        self.assertEqual(options[0]['license'],'cc-by-nc')
        with self.assertRaisesRegex(ValueError,'identity'):
            access.unpaywall_candidates('10.5555/wrong',get=lambda url:data)

    def test_core_only_accepts_exact_identifier(self):
        data={'results':[{'doi':'10.5555/wrong','downloadUrl':'https://www.econstor.eu/wrong.pdf'},
                         {'doi':'10.5555/test','downloadUrl':'https://www.econstor.eu/right.pdf'}]}
        options=access.core_candidates('10.5555/test',get=lambda url:data)
        self.assertEqual([o['url'] for o in options],['https://www.econstor.eu/right.pdf'])

    def test_safe_hosts_do_not_allow_local_or_lookalike_domains(self):
        for url in ('http://www.econstor.eu/p.pdf','https://127.0.0.1/p.pdf',
                    'https://www.econstor.eu.evil.test/p.pdf','https://u:p@www.econstor.eu/p.pdf'):
            self.assertFalse(access.safe_url(url))
        self.assertTrue(access.safe_url('https://www.econstor.eu/p.pdf'))

    def test_challenge_page_cannot_be_promoted(self):
        raw=b'<main>Making sure you are not a bot! captcha</main>'
        with self.assertRaisesRegex(ValueError,'challenge'):
            access.document_from_html(raw,{'title':'Article'},'https://www.econstor.eu/paper')

    def test_no_model_does_not_fetch_any_article(self):
        retriever=Mock()
        stats=reading.process([{'kind':'scholarly','doi':'10.5555/test'}],None,retriever=retriever)
        self.assertTrue(stats['skipped_no_model'])
        retriever.assert_not_called()

    def test_second_pass_must_support_every_claim(self):
        chunk={'id':'C0001','text':'The classroom comparison involved students who discussed their decisions after completing the task.'}
        claim={'field':'study_design','text':'Participants discussed decisions after finishing the classroom task in the reported comparison.',
               'quote':'students who discussed their decisions after completing'}
        with patch.object(reading,'model_json',side_effect=[{'claims':[claim]}, {'supported':[],'rejected':[0]}]):
            with self.assertRaisesRegex(ValueError,'verification'):
                reading.read_chunk(Mock(),chunk,'scholarly','A title')

    def test_finished_notes_keep_locations_but_not_quotes(self):
        doc=access.Document([{'location':'page:1','text':'Evidence anchor covers exactly these source words and additional context.'}],
                            'https://www.econstor.eu/paper.pdf','acceptedVersion',{'evidence_status':'full_document_retrieved'})
        note={'field':'limitations','text':'This comparison does not justify conclusions about longer term independent learning outcomes.',
              'quote':'Evidence anchor covers exactly these source words'}
        with patch.object(reading,'read_chunk',return_value=[note]):
            result=reading.synthesize(doc,Mock(),'scholarly','A title')
        self.assertEqual(result['coverage']['chunks_processed'],result['coverage']['chunks_total'])
        self.assertEqual(result['claim_evidence'][0]['locations'][0]['location'],'page:1')
        self.assertNotIn('quote',result['claim_evidence'][0])
        self.assertNotIn(note['quote'],json.dumps(result))
        self.assertIn('not_independently_reviewed',result['coverage']['review_status'])


if __name__=='__main__': unittest.main()

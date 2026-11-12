"""Deterministic protocol tests, not an evaluation of the local model's judgment."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compose_issue as composer
import test_compose_issue


class EditorialQualityGateTests(unittest.TestCase):
    def fixture(self):
        draft, packet = test_compose_issue.CompositionTests().fixture()
        draft.update(citation_schema_version=1, source_note='')
        return draft, packet

    def receipt(self, draft, packet, passed=True):
        passage = draft['signals'][0]['text'][:85]
        return {'decision':'pass' if passed else 'revise',
                'checks':[{'criterion':criterion,'pass':passed,
                           'reason':'This specific passage identifies the comparison and its evidence boundary clearly.',
                           'example':passage} for criterion in composer.REVIEW_CRITERIA],
                'source_checks':[{'key':p['key'], 'quote':'did not establish lasting independent learning',
                                  'claim':passage, 'supported':True} for p in packet],
                'issues':[] if passed else ['Signal 1: replace the vague opening with named authors and the measured outcome.']}

    def mock_responses(self, *values):
        model=Mock()
        model.create_chat_completion.side_effect=[{'choices':[{'message':{'content':json.dumps(v)}}]} for v in values]
        return model

    def test_modern_disclosure_is_once_not_a_forced_disclaimer_in_every_section(self):
        draft, packet=self.fixture()
        for p in packet:p.update(preprint=True)
        draft['source_note']=composer.source_disclosure(packet)
        result=composer.validate(draft,packet)
        self.assertIn('peer review is unverified',result['source_note'])
        self.assertNotIn('preprint',result['signals'][0]['text'])
        draft['signals'][0]['text'] += ' This proves a learning benefit.'
        with self.assertRaisesRegex(ValueError,'unsupported peer-review or causal'):
            composer.validate(draft,packet)

    def test_named_source_citations_are_required_for_modern_drafts(self):
        draft,packet=self.fixture()
        composer.validate(copy.deepcopy(draft),packet)
        draft['signals'][0]['citations']=[]
        with self.assertRaisesRegex(ValueError,'explicit inline citation'):
            composer.validate(draft,packet)
        draft,packet=self.fixture()
        draft['signals'][0]['citations'][0]['text']='S1'
        with self.assertRaisesRegex(ValueError,'recognizable author'):
            composer.validate(draft,packet)

    def test_single_source_theme_is_better_than_a_forced_pair(self):
        draft,packet=self.fixture()
        for index,section in enumerate(draft['signals']):
            section['evidence']=[{'key':packet[index]['key'],'quote':'did not establish lasting independent learning'}]
            section['text']='Source '+str(index+1)+' examines the question. '+section['text'].split('address this question. ',1)[1]
            section['citations']=[{'key':packet[index]['key'],'text':'Source '+str(index+1)}]
        composer.validate(draft,packet)

    def test_review_requires_specific_complete_assessment_not_a_rubber_stamp(self):
        draft,packet=self.fixture()
        receipt=self.receipt(draft,packet)
        composer.validate_editorial_review(receipt,draft,packet)
        for corrupt in ('empty','missing_source','invented_evidence','unsupported','contradiction','invented_passage'):
            bad=copy.deepcopy(receipt)
            if corrupt=='empty':bad['checks']=[]
            if corrupt=='missing_source':bad['source_checks'].pop()
            if corrupt=='invented_evidence':bad['source_checks'][0]['quote']='Words never present in the supplied source'
            if corrupt=='unsupported':bad['source_checks'][0]['supported']=False
            if corrupt=='contradiction':bad['issues']=['A real issue remains']
            if corrupt=='invented_passage':bad['checks'][0]['example']='A sentence that the draft never contained.'
            with self.subTest(corrupt=corrupt),self.assertRaises(ValueError):
                composer.validate_editorial_review(bad,draft,packet)

    def test_rejected_final_review_never_rewrites_approved_themes(self):
        draft,packet=self.fixture()
        model=self.mock_responses(self.receipt(draft,packet,False))
        progress = composer.Progress(composer.MemoryStore(), composer.MODEL)
        audit={}
        for _ in range(2):
            with self.assertRaisesRegex(ValueError,'still requires changes'):
                composer.review_and_revise(model,draft,packet,audit,progress)
        self.assertEqual(model.create_chat_completion.call_count,1)
        self.assertTrue(all(x['decision']=='revise' for x in audit['editorial_reviews']))
        self.assertTrue(all(len(c.kwargs['messages'])==2 for c in model.create_chat_completion.call_args_list))

    def test_malformed_review_cannot_license_publication_or_reset_on_restart(self):
        draft,packet=self.fixture()
        model=self.mock_responses({}, {})
        store = composer.MemoryStore()
        for _ in range(2):
            with self.assertRaisesRegex(ValueError,'correction budget exhausted'):
                composer.review_and_revise(model,draft,packet,{},composer.Progress(store,composer.MODEL))
        self.assertEqual(model.create_chat_completion.call_count,2)

    def test_evidence_budgets_end_at_sentences_not_half_a_qualification(self):
        original='The study measured an immediate outcome. This does not establish lasting learning.'
        self.assertEqual(composer.evidence_excerpt(original,55),'The study measured an immediate outcome.')
        self.assertEqual(composer.evidence_excerpt('One long sentence without a stop',5),'One long sentence without a stop')

if __name__=='__main__':unittest.main()

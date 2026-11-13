import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import publish_deadline as deadline
from edition_schedule import canonical_edition_date
from edition_references import QUALITATIVE_PROSE, section_response_schema, resolve_section_references, source_claims
from compose_issue import validate_design_claims, pending, validate_editorial_review, REVIEW_CRITERIA


class DeadlineTests(unittest.TestCase):
    now = dt.datetime(2026, 11, 9, 17, tzinfo=dt.timezone.utc)

    def root(self, tmp):
        root = Path(tmp); (root/'data').mkdir()
        return root

    def test_before_deadline_never_freezes_a_coverage_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.root(tmp)
            self.assertEqual(deadline.publish(root, self.now.replace(hour=16, minute=29))['status'], 'before_cutoff')
            self.assertFalse((root/'data/approved-issues').exists())

    def test_missing_sources_or_database_cannot_block_an_honest_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.root(tmp)
            result=deadline.publish(root,self.now)
            self.assertEqual(result['status'],'coverage_published')
            self.assertEqual(result['source_count'],0)
            issue=json.loads((root/'data/approved-issues/2026-11-09.json').read_text())
            deadline.validate_coverage(issue)
            self.assertIn('No eligible',issue['signals'][0]['text'])
            self.assertEqual(deadline.publish(root,self.now+dt.timedelta(days=2))['status'],'edition_exists')
            self.assertEqual(canonical_edition_date(root,'2026-11-11'),'2026-11-09')
            self.assertEqual(canonical_edition_date(root,'2026-11-16'),'2026-11-16')

    def test_existing_full_edition_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.root(tmp);folder=root/'data/approved-issues';folder.mkdir()
            path=folder/'2026-11-09.json'
            path.write_text(json.dumps({'status':'published','edition_date':'2026-11-09','headline':'Checked analysis'}))
            before=path.read_bytes()
            self.assertEqual(deadline.publish(root,self.now)['status'],'edition_exists')
            self.assertEqual(path.read_bytes(),before)

    def test_stale_week_is_not_relabelled_as_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=self.root(tmp)
            (root/'data/public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-02'},'items':[{'title':'Old record'}]}))
            self.assertEqual(deadline.eligible_shelf(root,'2026-11-09'),[])

    def test_no_rejected_generated_prose_can_enter_coverage_template(self):
        issue=deadline.coverage_issue('2026-11-09','01',[])
        for mutation in ('deck','letter','editorial_note'):
            bad=copy.deepcopy(issue);bad[mutation]='AI causes better learning.'
            with self.subTest(mutation=mutation),self.assertRaisesRegex(ValueError,'fixed'):
                deadline.validate_coverage(bad)

    def test_source_shelf_rechecks_dates_depth_duplicates_and_revocations(self):
        actual=json.loads((deadline.ROOT/'data/editorial-weekly.json').read_text())
        # A small realistic fixture, preserving its actual verified date evidence.
        item=actual['items'][0]
        date=actual['run']['date']
        with tempfile.TemporaryDirectory() as tmp:
            root=self.root(tmp)
            invalid=copy.deepcopy(item);invalid['published']='2008-01-01';invalid['title']='Wrong week'
            citation=copy.deepcopy(item);citation['title']='No substantive material';citation['reading']={'level':'citation_only'}
            changed=copy.deepcopy(item);changed['title']='Revoked reading';changed['original_reading']={'old':True}
            (root/'data/editorial-weekly.json').write_text(json.dumps({'run':{'date':date},'items':[item,item,invalid,citation,changed]}))
            def current(x,**kwargs):
                x=copy.deepcopy(x)
                if x['title']=='Revoked reading':x.pop('original_reading')
                return x
            with patch.object(deadline,'public_record',side_effect=current):
                shelf=deadline.eligible_shelf(root,date)
            self.assertEqual(len(shelf),1)
            deadline.validate_coverage(deadline.coverage_issue(date,'01',shelf))

    def test_independent_workflow_has_no_model_or_database_gate(self):
        path=deadline.ROOT/'.github/workflows/weekly-release.yml'
        workflow=path.read_text()
        self.assertIn("cron: '5 12,13 * * 1'",workflow)
        self.assertIn('python scripts/publish_deadline.py',workflow)
        for blocked in ('needs_model', 'final_reading.outputs.ready', 'pip install', 'SUPABASE', 'LOCAL_ISSUE_MODEL'):
            self.assertNotIn(blocked,workflow)
        self.assertIn('Meet weekly publication deadline',(deadline.ROOT/'.github/workflows/publish.yml').read_text())


class ObservedFailureTests(unittest.TestCase):
    def test_string_grammar_cannot_consume_json_delimiters(self):
        import re
        pattern=QUALITATIVE_PROSE['pattern']
        self.assertTrue(re.fullmatch(pattern,'A plain qualitative sentence.'))
        for bad in ['A year 2026.', 'Ends here"},"injected":"yes', 'A\\path','Two\nlines']:
            self.assertIsNone(re.fullmatch(pattern,bad))

    def test_survey_caveat_does_not_erase_causal_claim(self):
        s={'key':'S4','evidence':'A cross-sectional survey measured intention to use GenAI.'}
        for text in ['Expected usefulness influenced willingness to use AI.',
                     'Anxiety had a negative impact on intention. Causality cannot be established.']:
            with self.assertRaisesRegex(ValueError,'Cross-sectional'):
                validate_design_claims(text,s)
        validate_design_claims('Anxiety was associated with lower willingness to use AI.',s)

    def test_reversed_strain_score_is_not_a_health_improvement(self):
        s={'key':'S2','evidence':'Following reverse coding, higher physical scores indicated less strain.'}
        with self.assertRaisesRegex(ValueError,'strain scale'):
            validate_design_claims('Adults experienced improvements in physical health.',s)
        validate_design_claims('Participants generally reported limited physical strain.',s)

    def test_critic_cannot_select_a_harmless_heading_instead_of_source_claims(self):
        source={'key':'S4','title':'Ghana survey'}
        paragraph='Davor: Expected usefulness caused academic achievement.'
        draft={'signals':[{'title':'An open question','text':paragraph+'\n\nA separate question for discussion.',
                           'evidence':[{'key':'S4'}],'citations':[{'key':'S4','text':'Davor:'}]}],
               'tension':{'text':'','evidence':[]}}
        self.assertEqual(source_claims(draft,source),paragraph)

    def test_discussion_and_missing_details_do_not_become_measured_results(self):
        s={'key':'S1','evidence':'methods: Students used an animation lesson.\ninterpretation: The authors discuss reduced cognitive load.'}
        for text in ['Found that AI content reduces cognitive load.',
                     'The study did not address physical health.']:
            with self.assertRaises(ValueError):validate_design_claims(text,s)
        validate_design_claims('The authors interpret the lesson in terms of cognitive load. The available passages leave physical health unresolved.',s)


if __name__=='__main__':unittest.main()

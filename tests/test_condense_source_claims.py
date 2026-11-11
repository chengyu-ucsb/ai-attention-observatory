"""Synthetic source-only regressions: proposals and pilots are not results."""
import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from condense_readings import (
 annotate, condensed, readable_excerpt, reported_result,
 reported_result_bundle, source_snippet,
)


class FindingClaimTests(unittest.TestCase):
 def test_hypothesis_statements_never_become_observed_findings(self):
  for source in [
   'H2: Digital anxiety is negatively associated with intention to use AI.',
   '(H2a): Digital anxiety is negatively associated with intention to use AI.',
   'Hypothesis two proposed that digital anxiety is negatively associated with AI use.',
   'Furthermore, Hypothesis two stated that anxiety is negatively associated with AI use.',
   'We hypothesized that digital anxiety was negatively associated with intention to use AI.',
   'According to H2, digital anxiety is negatively associated with intention to use AI.',
  ]:
   with self.subTest(source=source):
    self.assertEqual(reported_result(source), '')
    self.assertEqual(reported_result_bundle(source), '')

 def test_observed_result_supporting_a_hypothesis_remains_eligible(self):
  hypothesis='H2: Digital anxiety is negatively associated with intention to use AI.'
  observed=('The results showed that digital anxiety was negatively associated with '
            'intention to use AI (beta = -0.24, p = .004), supporting Hypothesis 2.')
  source=hypothesis+' '+observed
  self.assertEqual(reported_result(source,'Digital anxiety and intention to use AI'),observed)
  self.assertEqual(reported_result_bundle(source),readable_excerpt(observed,limit=600))

 def test_explicit_headings_are_boundaries_not_evidence(self):
  heading='Digital anxiety is negatively associated with intention to use AI.'
  measured='The analysis revealed that digital anxiety was not significantly associated with AI use (p = .31).'
  for source in [
   '<h3>'+heading+'</h3><p>'+measured+'</p>',
   '### '+heading+'\n'+measured,
   '4.2 '+heading+'\n'+measured,
   '4.2 '+heading+' '+measured,
  ]:
   with self.subTest(source=source):
    self.assertEqual(reported_result(source),measured)
  self.assertEqual(reported_result('<h3>'+heading+'</h3>'),'')

 def test_observed_null_is_not_filtered_out_by_the_hypothesis_guard(self):
  null=('Social influence was not significantly associated with intention to use AI '
        '(beta = -0.03, p = .42).')
  self.assertEqual(reported_result(null),null)

 def test_adjacent_negative_and_null_contrasts_remain_intact(self):
  positive='Results showed that AI use was associated with higher self-reported attention.'
  negative='However, AI use was negatively associated with independent task performance.'
  null='Further, AI use was not significantly associated with accuracy on the delayed test (p = .28).'
  source=' '.join([positive,negative,null])
  result=reported_result_bundle(source,'AI and attention')
  self.assertEqual(result,' '.join([readable_excerpt(positive,limit=600),negative,null]))
  self.assertNotIn('…',result)

 def test_bundles_do_not_cross_heading_or_hypothesis_boundaries(self):
  main='Results showed that AI use was associated with higher self-reported attention.'
  other='However, AI use was negatively associated with independent task performance.'
  for boundary in [
   '<h3>Independent task performance</h3>',
   '\n### Independent task performance\n',
   'H2: AI use is negatively associated with task performance. ',
  ]:
   with self.subTest(boundary=boundary):
    self.assertEqual(reported_result_bundle(main+' '+boundary+other,'AI and attention'),
                     readable_excerpt(main,limit=600))

 def test_finding_bounds_drop_instead_of_clipping_a_claim(self):
  source='The results showed that digital anxiety was negatively associated with intention to use AI.'
  self.assertEqual(reported_result(source,maxlen=len(source)-1),'')
  self.assertEqual(reported_result_bundle(source,limit=len(source)-1),'')
  self.assertEqual(reported_result(source,maxlen=len(source)),source)


class MainStudyMethodTests(unittest.TestCase):
 def test_short_pilot_cues_are_kept_before_sample_selection(self):
  sample='A total of 24 students participated in the study.'
  for cue in [
   'Pilot study. ', 'The pilot was first run. ', 'Content validity. ',
   'Pilot study\n', '### Pilot study\n', '<h3>Pilot study</h3>',
  ]:
   with self.subTest(cue=cue):
    self.assertEqual(source_snippet(cue+sample,'approach'),'')
    self.assertEqual(condensed(cue+sample,'approach'),'')

 def test_short_main_study_cues_reset_pilot_context(self):
  pilot='Pilot study. A total of 24 students participated in the study. '
  main='A total of 286 undergraduate students participated in the study.'
  for cue in [
   'Main study. ', 'The main study began. ', '\nMain study\n',
   '\n### Main study\n', '<h3>Main study</h3>',
  ]:
   with self.subTest(cue=cue):
    self.assertEqual(source_snippet(pilot+cue+main,'approach'),main)
    self.assertEqual(condensed(pilot+cue+main,'approach'),main)

 def test_pilot_only_sources_do_not_invent_a_main_sample(self):
  for source in [
   'The questionnaire was pilot-tested with a sample of 24 students, including eight cognitive interviews.',
   'The pilot study tested questionnaire clarity. A total of 24 students participated in the study.',
   'Content validity was assessed before recruitment. The questionnaire was completed by 24 participants.',
   'Instrument validation involved a sample of 24 students completing the questionnaire.',
   'The questionnaire was validated using interviews with 24 participants.',
   'We validated the questionnaire with a sample of 24 students.',
   'The questionnaire was pre-tested with a sample of 24 students.',
   'We pretested the instrument with 24 participants.',
   'Questionnaire pretesting used interviews with 24 students.',
  ]:
   with self.subTest(source=source):
    self.assertEqual(source_snippet(source,'approach'),'')
    self.assertEqual(condensed(source,'approach'),'')

 def test_pretest_posttest_main_study_design_is_not_a_pilot(self):
  for design in ['pre-test/post-test','pretest-posttest','pre-test and post-test']:
   source='The researchers used a '+design+' experimental design with 286 students.'
   with self.subTest(design=design):
    self.assertEqual(source_snippet(source,'approach'),source)
    self.assertEqual(condensed(source,'approach'),source)

 def test_baseline_pretest_does_not_taint_the_main_sample(self):
  baseline='Participants completed a pre-test before random assignment to the two teaching conditions.'
  main='A total of 286 students participated in the study.'
  self.assertEqual(source_snippet(baseline,'approach'),baseline)
  self.assertEqual(source_snippet(baseline+' '+main,'approach'),main)
  self.assertEqual(condensed(baseline+' '+main,'approach'),main)

 def test_real_sample_is_selected_after_pilot_or_instrument_validation(self):
  main='In the main study, a total of 286 undergraduate students participated in the survey.'
  for preliminary in [
   'The questionnaire was pilot-tested on a sample of 24 students.',
   'Questionnaire validation used interviews with 24 students.',
  ]:
   with self.subTest(preliminary=preliminary):
    self.assertEqual(source_snippet(preliminary+' '+main,'approach'),main)

 def test_real_sample_before_pilot_does_not_need_a_method_keyword(self):
  main='A total of 286 undergraduate students participated in the study.'
  source=('The study used a quantitative cross-sectional survey design. '+main+
          ' The study was pilot-tested on a sample of 24 students, of whom eight were interviewed.')
  self.assertEqual(source_snippet(source,'approach'),main)

 def test_pilot_context_can_end_before_a_separate_main_sample_sentence(self):
  source=('The pilot study assessed questionnaire clarity. A total of 24 students participated in the pilot. '
          'The main study then began at two colleges. A total of 286 undergraduate students participated in the study.')
  self.assertEqual(source_snippet(source,'approach'),source.rsplit('. ',1)[1])

 def test_target_or_planned_sample_is_not_a_reported_sample(self):
  for source in [
   'The planned sample comprised 286 students recruited from two colleges.',
   'The investigators aimed to recruit 286 participants in the main survey.',
  ]:
   self.assertEqual(source_snippet(source,'approach'),'')

 def test_approach_budget_does_not_clip_sample_or_promote_pilot(self):
  main='In the main study, a total of 286 undergraduate students participated in the survey.'
  pilot='The survey was pilot-tested on a sample of 24 students.'
  self.assertEqual(source_snippet(pilot+' '+main,'approach',limit=len(main)-1),'')
  self.assertEqual(source_snippet(pilot+' '+main,'approach',limit=len(main)),main)

 def test_abstract_fallback_and_source_input_remain_truthful(self):
  pilot='The questionnaire was pilot-tested on a sample of 24 students.'
  hypothesis='H2: Digital anxiety is negatively associated with intention to use AI.'
  main='A total of 286 undergraduate students participated in the study.'
  measured='The results showed that digital anxiety was not significantly associated with AI use (p = .31).'
  record={'kind':'scholarly','title':'Digital anxiety and AI use',
          'abstract_text':main+' '+measured,
          'analysis':{'methods':pilot,'results':hypothesis},
          'reading':{'level':'full_text','methods':pilot,'findings':hypothesis}}
  original=copy.deepcopy(record)
  digest=annotate(record)['reading']['digest']
  self.assertEqual(record,original)
  self.assertEqual(digest['approach'],main)
  self.assertEqual(digest['approach_source'],'abstract')
  self.assertEqual(digest['finding'],readable_excerpt(measured,limit=600))
  self.assertEqual(digest['finding_source'],'abstract')
  self.assertEqual(digest['interpretation'],'')

 def test_pilot_and_hypothesis_without_other_evidence_fail_closed(self):
  record={'kind':'scholarly','title':'Digital anxiety and AI use',
          'analysis':{'methods':'The questionnaire was pilot-tested on a sample of 24 students.',
                      'results':'H2: Digital anxiety is negatively associated with intention to use AI.'},
          'reading':{'level':'full_text'}}
  digest=annotate(record)['reading']['digest']
  for field in ['approach','finding']:
   self.assertEqual(digest[field],'')
   self.assertEqual(digest[field+'_source'],'none')


if __name__=='__main__':unittest.main()

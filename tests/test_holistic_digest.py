"""Preserve useful designs, material result contrasts and real constraints."""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from condense_readings import annotate, reported_result_bundle, source_snippet


class HolisticDigestTests(unittest.TestCase):
 def test_adjacent_cost_and_null_are_kept_with_main_result(self):
  source=('Results indicated that students using AI experienced significantly lower cognitive load. '
          'However, these students demonstrated lower-quality reasoning than the comparison group. '
          'Further, the groups did not differ significantly in their recommendations.')
  result=reported_result_bundle(source)
  self.assertIn('lower cognitive load',result)
  self.assertIn('lower-quality reasoning',result)
  self.assertIn('did not differ significantly',result)
  self.assertNotIn('…',result)

 def test_contrast_hypothesis_does_not_become_an_outcome(self):
  source=('Results showed that students using AI reported lower cognitive load. '
          'However, future research should test whether AI increased independent learning.')
  self.assertNotIn('future',reported_result_bundle(source))

 def test_contrast_about_previous_study_is_not_this_result(self):
  source=('Results showed that students using AI reported lower cognitive load. '
          'However, previous research found higher task performance in another population.')
  self.assertNotIn('previous',reported_result_bundle(source))

 def test_no_extension_from_measurement_diagnostic(self):
  source=('Results showed that students using AI reported lower cognitive load. '
          'However, the measurement model showed lower reliability than expected.')
  self.assertNotIn('reliability',reported_result_bundle(source))

 def test_bundle_does_not_clip_a_sentence_to_fit(self):
  result=reported_result_bundle(
   'Results showed that students using AI reported lower cognitive load. '
   'However, these students demonstrated lower-quality reasoning than the comparison group.',limit=90)
  self.assertEqual(result,'Students using AI reported lower cognitive load.')

 def test_boilerplate_limitation_intro_is_skipped(self):
  self.assertEqual(source_snippet('This study, while informative, has several limitations.','limitations'),'')
  source='This study has several limitations. The cross-sectional design cannot establish the direction of the relationships.'
  self.assertEqual(source_snippet(source,'limitations'),source.split('. ',1)[1])

 def test_explicit_abstract_design_can_beat_generic_fulltext_procedure(self):
  r={'kind':'scholarly','title':'AI research task','abstract_text':
     'A total of 91 university students were randomly assigned to use either an AI assistant or a search engine for the research task.',
     'analysis':{'methods':'The participants answered preliminary demographic questions before the main task.'},
     'reading':{'level':'full_text'}}
  d=annotate(r)['reading']['digest']
  self.assertIn('91 university students',d['approach'])
  self.assertEqual(d['approach_source'],'abstract')

 def test_future_research_and_other_study_are_not_methods(self):
  for source in [
   'Given the cross-sectional design, longitudinal studies employing objective measures of media use are needed to clarify directionality.',
   'One study highlights that AI-driven interventions outperform randomized approaches.']:
   self.assertEqual(source_snippet(source,'approach'),'')

 def test_real_specific_limitations_are_preserved(self):
  for source in [
   'A main limitation of this review is the possibility of misrepresenting the actual body of research.',
   'Additionally, we identified and discussed bias limitations of the evaluation technique.']:
   self.assertEqual(source_snippet(source,'limitations'),source)

 def test_short_intervening_caveat_breaks_adjacency(self):
  source=('Results showed that AI use was associated with higher performance. '
          'This was not a causal test. '
          'However, the comparison group demonstrated lower scores.')
  self.assertNotIn('comparison group',reported_result_bundle(source))

 def test_interpretation_and_named_prior_study_are_not_added(self):
  for addition in [
   'However, it is possible that the groups did not show improvement because the test was insensitive.',
   'However, Smith et al. (2020) found that performance was lower in their sample.']:
   source='Results showed that AI use was associated with higher performance. '+addition
   self.assertNotIn('However',reported_result_bundle(source))

 def test_adjacent_explicit_null_needs_no_transition_word(self):
  source=('Results showed that students using AI reported lower cognitive load. '
          'The groups did not differ significantly in their final recommendations.')
  self.assertIn('did not differ significantly',reported_result_bundle(source))

 def test_real_cognitive_ease_record_retains_countervailing_results(self):
  r=next(r for r in json.loads((ROOT/'data/library.json').read_text())
         if r.get('doi')=='10.1016/j.chb.2024.108386')
  d=annotate(r)['reading']['digest']
  self.assertIn('lower-quality reasoning',d['finding'])
  self.assertIn('lower-quality reasoning',d['idea'])
  self.assertLessEqual(len(d['idea']),230)
  self.assertIn('did not differ significantly',d['finding'])
  self.assertEqual(d['finding_source'],'abstract')
  self.assertIn('91 university students',d['approach'])
  self.assertEqual(d['approach_source'],'abstract')
  self.assertIn('absence',d['limitation'])
  self.assertNotEqual(d['limitation'],'This study, while informative, has several limitations.')
  self.assertEqual(d['status'],'automatically_condensed_source_text')

if __name__=='__main__':unittest.main()

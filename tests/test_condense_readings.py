"""Readable research digest regression checks. No fabricated findings or figures."""
import pathlib,sys,unittest,json
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
from condense_readings import clean,condensed,annotate,concept_tags,reported_result
class CondensedReadingTests(unittest.TestCase):
 def test_section_numbers_and_reference_artifacts_removed(self):
  s="4. Results 4.1. Common method bias and discriminant validity of the measurement structure To evaluate the discriminant validity of the four study constructs, nested confirmatory factor analyses were conducted ( Table 3 )."
  result=clean(s)
  self.assertNotIn("4. Results",result)
  self.assertNotIn("( Table 3 )",result)
 def test_finding_not_model_fit_artifact(self):
  s=("4. Results 4.1. Measurement model The four-factor measurement model fit the data well: CFI = 0.97, RMSEA = 0.04. "
     "The authors found that more frequent AI use was associated with higher perceived offloading among the respondents.")
  result=condensed(s,"finding")
  self.assertTrue("offloading" in result or not result)
  self.assertNotIn("CFI",result)
 def test_do_not_invent_empirical_findings(self):
  paper={"kind":"scholarly","doi":"10.1234/idea","title":"A conceptual examination of AI and attention",
   "reading":{"level":"abstract","overview":"This article proposes a framework of three ideas.","methods":"","findings":"","interpretation":"","limitations":""}}
  digest=annotate(paper)["reading"]["digest"]
  self.assertEqual(digest["finding"],"")
  self.assertEqual(digest["status"],"automatically_condensed_source_text")
 def test_curated_note_keeps_source_grounded_claim(self):
  paper={"kind":"scholarly","doi":"10.3389/feduc.2026.1861548","title":"The illusion of cognitive independence",
   "reading":{"level":"full_text","methods":"Online survey using Prolific.","findings":"Three learner profiles emerged.","limitations":"Cross-sectional design."}}
  digest=annotate(paper)["reading"]["digest"]
  self.assertIn("Three learner profiles",digest["finding"])
  self.assertIn("cannot establish the direction",digest["limitation"])
  self.assertEqual(digest["status"],"editorially_written_from_indexed_sections")
 def test_tags_are_source_named_not_unverified_causal_paths(self):
  paper={"kind":"scholarly","title":"GenAI literacy, cognitive offloading and critical thinking",
    "reading":{"overview":"A survey of student learning.","findings":""}}
  tags=concept_tags(paper)
  self.assertIn("AI literacy",tags)
  self.assertIn("Critical thinking",tags)
  self.assertLessEqual(len(tags),3)
 def test_methodological_diagnostics_are_not_presented_as_results(self):
  diagnostic=("4. Results 4.1. Common method bias. Harman's single-factor test "
              "indicated that the first factor explained 35 percent of variance. "
              "The measurement model showed adequate fit with CFI = 0.95. "
              "Cronbach alpha suggested that all scales had acceptable reliability.")
  self.assertEqual(reported_result(diagnostic,"AI literacy and critical thinking"),"")
 def test_real_result_beats_preceding_measurement_checks(self):
  content=("Harman's single-factor test was conducted to test common method bias. "
           "Cronbach alpha values indicated adequate reliability. "
           "Specifically, AI literacy was positively correlated with critical thinking "
           "and AI-assisted problem-solving among surveyed students.")
  claim=reported_result(content,"AI literacy and critical thinking")
  self.assertIn("positively correlated",claim)
  self.assertNotIn("Cronbach",claim)
 def test_indexed_papers_have_source_labelled_results_or_explicit_omission(self):
  records=json.loads((ROOT/"data/library.json").read_text())
  records={r.get("doi"):r for r in records}
  # Psychometric diagnostics occur first in the full-text extract.
  literacy=annotate(records["10.58304/ijts.260930"])["reading"]["digest"]
  self.assertNotIn("Harman",literacy["finding"])
  self.assertNotIn("single-factor",literacy["finding"])
  self.assertIn("AI",literacy["finding"])
  self.assertIn(literacy["finding_source"],{"full_text","abstract"})
  # The full-text extract covers instrument reliability; the source abstract
  # explicitly reports the appraisal paths.
  workers=annotate(records["10.3389/fpsyg.2026.1960382"])["reading"]["digest"]
  self.assertEqual(workers["finding_source"],"abstract")
  self.assertIn("algorithmic management",workers["finding"].lower())
  self.assertNotIn("Cronbach",workers["finding"])
  # When both the source extract and the truncated abstract lack a result,
  # the site must not relabel CFA diagnostics as empirical findings.
  truncated=annotate(records["10.3389/fpsyg.2026.1939286"])["reading"]["digest"]
  self.assertEqual(truncated["finding"],"")
  self.assertEqual(truncated["finding_source"],"none")
if __name__=="__main__":unittest.main()

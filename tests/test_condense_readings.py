"""Readable research digest regression checks. No fabricated findings or figures."""
import pathlib,sys,unittest,json
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
from condense_readings import clean,condensed,annotate,concept_tags,reported_result,readable_excerpt,CURATED
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
  self.assertIn("Three patterns emerged",digest["finding"])
  self.assertIn("cannot establish cause and effect",digest["limitation"])
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
  self.assertEqual(literacy["finding_source"],"editorial")
  self.assertIn("450",literacy["approach"])
  self.assertIn("20",literacy["approach"])
  # The full-text extract covers instrument reliability; the source abstract
  # explicitly reports the appraisal paths.
  workers=annotate(records["10.3389/fpsyg.2026.1960382"])["reading"]["digest"]
  self.assertEqual(workers["finding_source"],"abstract")
  self.assertIn("algorithmic management",workers["finding"].lower())
  self.assertNotIn("Cronbach",workers["finding"])
  adjacent=annotate(records["10.3389/fpsyg.2026.1930030"])["reading"]["digest"]
  self.assertEqual(adjacent["finding_source"],"editorial")
  self.assertIn("cross-sectional",adjacent["limitation"].lower())
  self.assertIn("did not examine generative AI",adjacent["explain"])
  # When both the source extract and the truncated abstract lack a result,
  # the site must not relabel CFA diagnostics as empirical findings.
  truncated=annotate(records["10.3389/fpsyg.2026.1939286"])["reading"]["digest"]
  self.assertEqual(truncated["finding"],"")
  self.assertEqual(truncated["finding_source"],"none")
 def test_editorial_summaries_are_short_and_idea_first(self):
  for doi,note in CURATED.items():
   for field,limit in [("idea",170),("explain",190),("approach",205),("finding",215),("interpretation",190),("limitation",190)]:
    line=note.get(field,"")
    self.assertLessEqual(len(line),limit,(doi,field,line))
    self.assertNotRegex(line,r"(?i)^\s*(?:the authors|the researchers|this study|we found)\b")
    self.assertNotIn("…",line,(doi,field))
  self.assertGreaterEqual(len(CURATED),9)
 def test_automatic_excerpt_removes_author_centred_lead_without_inventing_a_result(self):
  result=readable_excerpt("The authors found that AI usage was positively associated with reported task-switching.",limit=150)
  self.assertEqual(result,"AI usage was positively associated with reported task-switching.")
  interpret=readable_excerpt("The authors suggest that AI may help workers manage interruptions.",role="interpretation")
  self.assertIn("One interpretation is that",interpret)
  self.assertIn("may help",interpret)
 def test_automatic_digest_preserves_uncertain_language(self):
  paper={"kind":"scholarly","doi":"10.0000/example","title":"Attention and AI",
         "abstract_text":"Data suggested that AI use was associated with higher self-reported attention. This survey involved 100 students.",
         "reading":{"level":"abstract","overview":"The authors found that reported attention was associated with AI use.",
                    "findings":"The authors found that AI use was positively associated with self-reported attention.",
                    "methods":"The authors surveyed 100 students.",
                    "limitations":"These results cannot establish causal effects.","interpretation":""}}
  digest=annotate(paper)["reading"]["digest"]
  self.assertIn("associated",digest["finding"])
  self.assertNotRegex(digest["finding"],r"(?i)^the authors")
if __name__=="__main__":unittest.main()

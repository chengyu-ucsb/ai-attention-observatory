"""Regression tests for the recurring, source-aware visual publishing step."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from build_visuals import visual_spec


class VisualPipelineTests(unittest.TestCase):
 def test_new_scholarly_article_gets_source_based_graphic_without_doi(self):
  record={"kind":"scholarly","title":"A newly published study without a known DOI",
          "reading":{"level":"abstract","digest":{
           "status":"automatically_condensed_source_text",
           "finding_source":"abstract",
           "approach":"A survey of 218 university students.",
           "finding":"Digital interruptions were associated with lower self-reported concentration.",
           "limitation":"Self-reported survey results cannot establish causation."}}}
  visual=visual_spec(record)
  self.assertEqual(visual["kind"],"evidence_snapshot")
  self.assertEqual(visual["basis"],"abstract")
  self.assertEqual(len(visual["blocks"]),3)
  self.assertEqual(visual["blocks"][1]["text"],record["reading"]["digest"]["finding"])
  self.assertNotIn("effect_size",visual)
  self.assertNotIn("p_value",visual)

 def test_new_article_without_verified_result_is_never_presented_as_finding(self):
  record={"kind":"scholarly","reading":{"level":"full_text","digest":{
   "status":"automatically_condensed_source_text",
   "finding_source":"none",
   "approach":"A qualitative interview study of attention habits.",
   "finding":"",
   "limitation":"Transferability across workplaces was not assessed."}}}
  visual=visual_spec(record)
  self.assertEqual(visual["kind"],"research_design")
  self.assertTrue(all(b["label"]!="Reported finding" for b in visual["blocks"]))

 def test_unsupported_result_cannot_become_a_visual_claim(self):
  record={"kind":"scholarly","reading":{"level":"abstract","digest":{
   "approach":"An experiment involving 50 volunteers.",
   "finding":"AI improved cognition by 75%.",
   "finding_source":"none"}}}
  visual=visual_spec(record)
  self.assertNotIn("AI improved",str(visual))
  self.assertEqual(visual["kind"],"research_design")

 def test_empty_or_incomplete_sources_get_the_cover_art_only(self):
  for phrase in ("","The results were mostly unclear and incomplete…"):
   record={"kind":"scholarly","reading":{"level":"abstract","digest":{
    "finding":phrase,"finding_source":"abstract",
    "approach":"This paper has a very long description of its study but does not explain any method."*5}}}
   self.assertEqual(visual_spec(record)["kind"],"illustration_only")

 def test_commentary_does_not_get_empirical_graphics(self):
  record={"kind":"nonacademic","reading":{"level":"curated","digest":{"idea":"Design proposals"}}}
  self.assertEqual(visual_spec(record)["kind"],"illustration_only")


if __name__=="__main__": unittest.main()

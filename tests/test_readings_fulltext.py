"""Regression tests: source Results must not be replaced by Discussion."""
import sys, pathlib, unittest, xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_readings
import enrich
import enrich_openalex_fulltext as oa

class FullTextReadingTests(unittest.TestCase):
 def test_distinguish_findings_from_discussion(self):
  paper={"kind":"scholarly","title":"A test article","abstract_text":"This study examined cognition. The survey included workers. Results suggest some association with task focus.",
   "analysis":{"fulltext_url":"https://example.org/article","provenance":"Licensed full text","methods":"We measured cognitive effort.","results":"The observed difference was two points.","discussion":"The authors suggest an alternative mechanism.","limitations":"The sample was small."}}
  r=build_readings.make_note(paper)
  self.assertEqual(r["level"],"full_text")
  self.assertEqual(r["findings"],"The observed difference was two points.")
  self.assertEqual(r["interpretation"],"The authors suggest an alternative mechanism.")
  self.assertEqual(r["methods"],"We measured cognitive effort.")
 def test_without_results_do_not_invent_findings(self):
  paper={"kind":"scholarly","title":"A conceptual paper","abstract_text":"This conceptual article discusses potential effects of AI assistance on attention and agency at work.",
   "analysis":{"fulltext_url":"https://example.org/article","discussion":"The authors theorize a potential mechanism."}}
  r=build_readings.make_note(paper)
  self.assertEqual(r["level"],"full_text")
  self.assertEqual(r["findings"],"")
  self.assertFalse(r["reported_findings"])
  self.assertEqual(r["interpretation"],"The authors theorize a potential mechanism.")
 def test_europepmc_separates_results_from_discussion(self):
  xml=ET.fromstring('<article><body><sec><title>Study design</title><p>Participants completed two tasks measuring attention and effort over multiple sessions.</p></sec><sec><title>Findings</title><p>Participants in the treatment arm recalled more material at the second assessment.</p></sec><sec><title>Discussion</title><p>The authors propose an interpretation concerning effort and cognitive offloading.</p></sec></body></article>')
  result=enrich.extract_sections(xml)
  self.assertIn("recalled",result["results"])
  self.assertIn("propose",result["discussion"])
  self.assertIn("Participants",result["methods"])
 def test_tei_parser_preserves_section_labels(self):
  xml=ET.fromstring('<TEI><text><body><div><head>Results</head><p>Participants were faster under condition A than condition B in the observed experiment.</p></div><div><head>Discussion</head><p>The authors believe that the difference may relate to familiarity with the interface.</p></div></body></text></TEI>')
  result=oa.extract(xml)
  self.assertIn("faster",result["results"])
  self.assertIn("believe",result["discussion"])

if __name__=="__main__":unittest.main()

"""Licensed PDF fallback tests. PDFs themselves are never saved in the repo."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import enrich_pdf_fulltext as pdf

class PDFRecoveryTests(unittest.TestCase):
 def test_pdf_text_does_not_turn_references_into_results(self):
  lines=[
   "1. Introduction","The field of AI and attention is expanding rapidly.",
   "2. Methods","We recruited 130 students to investigate task-switching with an AI assistant.",
   "3. Results","AI-assisted participants reported more changes of task and less sustained attention.",
   "Additional findings indicated the relationship depended on the kind of AI assistance provided.",
   "4. Discussion","We cannot rule out differences in participant study habits as an alternative explanation.",
   "References","A cited article has many large effects which must not be attached to this study."
  ]
  sections=pdf.collect_sections(lines)
  self.assertIn("130 students",sections["methods"])
  self.assertIn("less sustained attention",sections["results"])
  self.assertNotIn("many large effects",str(sections))
 def test_only_known_openalex_ids_are_accepted_when_doi_missing(self):
  self.assertEqual(pdf.work_url({"url":"https://openalex.org/W7421"}),"https://api.openalex.org/works/W7421")
  self.assertEqual(pdf.work_url({"url":"https://evil.example/W7421"}),"")
  self.assertIn("doi.org",pdf.work_url({"doi":"10.1000/abc"}))
 def test_no_licensed_pdf_does_not_claim_full_text(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"library.json"
   path.write_text(json.dumps([{"kind":"scholarly","doi":"10.1000/nolic","title":"AI attention study"}]))
   work={"best_oa_location":{"license":"other-oa"},"content_urls":{"pdf":"https://content.openalex.org/works/W1.pdf"}}
   with patch.object(pdf,"LIB",path),patch.object(pdf,"fetch",return_value=json.dumps(work).encode()),patch.object(pdf.time,"sleep"):
    result=pdf.run()
   self.assertEqual(result["fulltexts_recovered"],0)
   record=json.loads(path.read_text())[0]
   self.assertNotIn("analysis",record)
   self.assertEqual(record["pdf_fulltext_attempt"]["status"],"no_licensed_machine_pdf")
 def test_licensed_pdf_is_extracted_into_index_and_never_stored_as_pdf(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);path=root/"library.json"
   path.write_text(json.dumps([{"kind":"scholarly","doi":"10.1000/yes","title":"AI attention study"}]))
   work={"best_oa_location":{"license":"cc-by","landing_page_url":"https://doi.org/10.1000/yes"},
         "content_urls":{"pdf":"https://content.openalex.org/works/W123.pdf"}}
   data=[json.dumps(work).encode(),b"%PDF-1.7 example"]
   sections={"methods":"We surveyed 130 students using a new AI tool.",
             "results":"Students described increased interruptions during the AI condition.",
             "limitations":"Associations are not causal."}
   with patch.object(pdf,"LIB",path),patch.object(pdf,"fetch",side_effect=data),patch.object(pdf,"extract_pdf",return_value=sections),patch.object(pdf.time,"sleep"):
    result=pdf.run()
   self.assertEqual(result["fulltexts_recovered"],1)
   record=json.loads(path.read_text())[0]
   self.assertEqual(record["analysis"]["results"],sections["results"])
   self.assertIn("pypdf",record["analysis"]["pdf_text_extraction"])
   self.assertEqual(list(root.glob("*.pdf")),[])
 def test_no_results_fails_closed(self):
  self.assertEqual(pdf.extract_pdf(b"not a pdf"),{})
  self.assertEqual(pdf.collect_sections(["Introduction","Research topic","References","The previous literature had large effects."]),{})

if __name__=="__main__":unittest.main()

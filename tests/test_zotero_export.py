"""Public RIS export never includes Zotero private material or full-text records."""
import json
import pathlib
import sys
import tempfile
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from export_zotero_backlog import generate

class PublicRISExportTests(unittest.TestCase):
 def test_only_public_unread_dois_and_deduplicate(self):
  with tempfile.TemporaryDirectory() as d:
   folder=pathlib.Path(d);input=folder/"data.json";output=folder/"review.ris"
   input.write_text(json.dumps([
    {"kind":"scholarly","doi":"10.1000/abc","title":"Study of cognition",
     "authors":["A Researcher"],"published":"2024-09-15","reading":{"level":"abstract"}},
    {"kind":"scholarly","doi":"10.1000/abc","title":"Duplicate","reading":{"level":"abstract"}},
    {"kind":"scholarly","doi":"10.1000/full","title":"Already extracted",
     "reading":{"level":"full_text"}},
    {"kind":"scholarly","doi":"","title":"No identifier","reading":{"level":"abstract"}},
    {"kind":"nonacademic","doi":"10.1000/other","title":"Magazine","reading":{"level":"curated"}}]))
   count=generate(input,output)
   self.assertEqual(count,1)
   ris=output.read_text()
   self.assertIn("TY  - JOUR",ris)
   self.assertIn("DO  - 10.1000/abc",ris)
   self.assertIn("AU  - A Researcher",ris)
   self.assertNotIn("Already extracted",ris)
   self.assertNotIn("Magazine",ris)
 def test_removes_line_breaks_from_citation_fields(self):
  with tempfile.TemporaryDirectory() as d:
   folder=pathlib.Path(d);input=folder/"data.json";output=folder/"review.ris"
   input.write_text(json.dumps([{"kind":"scholarly","doi":"10.1000/testing",
      "title":"Cognitive test\nER  -\nTY  - BOOK",
      "reading":{"level":"abstract"}}]))
   self.assertEqual(generate(input,output),1)
   ris=output.read_text()
   self.assertEqual(sum(line.startswith("TY  - ") for line in ris.splitlines()),1)
   self.assertEqual(sum(line=="ER  -" for line in ris.splitlines()),1)
if __name__=="__main__":unittest.main()

"""Open Wiley publisher reading is distinct from licensed excerpt republication."""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import enrich_wiley_html as wiley
import verified_full_article_notes as notes
import build_readings
import condense_readings

DOI="10.1111/bjet.70094"

def record():
 return {"kind":"scholarly","doi":DOI,
         "title":"Prompt-based emotional scaffolding in generative AI: Effects on self-regulated learning",
         "venue":"British Journal of Educational Technology",
         "abstract_text":"A preregistered experiment randomly assigned 144 high school students to three generative AI chatbot conditions in authentic learning, with measures of enjoyment and learning outcomes.",
         "open_access_license":"cc-by-nc-nd"}

class WileyAccessTests(unittest.TestCase):
 def test_wiley_url_only_for_valid_doi_and_approved_hosts(self):
  self.assertEqual(wiley.url_for(record()),"https://bera-journals.onlinelibrary.wiley.com/doi/"+DOI)
  self.assertEqual(wiley.url_for({"doi":"10.3390/edu.2026.1"}),"")
  self.assertEqual(wiley.url_for({"doi":"10.1111/../bad"}),"")

 def test_readability_check_requires_article_content(self):
  html="<html><head><title>Example</title></head><body>Open Access "+DOI+"<h2>RESULTS</h2><p>Results are presented.</p><h2>DISCUSSION</h2><p>These results suggest different outcomes.</p></body></html>"
  self.assertEqual(wiley.inspect_html(html,DOI),"public_html_verified")
  self.assertEqual(wiley.inspect_html(html,"10.1111/bjet.other"),"doi_mismatch")
  self.assertEqual(wiley.inspect_html(html.replace("<h2>DISCUSSION</h2>",""),DOI),"full_article_not_detected")
  self.assertEqual(wiley.inspect_html(html.replace("Open Access","Paywall"),DOI),"oa_not_confirmed")

 def test_public_html_diagnostic_does_not_store_copyright_text(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/"library.json";path.write_text(json.dumps([record()]))
   original="<h2>RESULTS</h2><p>Protected verbatim words should never be in JSON.</p><h2>DISCUSSION</h2>"
   def fake(url):return "<html>Open Access "+DOI+original+"</html>"
   stats=wiley.run(path=path,today=dt.date(2026,10,22),fetch=fake,limit=3)
   output=path.read_text()
  self.assertEqual(stats["public_html_verified"],1)
  self.assertNotIn("Protected verbatim words",output)
  self.assertIn("public_html_verified",output)
  self.assertNotIn('"analysis"',output)

 def test_access_denied_is_diagnostic_not_fabricated_reading(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/"library.json";path.write_text(json.dumps([record()]))
   def deny(url):raise urllib.error.HTTPError(url,403,"Forbidden",{},None)
   stats=wiley.run(path=path,today=dt.date(2026,10,22),fetch=deny,limit=2)
   stored=json.loads(path.read_text())[0]
  self.assertEqual(stats["publisher_blocked"],1)
  self.assertEqual(stored["wiley_html_attempt"]["status"],"publisher_denied_http_403")
  self.assertNotIn("analysis",stored)

 def test_editorially_checked_notes_are_original_and_readable(self):
  r=record();n=notes.apply([r])
  self.assertEqual(n,1)
  self.assertTrue(r["analysis"]["original_paraphrases_only"])
  self.assertIn("publisher HTML",r["analysis"]["provenance"])
  self.assertIn("not statistically significant",r["analysis"]["results"])
  self.assertIn("25-minute",r["analysis"]["limitations"])
  note=build_readings.make_note(r)
  self.assertEqual(note["level"],"full_text")
  self.assertIn("paraphrased",note["notice"])
  self.assertIn("not statistically significant",note["findings"])
  r["reading"]=note
  digest=condense_readings.annotate(r)["reading"]["digest"]
  self.assertEqual(digest["editorial_basis"],"publisher_full_article_paraphrased")
  self.assertIn("not measured learning gains",digest["idea"])
  notes.apply([r])
  self.assertEqual(r["analysis"]["results"].count("All three groups"),1)

 def test_protect_other_existing_machine_extraction(self):
  r=record();r["analysis"]={"results":"Preexisting source backed data","fulltext_url":"https://example.org/"}
  notes.apply([r])
  self.assertEqual(r["analysis"]["results"],"Preexisting source backed data")

 def test_vertical_year_chart_markup(self):
  js=(ROOT/"app.js").read_text(encoding="utf-8")
  css=(ROOT/"styles.css").read_text(encoding="utf-8")
  self.assertIn('make("div","year-row")',js)
  self.assertIn('bar.style.width=',js)
  self.assertNotIn('bar.style.height=Math.max(3,185*n/max)',js)
  self.assertIn("#year-chart .year-row",css)
  self.assertIn("grid-template-columns:54px minmax(0,1fr) 38px",css)

if __name__=="__main__":unittest.main()

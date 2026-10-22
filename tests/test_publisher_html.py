"""Publisher HTML fallback, deliberately restricted to licensed official sources."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import enrich_publisher_html as publisher

ARTICLE='''<html><head><meta name="citation_doi" content="10.3389/fpsyg.2026.12345"/>
<link rel="license" href="https://creativecommons.org/licenses/by/4.0/"/></head>
<body><nav><h2>Results</h2><p>Unrelated navigation and advertising.</p></nav>
<article><h2>2. Methods</h2><p>We recruited 310 students to examine how a generative AI assistant shaped sustained task attention during a writing exercise.</p>
<h2>3. Results</h2><p>Students relying heavily on the AI system reported more interruptions and less confidence in evaluating answers independently.</p>
<h2>4. Discussion</h2><p>The observed association does not distinguish self-selection from any effect of the technology itself.</p>
<h2>References</h2><p>Previous research has shown large unrelated effects on cognitive processes.</p></article></body></html>'''
class PublisherHTMLTests(unittest.TestCase):
 def test_parse_licensed_full_article_not_nav_or_references(self):
  text,error=publisher.parse(ARTICLE,"10.3389/fpsyg.2026.12345")
  self.assertIsNone(error)
  self.assertIn("310 students",text["methods"])
  self.assertIn("less confidence",text["results"])
  self.assertNotIn("Unrelated navigation",str(text))
  self.assertNotIn("large unrelated effects",str(text))
 def test_denies_unlicensed_source(self):
  text,error=publisher.parse(ARTICLE.replace("creativecommons.org/licenses/by/4.0/","creativecommons.org/licenses/by-nc/4.0/"),"10.3389/fpsyg.2026.12345")
  self.assertEqual(error,"license_not_verified");self.assertEqual(text,{})
 def test_doi_and_host_scope_is_narrow(self):
  self.assertIn("journals/psychology",publisher.url_for("10.3389/fpsyg.2026.12345"))
  self.assertEqual(publisher.url_for("10.1234/anything"),"")
  self.assertEqual(publisher.url_for("javascript://bad"),"")
 def test_saves_real_source_sections_not_html(self):
  with tempfile.TemporaryDirectory() as d:
   file=Path(d)/"library.json"
   file.write_text(json.dumps([{"kind":"scholarly","doi":"10.3389/fpsyg.2026.12345","published":"2026-03-03"}]))
   with patch.object(publisher,"LIB",file),patch.object(publisher,"fetch_article",return_value=(ARTICLE,"https://www.frontiersin.org/articles/verified/full")),patch.object(publisher.time,"sleep"):
    result=publisher.run()
   self.assertEqual(result["new_fulltexts"],1)
   row=json.loads(file.read_text())[0]
   self.assertEqual(row["analysis"]["extraction_version"],3)
   self.assertEqual(row["analysis"]["license"],"cc-by (source webpage verified)")
   self.assertNotIn("<html>",str(row["analysis"]))
if __name__=="__main__":unittest.main()

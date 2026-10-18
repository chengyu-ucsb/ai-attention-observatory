import unittest
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import discover_editorial as ed
import enrich_openalex_fulltext as oa
import build_readings as readings

RSS="""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>How AI tools change focused learning</title>
<link>https://example.org/story</link>
<description>Researchers and product designers discuss whether AI summaries change attention, memory and learning habits.</description>
<pubDate>Sun, 18 Oct 2026 00:00:00 GMT</pubDate><source>Tech Policy Press</source></item>
</channel></rss>"""

ATOM="""<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Generative AI and cognitive offloading in the classroom</title>
<link rel="alternate" href="https://example.org/essay"/>
<updated>2026-10-17T00:00:00Z</updated>
<summary>We examine why AI use can change students' cognitive effort and learning routines.</summary>
<author><name>Example Author</name></author></entry>
</feed>"""

TEI="""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
<div><head>Materials and methods</head><p>We interviewed 50 knowledge workers and analyzed their descriptions of AI and attention.</p></div>
<div><head>Results</head><p>Workers described both benefits and costs for remembering steps after switching tasks.</p></div>
<div><head>Discussion</head><p>The reported effects depend on context and should not be interpreted as experimental causal evidence.</p></div>
</body></text></TEI>"""

class EditorialTests(unittest.TestCase):
 def test_rss(self):
  items=ed.parse_feed(ET.fromstring(RSS))
  self.assertEqual(items[0]["source"],"Tech Policy Press")
  self.assertEqual(items[0]["date"],"2026-10-18")
  self.assertTrue(ed.eligible(items[0]))
 def test_atom(self):
  items=ed.parse_feed(ET.fromstring(ATOM))
  self.assertEqual(items[0]["authors"],["Example Author"])
  self.assertEqual(items[0]["url"],"https://example.org/essay")
  self.assertTrue(ed.eligible(items[0]))
 def test_no_irrelevant(self):
  self.assertFalse(ed.eligible(dict(title="Stock price target",description="AI stock price rises",date="2026-10-18")))
 def test_feed_description_labeled_not_full_text(self):
  item=ed.parse_feed(ET.fromstring(ATOM))[0]
  rec=ed.to_record(item,"The Conversation","Expert commentary")
  self.assertEqual(rec["content_access"],"feed_description")
  self.assertNotIn("findings",rec["preview"].lower())
  self.assertFalse(rec["reading"]["findings"])
 def test_reading_not_fake_findings(self):
  item=ed.parse_feed(ET.fromstring(ATOM))[0]
  r=ed.to_record(item,"The Conversation","Expert commentary")
  self.assertEqual(readings.make_note(r)["findings"],"")
 def test_tei_extraction(self):
  result=oa.extract(ET.fromstring(TEI))
  self.assertIn("interviewed",result["methods"])
  self.assertIn("Workers",result["results"])
  self.assertIn("causal",result["discussion"])

if __name__=="__main__":unittest.main()

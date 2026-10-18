import unittest
from pathlib import Path
import json,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
class ObservatoryTests(unittest.TestCase):
 def test_baseline(self):
  library=json.loads((ROOT/"data/library.json").read_text())
  self.assertIsInstance(library,list)
  self.assertTrue(library)
  for item in library:
   self.assertTrue(item.get("title"))
   self.assertTrue((item.get("url") or "").startswith("https://"))
 def test_weekly(self):
  v=json.loads((ROOT/"data/weekly.json").read_text())
  self.assertIn("items",v);self.assertIn("run",v)
 def test_feed(self):
  f=ROOT/"feed.xml"
  self.assertTrue(f.exists(),"RSS generator must run before tests")
  root=ET.parse(f).getroot()
  self.assertEqual(root.tag,"rss")
 def test_no_false_publication_claim(self):
  text=(ROOT/"index.html").read_text()
  self.assertIn("metadata",text.lower())
  self.assertIn("chengyufang.org",text)
if __name__=="__main__":unittest.main()

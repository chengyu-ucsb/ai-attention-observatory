"""RSS subscription regression tests for the approved editorial issue feed."""
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_newsletter import FEED, build_rss

class WeeklyFeedTests(unittest.TestCase):
 def test_rss_feed_has_permanent_ids_and_dates(self):
  path=ROOT/"issue-feed.xml"
  rss=ET.parse(path).getroot()
  self.assertEqual(rss.tag,"rss")
  self.assertEqual(rss.attrib.get("version"),"2.0")
  ch=rss.find("channel")
  self.assertIsNotNone(ch)
  self.assertTrue(ch.findtext("title"))
  self.assertTrue(ch.findtext("description"))
  self.assertTrue(ch.findtext("link").startswith("https://"))
  self.assertEqual(ch.find("{http://www.w3.org/2005/Atom}link").attrib["href"],FEED)
  self.assertEqual(ch.find("{http://www.w3.org/2005/Atom}link").attrib["rel"],"self")
  items=ch.findall("item")
  self.assertGreaterEqual(len(items),1,"The archive currently contains at least one approved issue.")
  for item in items:
   link=item.findtext("link")
   self.assertTrue(link.startswith("https://"))
   self.assertEqual(item.findtext("guid"),link)
   self.assertEqual(item.find("guid").attrib["isPermaLink"],"true")
   self.assertIn("/issues/",link)
   self.assertTrue(item.findtext("description"))
   self.assertIsNotNone(parsedate_to_datetime(item.findtext("pubDate")).tzinfo)
  self.assertEqual(len({item.findtext("guid") for item in items}),len(items))
  self.assertIsNotNone(parsedate_to_datetime(ch.findtext("lastBuildDate")).tzinfo)

 def test_both_feeds_have_browser_view_without_losing_valid_rss(self):
  for name in ("issue-feed.xml","feed.xml"):
   raw=(ROOT/name).read_text()
   self.assertIn('<?xml-stylesheet type="text/xsl" href="assets/feed.xsl"?>',raw)
   self.assertEqual(ET.fromstring(raw).tag,"rss")
   items=ET.fromstring(raw).findall("./channel/item")
   self.assertTrue(items,"RSS should contain readable entries")
  xsl=ET.parse(ROOT/"assets/feed.xsl").getroot()
  self.assertEqual(xsl.tag,"{http://www.w3.org/1999/XSL/Transform}stylesheet")
 def test_record_rss_uses_cleaned_digest_not_raw_method_checks(self):
  rss=ET.parse(ROOT/"feed.xml").getroot()
  items=rss.findall("./channel/item")
  self.assertGreater(len(items),5)
  self.assertTrue(any("#paper/" in item.findtext("link","") for item in items))
  for item in items:
   note=item.findtext("description","")
   self.assertNotIn("Harman's single-factor",note)
   self.assertNotIn("Cronbach",note)
   self.assertNotIn("Plato’s dialogues show",note)
   self.assertNotIn("The source describes",note)
   self.assertNotIn("One interpretation is that",note)
   self.assertIsNotNone(parsedate_to_datetime(item.findtext("pubDate")).tzinfo)
 def test_subscription_page_preserves_direct_machine_readable_link(self):
  doc=(ROOT/"subscribe.html").read_text()
  self.assertIn("issue-feed.xml",doc)
  self.assertIn("Copy RSS URL",doc)
  self.assertIn('type="application/rss+xml"',doc)
  index=(ROOT/"index.html").read_text()
  self.assertIn('rel="alternate" type="application/rss+xml"',index)
  self.assertIn('href="subscribe.html"',index)

 def test_html_preview_and_archive_exist(self):
  self.assertTrue((ROOT/"newsletter.html").stat().st_size>2000)
  self.assertTrue((ROOT/"issues"/"index.html").stat().st_size>1000)
  archive=list((ROOT/"issues").glob("20??-??-??.html"))
  self.assertTrue(archive)

if __name__=="__main__":unittest.main()

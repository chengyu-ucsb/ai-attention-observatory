"""RSS subscription regression tests for the approved editorial issue feed."""
from datetime import datetime
import copy
import html
from html.parser import HTMLParser
import json
import tempfile
from unittest.mock import patch
from email.utils import parsedate_to_datetime
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_newsletter
from build_newsletter import FEED, build_rss

class VisibleText(HTMLParser):
 def __init__(self,value):
  super().__init__(convert_charrefs=True);self.parts=[];self.feed(value)
 def handle_data(self,data):self.parts.append(data)
 def handle_endtag(self,tag):
  if tag in ('p','div','h1','h2','h3','li','summary'):self.parts.append(' ')
 def text(self):return ' '.join(''.join(self.parts).split())

class WeeklyFeedTests(unittest.TestCase):
 def latest_published_issue(self):
  # The current collection may still await publication; the archive is the
  # authority for retained editions and their immutable source snapshots.
  for path in sorted((ROOT/'data/approved-issues').glob('????-??-??.json'),reverse=True):
   issue=json.loads(path.read_text())
   if issue.get('status')=='published':
    return issue
  self.fail('The archive must contain a published issue for presentation regressions.')

 def test_brief_redesign_preserves_all_published_copy_and_source_versions(self):
  issue=self.latest_published_issue()
  frozen=copy.deepcopy(issue)
  page=build_newsletter.render_issue(issue)
  rss=build_newsletter.rss_content(issue)
  self.assertIn('<details',page)
  self.assertNotIn('<details',rss)
  self.assertIn('THE ATTENTION BRIEF',page)
  self.assertNotIn('Attention Edit',page)
  self.assertNotIn('fonts.googleapis.com',page)
  texts=[issue[k] for k in ('headline','deck','letter','closer','editorial_note')]
  texts += [s['text'] for s in issue['signals']]
  texts += [issue['tension']['text'],issue['experiment']['text'],issue['experiment']['caution']]
  for text in texts:
   self.assertIn(' '.join(text.split()),VisibleText(page).text())
   self.assertIn(' '.join(text.split()),VisibleText(rss).text())
  for source in issue['sources']:
   self.assertIn(html.escape(source['title'],quote=True),page)
   for key in ('source_version','source_doi','related_journal_doi','review_scope','quality_note','notice','temporal_notice'):
    if source.get(key):
     self.assertIn(html.escape(source[key],quote=True),page)
     self.assertIn(html.escape(source[key],quote=True),rss)
  self.assertEqual(issue,frozen)

 def test_brief_brand_does_not_change_feed_identity_or_archived_snapshot(self):
  issue=self.latest_published_issue()
  issue['subject']='The Attention Edit · A preserved issue'
  frozen=copy.deepcopy(issue)
  feed=build_newsletter.json_feed([issue])
  self.assertEqual(feed['items'][0]['title'],'The Attention Brief · A preserved issue')
  self.assertEqual(feed['items'][0]['_observatory'],frozen)
  with tempfile.TemporaryDirectory() as directory, patch.object(build_newsletter,'ROOT',Path(directory)):
   build_rss([issue])
   channel=ET.parse(Path(directory)/'issue-feed.xml').find('channel')
   item=channel.find('item')
   self.assertEqual(item.findtext('title'),feed['items'][0]['title'])
   self.assertEqual(item.findtext('guid'),feed['items'][0]['id'])
   self.assertEqual(item.findtext('pubDate'),build_newsletter.rss_date(build_newsletter.published_on(issue['edition_date'])))
  self.assertEqual(issue,frozen)

 def test_long_copy_shows_a_complete_sentence_and_preserves_full_analysis(self):
  first='The estimate was 3.14 in this study.'
  text=first+' '+('The limits remain important and do not establish causation. '*6)
  rendered=build_newsletter.long_copy(text)
  self.assertIn(html.escape(first),rendered.split('<details>')[0])
  self.assertIn(html.escape(text),rendered.split('<details>')[1])
  self.assertNotIn('<details',build_newsletter.long_copy('A short sentence.'))

 def test_inline_versions_are_readable_and_shelf_preserves_distinct_notices(self):
  source={'id':'test','title':'Test source','source_url':'https://example.org/paper',
          'original_summary':True,'source_version':'arxiv_preprint_v1',
          'notice':'No historical snapshot is available.',
          'temporal_notice':'Current HTML was read after publication.'}
  issue={'sources':[source]}
  links=build_newsletter.source_links(issue,['test'])
  self.assertIn('arXiv preprint v1',links)
  self.assertNotIn('arxiv_preprint_v1',links)
  for disclosure in (True,False):
   shelf=build_newsletter.source_shelf(issue,disclosure)
   self.assertIn('arxiv_preprint_v1',shelf)
   self.assertIn(source['notice'],shelf)
   self.assertIn(source['temporal_notice'],shelf)
  source['temporal_notice']=source['notice']
  self.assertEqual(build_newsletter.source_shelf(issue).count(source['notice']),1)
  self.assertEqual(build_newsletter.readable_version('publisher_article'),'Publisher article')

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
   if name=="issue-feed.xml":
    self.assertTrue(items,"The published issue archive must have an edition")
  xsl=ET.parse(ROOT/"assets/feed.xsl").getroot()
  self.assertEqual(xsl.tag,"{http://www.w3.org/1999/XSL/Transform}stylesheet")
 def test_record_rss_uses_cleaned_digest_not_raw_method_checks(self):
  rss=ET.parse(ROOT/"feed.xml").getroot()
  items=rss.findall("./channel/item")
  # A quiet discovery week can yield zero or one qualified reading.
  # RSS validity and source attribution must not depend on a fixed count.
  self.assertTrue(all("#paper/" in item.findtext("link","") for item in items))
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

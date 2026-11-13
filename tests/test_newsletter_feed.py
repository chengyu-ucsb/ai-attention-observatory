"""RSS subscription regression tests for the approved editorial issue feed."""
from datetime import datetime
import copy
import html
from html.parser import HTMLParser
import json
import re
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

 def test_layered_reader_has_complete_no_script_content_and_valid_navigation(self):
  issue=self.latest_published_issue()
  page=build_newsletter.render_issue(issue)
  markup=page.split('<script>')[0]
  panels=re.findall(r'<section[^>]*id="([^"]+)"[^>]*data-edition-panel[^>]*>',markup)
  options=re.findall(r'<option value="([^"]+)">',markup)
  self.assertEqual(set(panels),set(options))
  self.assertEqual(len(panels),len(options))
  self.assertGreaterEqual(len(panels),4)
  # Hidden panels are a browser enhancement: all content survives script failure.
  for tag in re.findall(r'<section[^>]*data-edition-panel[^>]*>',markup):
   self.assertNotIn('hidden',tag)
  for i,section in enumerate(issue['signals'],1):
   panel=markup.split('id="signal-'+str(i)+'"',1)[1].split('</section>',1)[0]
   self.assertIn(' '.join(section['text'].split()),VisibleText(panel).text())
   self.assertIn('data-edition-target="signal-'+str(i)+'"',markup)
  self.assertIn('id="edition-read-all" aria-pressed="false"',markup)
  self.assertIn('data-edition-layer="opening"',markup)
  self.assertIn('data-edition-layer="methods"',markup)
  self.assertIn('data-edition-layer="sources"',markup)
  self.assertIn('AI-assisted summary. AI can make mistakes.',markup)
  self.assertNotIn('AI source-check, not human review',markup)

 def test_reading_map_uses_existing_labels_and_actual_source_counts(self):
  issue=self.latest_published_issue()
  page=build_newsletter.overview(issue)
  for i,section in enumerate(issue['signals'],1):
   card=page.split('data-edition-target="signal-'+str(i)+'"',1)[1].split('</a>',1)[0]
   self.assertIn(html.escape(section.get('short') or section['title'],quote=True),card)
   count=len(section['source_ids'])
   self.assertIn(str(count)+' source'+('' if count==1 else 's'),card)
  self.assertIn('Edition reading map',page)
  self.assertNotIn('effect size',page)

 def test_methods_and_dates_are_secondary_layers_without_losing_their_text(self):
  issue=self.latest_published_issue()
  page=build_newsletter.render_issue(issue)
  opening=page.split('<nav class="reader-map"',1)[0]
  self.assertNotIn(html.escape(issue['editorial_note'],quote=True),opening)
  methods=page.split('data-edition-layer="methods"',1)[1].split('</details>',1)[0]
  self.assertIn(' '.join(issue['editorial_note'].split()),VisibleText(methods).text())
  self.assertIn(build_newsletter.publication_scope(issue),html.unescape(methods))
  self.assertIn('data-edition-layer="history"',page)
  # RSS remains a complete linear reading, with no controls or modal script.
  rss=build_newsletter.rss_content(issue)
  self.assertNotIn('<script',rss)
  self.assertNotIn('data-edition-panel',rss)
  self.assertNotIn('data-edition-layer',rss)
  self.assertIn(' '.join(issue['editorial_note'].split()),VisibleText(rss).text())

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
   self.assertEqual(item.findtext('pubDate'),build_newsletter.rss_date(build_newsletter.publication_timestamp(issue)))
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
   key=link.rsplit('/',1)[-1].removesuffix('.html')
   archived=json.loads((ROOT/'data/approved-issues'/f'{key}.json').read_text())
   self.assertEqual(item.findtext("guid"),build_newsletter.feed_identity(archived))
   self.assertEqual(item.findtext("pubDate"),build_newsletter.rss_date(build_newsletter.publication_timestamp(archived)))
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


 def test_monday_identity_does_not_rewrite_release_clock_or_feed_id(self):
  issue=copy.deepcopy(self.latest_published_issue())
  issue.update(edition_date='2026-11-09', first_published_date='2026-11-13',
               feed_id=build_newsletter.BASE+'issues/2026-11-13.html',
               feed_published_at='2026-11-13T12:00:00+00:00')
  frozen=copy.deepcopy(issue)
  page=build_newsletter.render_issue(issue)
  self.assertIn('Week of Monday, November 9, 2026',page)
  self.assertIn('First published 2026-11-13',page)
  self.assertIn('rel="canonical" href="'+build_newsletter.BASE+'issues/2026-11-09.html"',page)
  item=build_newsletter.json_feed([issue])['items'][0]
  self.assertEqual(item['id'],issue['feed_id'])
  self.assertTrue(item['url'].endswith('/2026-11-09.html'))
  self.assertEqual(item['date_published'],'2026-11-13T12:00:00+00:00')
  with tempfile.TemporaryDirectory() as directory,patch.object(build_newsletter,'ROOT',Path(directory)):
   build_rss([issue]);rss=ET.parse(Path(directory)/'issue-feed.xml').find('./channel/item')
   self.assertEqual(rss.findtext('guid'),item['id'])
   self.assertEqual(rss.findtext('link'),item['url'])
   self.assertEqual(parsedate_to_datetime(rss.findtext('pubDate')).isoformat(),item['date_published'])
  self.assertEqual(issue,frozen)

 def test_merged_supplement_survives_html_and_feed_with_source_links(self):
  issue=copy.deepcopy(self.latest_published_issue());source=issue['sources'][0]
  issue['supplements']=[{'title':'A retained question','text':'This earlier perspective raises a question.',
                         'source_ids':[source['id']],
                         'citations':[{'text':'earlier perspective','source_id':source['id']}]}]
  for page in (build_newsletter.render_issue(issue),build_newsletter.rss_content(issue)):
   self.assertIn('A retained question',page)
   self.assertIn('This',VisibleText(page).text())
   self.assertIn('earlier perspective raises a question.',VisibleText(page).text())
   self.assertIn('class="inline-citation"',page)

 def test_legacy_links_redirect_and_original_versions_remain_readable(self):
  original=copy.deepcopy(self.latest_published_issue());original['edition_date']='2026-11-13'
  canonical=copy.deepcopy(original);canonical['edition_date']='2026-11-09'
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);data=root/'data';data.mkdir();revisions=data/'edition-revisions';revisions.mkdir()
   folder=root/'issues';folder.mkdir()
   snapshot=json.dumps(original).encode()
   (revisions/'2026-11-13.json').write_bytes(snapshot)
   lineage={'aliases':{'2026-11-13':'2026-11-09'},'revisions':{'2026-11-13':{'canonical_date':'2026-11-09','sha256':build_newsletter.sha256(snapshot).hexdigest(),'note':'Consolidated Monday edition.'}}}
   (data/'edition-lineage.json').write_text(json.dumps(lineage))
   with patch.object(build_newsletter,'DATA',data):build_newsletter.build_history_pages(folder,[canonical])
   alias=(folder/'2026-11-13.html').read_text();history=(folder/'history/2026-11-13.html').read_text()
   self.assertIn('0; url=2026-11-09.html',alias)
   self.assertIn('history/2026-11-13.html',alias)
   self.assertIn('Original published version · 2026-11-13',history)
   self.assertIn('href="../../assets/typography.css"',history)
   self.assertIn('name="robots" content="noindex"',history)
   self.assertIn('rel="canonical" href="'+build_newsletter.BASE+'issues/2026-11-09.html"',history)
   self.assertEqual(json.loads((revisions/'2026-11-13.json').read_text()),original)
   # Even whitespace changes must not silently replace the frozen original.
   (revisions/'2026-11-13.json').write_bytes(snapshot+b'\n')
   with patch.object(build_newsletter,'DATA',data),self.assertRaisesRegex(ValueError,'snapshot hash mismatch'):
    build_newsletter.build_history_pages(folder,[canonical])

if __name__=="__main__":unittest.main()

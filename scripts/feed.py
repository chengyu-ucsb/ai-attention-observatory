"""Publish readable, standards-compliant reading RSS from the public library digest.

The newsletter issue feed (issue-feed.xml) is different: it includes only
published cross-source essays. Reading RSS contains short source-linked notes.
"""
from __future__ import annotations
from reading_headlines import reader_headline, genre_label
import datetime
import json
import pathlib
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from original_readings import public_record
from collection_window import previous_week, weekly_eligible, window_metadata

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
BASE="https://chengyu-ucsb.github.io/ai-attention-observatory/"
URL=BASE+"feed.xml"
ATOM="http://www.w3.org/2005/Atom"
ET.register_namespace("atom",ATOM)

def rss_date(value):
 try:
  dt=datetime.datetime.fromisoformat(value[:10]).replace(hour=12,tzinfo=datetime.timezone.utc)
 except (ValueError,TypeError,AttributeError):
  dt=datetime.datetime.now(datetime.timezone.utc)
 return format_datetime(dt,usegmt=True)

def build():
 if not (DATA/"public-weekly.json").exists():
  from build_public import build as project
  project()
 weekly=json.loads((DATA/"public-weekly.json").read_text(encoding="utf-8"))
 date=(weekly.get("run") or {}).get("date")
 bounds=previous_week(date) if date else None
 if bounds:
  expected=window_metadata(date)
  supplied=(weekly.get("run") or {}).get("publication_window") or expected
  if any(supplied.get(key)!=expected[key] for key in ("from","to","timezone")):
   raise ValueError("RSS publication window does not match previous completed UTC week")
 root=ET.Element("rss",{"version":"2.0"})
 channel=ET.SubElement(root,"channel")
 fields={
  "title":"Latest readings | AI & Attention Observatory",
  "link":BASE+"#library",
  "description":"Research, reporting, and opinion about AI and human attention.",
  "language":"en-us",
  "ttl":"60"
 }
 for field,value in fields.items():
  ET.SubElement(channel,field).text=value
 ET.SubElement(channel,"{"+ATOM+"}link",{"href":URL,"rel":"self","type":"application/rss+xml"})
 entries=0
 for x in (weekly.get("items") or [])[:50]:
  x=public_record(x, require_current=True)
  if bounds and not weekly_eligible(x,*bounds):continue
  read=x.get("reading") or {}
  if read.get("level")=="citation_only":continue
  digest=read.get("digest") or {}
  idea=(digest.get("idea") or "").strip()
  if not idea:continue
  label=genre_label(x)
  attribution=read.get("attributed_to") or x.get("venue")
  byline=" · ".join(part for part in (label,attribution) if part)
  # A bibliographic title alone is not a synopsis. Keep that item's
  # attribution instead of recycling the original title as its whole lead.
  description=byline if idea.casefold()==str(x.get("title") or "").casefold() else byline+". "+idea
  stable=x.get("doi") or x.get("url") or x.get("title")
  if not stable:continue
  permalink=BASE+"#paper/"+urllib.parse.quote(str(stable),safe="")
  item=ET.SubElement(channel,"item")
  for field,value in [
   ("title",reader_headline(x)),
   ("link",permalink),
   ("description",description),
   ("pubDate",rss_date(x.get("published") or (weekly.get("run") or {}).get("date"))),
   ("guid",permalink)
  ]:
   el=ET.SubElement(item,field)
   if field=="guid":el.attrib["isPermaLink"]="true"
   el.text=value
  if read.get("original_summary"):
   ET.SubElement(item,"source",{"url":read["source_url"]}).text=x.get("venue") or "Original source"
  ET.SubElement(item,"category").text=label
  ET.SubElement(item,"category").text=x.get("lane") or "AI and attention"
  entries+=1
 ET.SubElement(channel,"lastBuildDate").text=rss_date((weekly.get("run") or {}).get("date"))
 ET.indent(root)
 xml=ET.tostring(root,encoding="utf-8",xml_declaration=True)
 xml=xml.replace(b"?>",b"?>\n<?xml-stylesheet type=\"text/xsl\" href=\"assets/feed.xsl\"?>",1)
 ET.fromstring(xml)
 (ROOT/"feed.xml").write_bytes(xml)
 print(json.dumps({"feed":"feed.xml","items":entries}))
 return entries

if __name__=="__main__":build()


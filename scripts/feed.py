"""Publish readable, standards-compliant research RSS from the public library digest.

The newsletter issue feed (issue-feed.xml) is different: it includes only
published cross-source essays. Research RSS contains short source-linked notes.
"""
from __future__ import annotations
import datetime
import json
import pathlib
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import format_datetime

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
 root=ET.Element("rss",{"version":"2.0"})
 channel=ET.SubElement(root,"channel")
 fields={
  "title":"New research | AI & Attention Observatory",
  "link":BASE+"#library",
  "description":"New studies and ideas about AI, cognition, and attention. Research notes link to the original evidence.",
  "language":"en-us",
  "ttl":"60"
 }
 for field,value in fields.items():
  ET.SubElement(channel,field).text=value
 ET.SubElement(channel,"{"+ATOM+"}link",{"href":URL,"rel":"self","type":"application/rss+xml"})
 entries=0
 for x in (weekly.get("items") or [])[:50]:
  read=x.get("reading") or {}
  if read.get("level")=="citation_only":continue
  digest=read.get("digest") or {}
  idea=(digest.get("idea") or "").strip()
  if not idea:continue
  # Do not use full Results extracts as article descriptions.
  text=idea
  explain=(digest.get("explain") or "").strip()
  if explain and explain.lower() not in text.lower():
   text+=" "+explain
  kind=x.get("kind") or "scholarly"
  label="Conceptual framework" if x.get("research_type")=="conceptual_framework" else "Research finding" if digest.get("finding") else ("Research question" if kind=="scholarly" else "Perspective")
  stable=x.get("doi") or x.get("url") or x.get("title")
  if not stable:continue
  permalink=BASE+"#paper/"+urllib.parse.quote(str(stable),safe="")
  item=ET.SubElement(channel,"item")
  for field,value in [
   ("title",idea[:165]),
   ("link",permalink),
   ("description",label+": "+text[:490]),
   ("pubDate",rss_date(x.get("published") or (weekly.get("run") or {}).get("date"))),
   ("guid",permalink)
  ]:
   el=ET.SubElement(item,field)
   if field=="guid":el.attrib["isPermaLink"]="true"
   el.text=value
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

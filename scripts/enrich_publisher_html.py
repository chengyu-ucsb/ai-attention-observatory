"""Low-rate full-text HTML retrieval for explicitly CC-BY publisher articles.

Only official Frontiers/MDPI article pages. No proxy, bypass, browser automation
or copying of complete HTML/PDF. HTML is discarded after extracting short
section passages into the private evidence index. Sites that deny access are
left unresolved; do not retry aggressively.
"""
from __future__ import annotations
from enrich_wiley_html import run as inspect_wiley_html
from verified_full_article_notes import run as apply_verified_readings
import datetime as dt
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
LIB=ROOT/"data/library.json"
JOURNALS={"fpsyg":"psychology","feduc":"education","frai":"artificial-intelligence",
          "fcomm":"communication","fpubh":"public-health","fneur":"neuroscience"}
DOI=re.compile(r"^10\.(3389|3390)/[a-z0-9._/-]+$",re.I)
HEAD=re.compile(r"^\s*(?:\d+(?:\.\d+)*[.\s]*)?(materials and methods|methodology|methods?|results?(?: and discussion)?|findings|discussion|limitations|conclusions?|references|bibliography)\s*[:.]?\s*$",re.I)
ALLOW_HOSTS={"www.frontiersin.org","frontiersin.org","www.mdpi.com","mdpi.com"}
AGENT="AIAttentionObservatory/4.1 (academic indexing; fangcu@ucmail.uc.edu)"
def clean(t):return " ".join(str(t or "").split())
def section_name(raw):
 m=HEAD.fullmatch(clean(raw))
 if not m:return ""
 title=m.group(1).lower()
 if title.startswith(("reference","bibliography")):return "stop"
 if title.startswith(("material","method")):return "methods"
 if title.startswith(("result","finding")):return "results"
 if title.startswith("limitation"):return "limitations"
 return "discussion"
class ArticleHTML(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True)
  self.blocked=0;self.heading=None;self.paragraph=None;self.active="";self.secs={}
 def handle_starttag(self,tag,attrs):
  if tag in ("script","style","nav","footer","aside"):self.blocked+=1
  if self.blocked:return
  if tag in ("h2","h3","h4") and self.heading is None:self.heading=[]
  if tag=="p" and self.paragraph is None:self.paragraph=[]
 def handle_data(self,data):
  if self.blocked:return
  if self.heading is not None:self.heading.append(data)
  if self.paragraph is not None:self.paragraph.append(data)
 def handle_endtag(self,tag):
  if tag in ("script","style","nav","footer","aside"):
   if self.blocked:self.blocked-=1
   return
  if self.blocked:return
  if tag in ("h2","h3","h4") and self.heading is not None:
   key=section_name(" ".join(self.heading));self.heading=None
   if key=="stop":self.active="stop"
   elif key:self.active=key
  if tag=="p" and self.paragraph is not None:
   value=clean(" ".join(self.paragraph));self.paragraph=None
   if self.active and self.active!="stop" and len(value)>=45:
    joined=self.secs.get(self.active,"")
    if len(joined)<6700:self.secs[self.active]=(joined+" "+value).strip()[:6700]
def url_for(doi):
 if not DOI.fullmatch(doi or ""):return ""
 if doi.lower().startswith("10.3390/"):return "https://doi.org/"+doi
 parts=doi.lower().split("/")
 code=parts[1].split(".")[0]
 return "https://www.frontiersin.org/journals/"+JOURNALS.get(code,code)+"/articles/"+doi+"/full"
def fetch_article(url):
 req=urllib.request.Request(url,headers={"User-Agent":AGENT,"Accept":"text/html"})
 with urllib.request.urlopen(req,timeout=22) as resp:
  hostname=(urllib.parse.urlparse(resp.geturl()).hostname or "").lower()
  if hostname not in ALLOW_HOSTS:raise ValueError("Redirect to an unapproved publisher host")
  payload=resp.read(6_000_001)
  if len(payload)>6_000_000:raise ValueError("Publisher page exceeds size limit")
  return payload.decode("utf-8","replace"),resp.geturl()
def licensed(page):
 text=page.lower()
 return any(token in text for token in (
  "creativecommons.org/licenses/by/4.0",
  "creativecommons.org/licenses/by/3.0",
  "creative commons attribution license (cc by)",
  "licensed under the creative commons attribution")) and not any(token in text for token in (
  "creativecommons.org/licenses/by-nc/","creativecommons.org/licenses/by-nd/"))
def parse(html,doi):
 if doi.lower() not in html.lower():return {}, "doi_not_found_on_page"
 if not licensed(html):return {}, "license_not_verified"
 parser=ArticleHTML()
 parser.feed(html)
 secs=parser.secs
 # Don't index navigation headings or a truncated abstract as a full paper.
 if not (secs.get("results") or secs.get("discussion")):return {}, "missing_sections"
 if max(len(s) for s in secs.values())<100:return {}, "insufficient_article_text"
 return secs,None
def eligible(record,date):
 doi=(record.get("doi") or "").lower()
 if record.get("kind")!="scholarly" or record.get("analysis") or not url_for(doi):return False
 old=record.get("publisher_html_attempt") or {}
 if old.get("version")!=1:return True
 try:return dt.date.fromisoformat((old.get("next_at") or "")[:10])<=date
 except ValueError:return True
def mark(record,status,days,date):
 attempt=record.setdefault("publisher_html_attempt",{})
 attempt.update(version=1,status=status,last_at=date.isoformat(),
                next_at=(date+dt.timedelta(days=days)).isoformat(),attempts=attempt.get("attempts",0)+1)
def run():
 records=json.loads(LIB.read_text(encoding="utf-8"))
 date=dt.date.today();limit=max(1,min(int(os.getenv("PUBLISHER_HTML_LIMIT","28")),70))
 candidates=[r for r in records if eligible(r,date)]
 candidates.sort(key=lambda r:(0 if (r.get("doi") or "").startswith("10.3389/") else 1,
                                 (r.get("publisher_html_attempt") or {}).get("attempts",0),
                                 r.get("published") or ""))
 stats={"attempted":0,"new_fulltexts":0,"license_unverified":0,"sections_missing":0,"access_denied":0,"temporary_errors":0}
 for record in candidates[:limit]:
  doi=record["doi"].lower()
  try:
   html,url=fetch_article(url_for(doi));stats["attempted"]+=1
   sections,error=parse(html,doi)
   if error:
    mark(record,error,30 if error=="license_not_verified" else 14,date)
    if error=="license_not_verified":stats["license_unverified"]+=1
    else:stats["sections_missing"]+=1
    continue
   record["analysis"]={
    "provenance":"Original publisher openly licensed HTML (automated section reading)",
    "license":"cc-by (source webpage verified)","license_url":url,
    "fulltext_url":url,"methods":sections.get("methods",""),
    "results":sections.get("results",""),"discussion":sections.get("discussion",""),
    "limitations":sections.get("limitations",""),"figures":[],
    "key_idea":(sections.get("results") or sections.get("discussion") or "")[:280],
    "extraction_date":date.isoformat(),"extraction_version":3,
    "sections_available":list(sections)}
   mark(record,"full_text",365,date);stats["new_fulltexts"]+=1
  except urllib.error.HTTPError as ex:
   mark(record,"publisher_access_denied" if ex.code in (401,403,404,429) else "temporary_error",
        45 if ex.code in (401,403,404,429) else 3,date)
   if ex.code in (401,403,404,429):stats["access_denied"]+=1
   else:stats["temporary_errors"]+=1
  except (urllib.error.URLError,TimeoutError,ValueError) as ex:
   mark(record,"temporary_error",3,date);stats["temporary_errors"]+=1
  time.sleep(.7)
 LIB.write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 # The public Wiley site can be READ independently of the reuse terms.
 # Only verified original paraphrases become public research readings.
 stats["wiley_html"]=inspect_wiley_html(path=LIB)
 stats["publisher_source_checked_notes"]=apply_verified_readings(path=LIB)
 updated=json.loads(LIB.read_text(encoding="utf-8"))
 stats["still_without_fulltext"]=sum(r.get("kind")=="scholarly" and not r.get("analysis") for r in updated)
 print(json.dumps(stats))
 return stats
if __name__=="__main__":run()

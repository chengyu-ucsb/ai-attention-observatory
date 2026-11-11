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
from publisher_sections import ArticleHTML, clean, section_name
from html.parser import HTMLParser
import hashlib
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
ALLOW_HOSTS={"www.frontiersin.org","frontiersin.org","www.mdpi.com","mdpi.com"}
AGENT="AIAttentionObservatory/4.1 (academic indexing; fangcu@ucmail.uc.edu)"
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
class SourceMetadata(HTMLParser):
 """Only explicit primary DOI metadata and concrete license URLs qualify."""
 def __init__(self):
  super().__init__(convert_charrefs=True)
  self.dois=set();self.license_urls=set()
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=="meta" and attrs.get("name","").lower() in ("citation_doi","dc.identifier"):
   value=clean(attrs.get("content","")).lower()
   value=re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)","",value)
   if attrs.get("name","").lower()=="citation_doi" or value.startswith("10."):
    self.dois.add(value)
  if tag in ("a","link"):
   href=attrs.get("href","").strip()
   parsed=urllib.parse.urlparse(href)
   if (parsed.hostname or "").lower() in ("creativecommons.org","www.creativecommons.org"):
    if parsed.path.lower().startswith("/licenses/"):
     self.license_urls.add(href)

def source_metadata(page):
 metadata=SourceMetadata();metadata.feed(page);return metadata

def licensed(page):
 return verified_license(source_metadata(page))

def verified_license(metadata):
 # A concrete CC-BY link is required. Reject mixed, restrictive, unknown,
 # or qualified license URLs instead of interpreting broad Attribution prose.
 if not metadata.license_urls:return False
 for url in metadata.license_urls:
  parsed=urllib.parse.urlparse(url)
  if (parsed.scheme not in ("https","http") or parsed.params or parsed.query or parsed.fragment
      or not re.fullmatch(r"/licenses/by/(?:3\.0|4\.0)/?",parsed.path)):
   return False
 return True
def parse(html,doi, *, with_coverage=False):
 metadata=source_metadata(html)
 if metadata.dois!={doi.lower()}:return {}, "primary_doi_not_verified"
 if not verified_license(metadata):return {}, "license_not_verified"
 parser=ArticleHTML()
 parser.feed(html)
 secs=parser.secs
 # Don't index navigation headings or a truncated abstract as a full paper.
 if not (secs.get("results") or secs.get("discussion")):return {}, "missing_sections"
 if max(len(s) for s in secs.values())<100:return {}, "insufficient_article_text"
 return ((secs,parser.coverage) if with_coverage else secs),None
EXTRACTION_VERSION=4
PUBLISHER_PROVENANCE="Original publisher openly licensed HTML (automated section reading)"
def needs_section_repair(record):
 analysis=record.get("analysis") or {}
 return (analysis.get("provenance")==PUBLISHER_PROVENANCE
         and analysis.get("extraction_version")==3 and not analysis.get("results"))
def build_analysis(sections,coverage,url,date):
 return {
    "provenance":"Original publisher openly licensed HTML (automated section reading)",
    "license":"cc-by (source webpage verified)","license_url":url,
    "fulltext_url":url,"methods":sections.get("methods",""),
    "results":sections.get("results",""),"discussion":sections.get("discussion",""),
    "limitations":sections.get("limitations",""),"figures":[],
    "key_idea":(sections.get("results") or sections.get("discussion") or "")[:280],
    "extraction_date":date.isoformat(),"extraction_version":EXTRACTION_VERSION,
    "extraction_coverage":coverage,
    "sections_available":list(sections)}

def reparse_retained_html(record,html,date, *, source_verification):
 """Propose a repair from previously authorized retained HTML, without I/O.

 Caller supplies independently verified exact identity, content hash and
 CC-BY reuse permission in source_verification. Does not
 mutate the record, reset attempts, fetch, or bypass acquisition controls.
 """
 verification=source_verification or {}
 if (verification.get("doi") != record.get("doi")
     or not record.get("title") or verification.get("title") != record.get("title")
     or verification.get("license") != "cc-by"
     or verification.get("sha256") != hashlib.sha256(html.encode("utf-8")).hexdigest()):
  return None,"source_verification_required"
 previous=record.get("analysis") or {}
 if not needs_section_repair(record):return None,"not_repair_candidate"
 parsed,error=parse(html,record.get("doi") or "",with_coverage=True)
 if error:return None,error
 sections,coverage=parsed
 if not sections.get("results") or any(previous.get(key) and not sections.get(key)
     for key in ("methods","discussion","limitations")):
  return None,"incomplete_reparse"
 analysis=build_analysis(sections,coverage,previous.get("fulltext_url",""),date)
 analysis["extraction_coverage"]["source_representation"]={
  "format":"retained_publisher_html", "sha256":verification["sha256"],
  "checked_at":date.isoformat(), "url":previous.get("fulltext_url","")}
 return analysis,None

def eligible(record,date):
 doi=(record.get("doi") or "").lower()
 if record.get("kind")!="scholarly" or not url_for(doi):return False
 old=record.get("publisher_html_attempt") or {}
 # Existing analyses are deliberately NOT automatically refetched. The source
 # acquisition controller owns provider/host/rights cooldowns; migration must
 # be scheduled there, or performed on already retained authorized HTML.
 if record.get("analysis"):return False
 try:return dt.date.fromisoformat((old.get("next_at") or "")[:10])<=date
 except ValueError:return not old.get("status")
def mark(record,status,days,date):
 attempt=record.setdefault("publisher_html_attempt",{})
 attempt.update(version=2,status=status,last_at=date.isoformat(),
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
   parsed,error=parse(html,doi,with_coverage=True)
   if error:
    mark(record,error,30 if error=="license_not_verified" else 14,date)
    if error=="license_not_verified":stats["license_unverified"]+=1
    else:stats["sections_missing"]+=1
    continue
   sections,coverage=parsed
   previous=record.get("analysis") or {}
   if previous and (not sections.get("results") or any(
       previous.get(key) and not sections.get(key)
       for key in ("methods","results","discussion","limitations"))):
    mark(record,"incomplete_reparse",14,date)
    stats["sections_missing"]+=1
    continue
   record["analysis"]=build_analysis(sections,coverage,url,date)
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

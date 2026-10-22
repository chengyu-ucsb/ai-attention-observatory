"""Resumable, budget-aware, licensed full-text acquisition for the observatory.

Scheduled independently of weekly discovery. Only a small pending batch is tried at
each invocation. 429 errors pause the shared queue until budget replenishment.
Unlicensed/unavailable sources are retained for later reevaluation, NOT republished.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
LIB=DATA/"library.json"
STATE=DATA/"fulltext-backfill-state.json"
UTC=dt.timezone.utc
ALLOW={"cc-by","cc-by-sa","cc0","public-domain"}
FOCUS=re.compile(r"attention|focus|cognit|thinking|think|distract|interrupt|offload|memory|metacognit|task.switch|ai literacy",re.I)
HEADINGS={
 "methods":("method","material","procedure","design","data collection","analysis approach","participants"),
 "results":("results","findings"),
 "discussion":("discussion","conclusion"),
 "limitations":("limitation","strengths and limitations"),
}

def now():return dt.datetime.now(UTC)
def iso(value):return value.astimezone(UTC).isoformat(timespec="seconds")
def parse(value):
 try:return dt.datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(UTC)
 except (ValueError,TypeError,AttributeError):return dt.datetime.min.replace(tzinfo=UTC)
def local(tag):return tag.split("}")[-1].lower()
def content(el):return " ".join(" ".join(el.itertext()).split())
def extract(root):
 sections={}
 for div in root.iter():
  if local(div.tag)!="div":continue
  head=next((content(e).lower() for e in div if local(e.tag)=="head"),"")
  key=next((k for k,words in HEADINGS.items() if any(w in head for w in words)),None)
  if not key or key in sections:continue
  parts=[content(el) for el in div.iter() if local(el.tag)=="p"]
  value=" ".join(x for x in parts if len(x)>40)
  if value:sections[key]=value[:4500].rsplit(" ",1)[0] if len(value)>4500 else value
 return sections
def get(url,key):
 u=url+("&" if "?" in url else "?")+urllib.parse.urlencode({"api_key":key})
 req=urllib.request.Request(u,headers={"User-Agent":"AI-Attention-Observatory/3.0 (fangcu@ucmail.uc.edu)","Accept":"application/xml,application/json","Accept-Encoding":"identity"})
 with urllib.request.urlopen(req,timeout=24) as response:
  return response.read(5_000_000),response.headers
def read_json(path,default):
 try:return json.loads(path.read_text())
 except (ValueError,OSError):return default
def next_retry(days):return iso(now()+dt.timedelta(days=days))
def pause_time(error):
 # OpenAlex credits reset at midnight UTC. The response reports seconds to reset.
 headers=getattr(error,"headers",{}) or {}
 value=headers.get("X-RateLimit-Reset") or headers.get("Retry-After")
 try:seconds=int(value)
 except (ValueError,TypeError):seconds=None
 if seconds is None or seconds>86400 or seconds<0:
  tomorrow=now().date()+dt.timedelta(days=1)
  target=dt.datetime.combine(tomorrow,dt.time(1,0),tzinfo=UTC)
 else:
  # At least one hour: the next scheduled run rechecks rather than spinning.
  target=now()+dt.timedelta(seconds=max(seconds+120,3600))
 return iso(target)
def priority(r):
 title=r.get("title") or ""
 return (-int(bool(FOCUS.search(title))),-int(r.get("relation")!="Adjacent digital-attention evidence"),-int(bool(r.get("open_access_url"))),
         r.get("fulltext_attempt",{}).get("attempts",0),r.get("published") or "")
def eligible(r,t):
 if r.get("kind")!="scholarly" or not r.get("doi") or r.get("analysis"):return False
 attempt=r.get("fulltext_attempt") or {}
 # Make one targeted pass after changes in retrieval logic; then honor backoff.
 if attempt.get("pipeline_version")!=2:return True
 return parse(attempt.get("next_at"))<=t
def summarize(records,info):
 t=now()
 scholarly=[r for r in records if r.get("kind")=="scholarly"]
 remaining=[r for r in scholarly if not r.get("analysis")]
 ready=[r for r in remaining if eligible(r,t)]
 postponed=[r for r in remaining if r.get("doi") and not eligible(r,t)]
 reasons={}
 for r in postponed:
  status=(r.get("fulltext_attempt") or {}).get("status","other")
  reasons[status]=reasons.get(status,0)+1
 return {"last_run":iso(t),"total_scholarly":len(scholarly),"full_text_extracted":sum(bool(r.get("analysis")) for r in scholarly),
         "ready_for_attempt":len(ready),"retry_scheduled":len(postponed),
         "without_doi":sum(not r.get("doi") for r in remaining),"deferred_by_reason":reasons,**info}
def run():
 DATA.mkdir(exist_ok=True)
 records=read_json(LIB,[])
 state=read_json(STATE,{})
 key=os.getenv("OPENALEX_API_KEY","").strip()
 info={"attempted":0,"extracted_this_run":0,"quota_pause_until":state.get("quota_pause_until"),"status":"idle"}
 if not key:
  info["status"]="missing_api_key"
 elif parse(state.get("quota_pause_until"))>now():
  info["status"]="waiting_for_budget"
 else:
  state["quota_pause_until"]=None
  info["quota_pause_until"]=None
  candidates=sorted((r for r in records if eligible(r,now())),key=priority)
  max_attempts=max(1,min(int(os.getenv("OPENALEX_FULLTEXT_LIMIT","24")),100))
  content_limit=max(1,min(int(os.getenv("OPENALEX_CONTENT_LIMIT","8")),25))
  content_calls=0
  for r in candidates[:max_attempts]:
   if content_calls>=content_limit:break
   info["attempted"]+=1
   entry=r.get("fulltext_attempt") or {}
   entry["attempts"]=entry.get("attempts",0)+1
   entry["last_at"]=iso(now())
   entry["pipeline_version"]=2
   r["fulltext_attempt"]=entry
   doi=urllib.parse.quote("https://doi.org/"+r["doi"],safe=":")
   try:
    payload,_=get("https://api.openalex.org/works/"+doi,key)
    work=json.loads(payload)
    if not isinstance(work,dict) or not work.get("id"):raise ValueError("OpenAlex work lookup returned no ID")
    locations=[work.get("best_oa_location") or {}]+(work.get("locations") or [])
    loc=next((p for p in locations if (p.get("license") or "").lower() in ALLOW),None)
    preferred=work.get("best_oa_location") or {}
    href=preferred.get("landing_page_url") or preferred.get("pdf_url")
    if href and href.startswith("https://"):r["open_access_url"]=href
    if not loc:
     entry.update(status="waiting_for_license",next_at=next_retry(14))
     continue
    url=(work.get("content_urls") or {}).get("grobid_xml") or ""
    if not url.startswith("https://content.openalex.org/works/"):
     entry.update(status="waiting_for_machine_text",next_at=next_retry(7))
     continue
    content_calls+=1
    xml,_=get(url,key)
    root=ET.fromstring(xml)
    secs=extract(root)
    if not (secs.get("results") or secs.get("discussion")):
     entry.update(status="missing_sections",next_at=next_retry(14))
     continue
    lic_url=loc.get("landing_page_url") or loc.get("pdf_url") or href or work.get("doi") or ""
    r["analysis"]={
      "provenance":"OpenAlex OA GROBID XML (automatic parsing; verify source)",
      "license":(loc.get("license") or "").lower(),
      "license_url":loc.get("license_id") or "",
      "methods":secs.get("methods",""),"results":secs.get("results",""),
      "discussion":secs.get("discussion",""),"limitations":secs.get("limitations",""),
      "figures":[],"fulltext_url":lic_url,
      "key_idea":(secs.get("results") or secs.get("discussion") or "")[:280],
      "extraction_date":now().date().isoformat()}
    r["oa_grobid_checked"]=now().date().isoformat()
    entry.update(status="full_text",next_at=None)
    info["extracted_this_run"]+=1
   except urllib.error.HTTPError as exc:
    if exc.code==429:
     until=pause_time(exc)
     state["quota_pause_until"]=until
     info.update(quota_pause_until=until,status="waiting_for_budget")
     # Retry the same paper after the quota reset rather than recording a failure.
     entry.update(status="budget_retry",next_at=until)
     break
    if exc.code in (400,403,404):
     entry.update(status="source_unavailable",next_at=next_retry(21))
    else:entry.update(status="transient_error",next_at=next_retry(1))
   except (ValueError,ET.ParseError,urllib.error.URLError,TimeoutError) as exc:
    entry.update(status="transient_error",next_at=next_retry(1))
   time.sleep(.20)
  else:
   if candidates:info["status"]="batch_processed"
   else:info["status"]="no_ready_sources"
  if info["status"]=="idle":info["status"]="batch_processed"
 # Persist after every run, including quota pause, to make subsequent Actions resumable.
 LIB.write_text(json.dumps(records,indent=2,ensure_ascii=False)+"\n")
 public=summarize(records,info)
 STATE.write_text(json.dumps(public,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps(public,indent=2,ensure_ascii=False))
 return public

if __name__=="__main__":run()

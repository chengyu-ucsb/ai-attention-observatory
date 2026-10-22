"""Independent PMC identifier and licensed full-text recovery.

Europe PMC's search index misses some matching DOI records and the OpenAlex
content cache is separate from PMC. This fallback resolves DOIs in one batch
against NCBI's official ID converter, then uses *only the sanctioned PMC
OAI-PMH API* to retrieve articles with reusable JATS full text.

The public site receives parsed section snippets and source URLs, not an
unlicensed copy of a paper. Failed lookups and rights restrictions are tracked
and retried on a longer schedule; one missing source never stops the queue.
"""
from __future__ import annotations
import datetime as dt
import gzip
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from enrich import extract_sections, permitted

ROOT=pathlib.Path(__file__).resolve().parents[1]
LIB=ROOT/"data/library.json"
CONVERTER="https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
OAI="https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"
USER_AGENT="AIAttentionObservatory/4.0 (research indexing; fangcu@ucmail.uc.edu)"
ID=re.compile(r"PMC([0-9]+)$")
UTC=dt.timezone.utc

def today():return dt.datetime.now(UTC)
def parse_date(value):
 try:return dt.date.fromisoformat((value or "")[:10])
 except (ValueError,TypeError):return dt.date.min
def clean(value):return " ".join(str(value or "").split())
def local(tag):return tag.rsplit("}",1)[-1]
def fetch(url):
 req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/xml,application/json","Accept-Encoding":"gzip, deflate"})
 with urllib.request.urlopen(req,timeout=28) as response:
  raw=response.read(9_000_000)
  if (response.headers.get("Content-Encoding") or "").lower()=="gzip" or raw[:2]==b"\x1f\x8b":
   raw=gzip.decompress(raw)
  return raw
def batches(rows,n):
 for i in range(0,len(rows),n):yield rows[i:i+n]
def resolve_ids(dois):
 """Convert one batch of DOIs to PMCIDs; never infer an ID from paper title."""
 resolved={}
 for batch in batches(dois,100):
  args={"ids":",".join(batch),"idtype":"doi","format":"json","tool":"AIAttentionObservatory","email":"fangcu@ucmail.uc.edu"}
  response=json.loads(fetch(CONVERTER+"?"+urllib.parse.urlencode(args)))
  for rec in response.get("records") or []:
   pmcid=rec.get("pmcid") or ""
   doi=(rec.get("doi") or rec.get("requested-id") or "").lower()
   if ID.fullmatch(pmcid) and doi in batch and not rec.get("errmsg"):resolved[doi]=pmcid
  time.sleep(.36)
 return resolved
def jats_and_rights(xml):
 """Select the actual article (not OAI envelope) and normalize JATS namespaces."""
 root=ET.fromstring(xml)
 if any(local(el.tag)=="error" for el in root.iter()):
  return None,"oai_no_reusable_record"
 article=next((el for el in root.iter() if local(el.tag)=="article"),None)
 if article is None:return None,"missing_article_xml"
 for el in article.iter():el.tag=local(el.tag)
 licenses=[]
 for el in article.findall(".//license"):
  words=clean(" ".join(el.itertext())).lower()
  refs=" ".join(str(v) for k,v in el.attrib.items() if local(k) in ("href","license-type")).lower()
  # Link-form licenses are common in PMC JATS. Do not assume *all* OA = CC-BY.
  licenses.append(words+" "+refs)
 if not permitted(licenses):return None,"reuse_license_not_verified"
 sections=extract_sections(article)
 if not (sections.get("results") or sections.get("discussion")):
  return None,"missing_results_discussion"
 return {"sections":sections,"license":licenses[0][:190]},None
def eligible(record,date):
 if record.get("kind")!="scholarly" or not record.get("doi") or record.get("analysis"):return False
 check=record.get("pmc_oai_attempt") or {}
 if check.get("version")!=1:return True
 return parse_date(check.get("next_at"))<=date
def priority(record):
 title=record.get("title") or ""
 return (-int(bool(re.search(r"attention|cognit|thinking|offload|critical|focus",title,re.I))),
         -int("pmc" in str(record.get("open_access_url") or "").lower()),
         (record.get("pmc_oai_attempt") or {}).get("attempts",0),
         record.get("published") or "")
def status(record,status,retry_days,at):
 info=record.setdefault("pmc_oai_attempt",{})
 info.update(version=1,status=status,last_at=at.isoformat(),next_at=(at+dt.timedelta(days=retry_days)).isoformat(),attempts=info.get("attempts",0)+1)
def run():
 rows=json.loads(LIB.read_text(encoding="utf-8"))
 limit=max(1,min(int(os.getenv("PMC_OAI_LIMIT","32")),90))
 article_limit=max(1,min(int(os.getenv("PMC_OAI_XML_LIMIT","16")),60))
 date=today().date()
 candidates=sorted((r for r in rows if eligible(r,date)),key=priority)[:limit]
 known={r["doi"].lower():r.get("pmcid") for r in candidates if ID.fullmatch(r.get("pmcid") or "")}
 unknown=[r["doi"].lower() for r in candidates if r["doi"].lower() not in known]
 stats={"candidates":len(candidates),"resolved_pmcids":0,"oai_checked":0,"new_fulltexts":0,"no_pmc_record":0,
        "rights_restricted":0,"missing_source_sections":0,"errors":0}
 if unknown:
  try:known.update(resolve_ids(unknown))
  except (urllib.error.URLError,TimeoutError,ValueError) as err:
   stats["id_converter_error"]=str(err)[:130]
   # Preserve the backlog and retry next run rather than recording false misses.
   print(json.dumps(stats));return stats
 for r in candidates:
  if stats["oai_checked"]>=article_limit:break
  doi=r["doi"].lower()
  pmcid=known.get(doi)
  if not pmcid:
   status(r,"no_pmc_record",28,date)
   stats["no_pmc_record"]+=1
   continue
  r["pmcid"]=pmcid
  stats["resolved_pmcids"]+=1
  try:
   request={"verb":"GetRecord","metadataPrefix":"pmc","identifier":"oai:pubmedcentral.nih.gov:"+ID.fullmatch(pmcid).group(1)}
   xml=fetch(OAI+"?"+urllib.parse.urlencode(request))
   stats["oai_checked"]+=1
   parsed,error=jats_and_rights(xml)
   if error:
    status(r,error,21 if error=="reuse_license_not_verified" else 14,date)
    if error=="reuse_license_not_verified":stats["rights_restricted"]+=1
    else:stats["missing_source_sections"]+=1
    continue
   secs=parsed["sections"]
   r["analysis"]={
    "provenance":"NCBI PMC OAI-PMH JATS (automatic source-section extraction)",
    "license":parsed["license"],"license_url":"https://pmc.ncbi.nlm.nih.gov/articles/"+pmcid+"/",
    "methods":secs.get("methods",""),"results":secs.get("results",""),
    "discussion":secs.get("discussion",""),"limitations":secs.get("limitations",""),
    "figures":[],"fulltext_url":"https://pmc.ncbi.nlm.nih.gov/articles/"+pmcid+"/",
    "key_idea":(secs.get("results") or secs.get("discussion") or "")[:280],
    "extraction_date":date.isoformat(),"extraction_version":3,"sections_available":list(secs)}
   status(r,"full_text",365,date)
   stats["new_fulltexts"]+=1
  except (urllib.error.URLError,TimeoutError,ValueError,ET.ParseError) as err:
   status(r,"transient_error",1,date)
   stats["errors"]+=1
   if stats["errors"]<=3:print("PMC OAI temporary error:",doi,str(err)[:90])
  time.sleep(.38)
 LIB.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 stats["still_without_fulltext"]=sum(r.get("kind")=="scholarly" and not r.get("analysis") for r in rows)
 print(json.dumps(stats,ensure_ascii=False))
 return stats

if __name__=="__main__":run()

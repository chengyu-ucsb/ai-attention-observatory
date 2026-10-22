"""Repository-first recovery for missing articles, independent of campus logins.

Semantic Scholar's DOI-based API and Unpaywall OA-location metadata are queried
within small resumable batches. Only PDFs with explicit permissive reuse
licenses and known scholarly-host domains are parsed. Every other link is a
candidate for review, not full-text evidence. PDF bytes never reach git.

Never follow redirects off known scholarly domains; never use institutional
credentials, proxy cookies, scraped login sessions, or unauthorized bulk APIs.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from enrich_pdf_fulltext import extract_pdf,clean

ROOT=Path(__file__).resolve().parents[1]
LIB=ROOT/"data/library.json"
PERMISSIVE={"cc-by","cc-by-sa","cc0","public-domain"}
ALLOWED_HOSTS={
 "aclanthology.org","www.aclweb.org","aclweb.org",
 "arxiv.org","export.arxiv.org",
 "europepmc.org","www.ebi.ac.uk","www.ncbi.nlm.nih.gov","pmc.ncbi.nlm.nih.gov",
 "journals.plos.org","storage.googleapis.com",
 "www.frontiersin.org","frontiersin.org",
 "www.mdpi.com","mdpi.com",
 "peerj.com","www.peerj.com",
 "bio-protocol.org","www.bio-protocol.org",
 "www.nature.com","link.springer.com",
 "www.tandfonline.com","www.sciencedirect.com",
 "www.jmir.org","jmir.org",
}
EMAIL=os.getenv("UNPAYWALL_EMAIL","fangcu@ucmail.uc.edu")
DOI_RX=re.compile(r"^10\.\d{4,9}/\S+$",re.I)


def license_name(value):
 v=str(value or "").strip().lower().replace("_","-")
 v=re.sub(r"[\s]+","-",v)
 v=v.replace("creativecommons.org/licenses/","")
 v=v.replace("creativecommons.org/publicdomain/zero/","cc0/")
 v=v.replace("ccbysa","cc-by-sa").replace("ccby","cc-by")
 if any(x in v for x in ("-nc","-nd","noncommercial","noderivatives","no-derivatives")):return ""
 if v in ("cc-by","cc-by-2.0","cc-by-3.0","cc-by-4.0","cc-by/4.0","cc-by/3.0"):
  return "cc-by"
 if v in ("cc-by-sa","cc-by-sa-2.0","cc-by-sa-3.0","cc-by-sa-4.0","cc-by-sa/4.0"):
  return "cc-by-sa"
 if v in ("cc0","cc0-1.0","cc0/1.0","public-domain","publicdomain"):return "cc0"
 if re.fullmatch(r"https?://(?:www\.)?creativecommons\.org/licenses/by/(?:2\.0|3\.0|4\.0)/?",str(value or ""),re.I):return "cc-by"
 if re.fullmatch(r"https?://(?:www\.)?creativecommons\.org/licenses/by-sa/(?:2\.0|3\.0|4\.0)/?",str(value or ""),re.I):return "cc-by-sa"
 return ""


def supported_pdf(url):
 try:
  p=urllib.parse.urlsplit(url)
  host=(p.hostname or "").lower()
  return (p.scheme=="https" and p.port in (None,443) and
    not p.username and not p.password and host in ALLOWED_HOSTS and
    bool(p.path) and len(url)<=1500)
 except ValueError:return False


class RedirectGuard(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if not supported_pdf(newurl):
   raise ValueError("PDF redirect leaves approved scholarly hosts")
  return super().redirect_request(req,fp,code,msg,headers,newurl)


def pdf_bytes(url,limit=18_000_000):
 if not supported_pdf(url):raise ValueError("Unapproved PDF host")
 req=urllib.request.Request(url,headers={
  "User-Agent":"AI-Attention-Observatory/4.3 (academic research, contact fangcu@ucmail.uc.edu)",
  "Accept":"application/pdf"})
 opener=urllib.request.build_opener(RedirectGuard())
 with opener.open(req,timeout=23) as response:
  if not supported_pdf(response.geturl()):raise ValueError("Unapproved PDF redirect")
  length=response.headers.get("Content-Length")
  if length and int(length)>limit:raise ValueError("Oversize PDF")
  payload=response.read(limit+1)
  if len(payload)>limit or not payload.startswith(b"%PDF"):raise ValueError("Not a bounded PDF")
  return payload


def metadata_request(url,key="",method="GET",payload=None):
 headers={
  "User-Agent":"AI-Attention-Observatory/4.3 (contact fangcu@ucmail.uc.edu)",
  "Accept":"application/json"}
 if key:headers["x-api-key"]=key
 if payload is not None:
  headers["Content-Type"]="application/json"
  payload=json.dumps(payload).encode()
 req=urllib.request.Request(url,method=method,data=payload,headers=headers)
 with urllib.request.urlopen(req,timeout=26) as resp:
  return json.loads(resp.read(8_000_000))


def s2_batch(dois):
 """Official /paper/batch API returns rows in input ID order, null on misses."""
 ids=["DOI:"+d for d in dois]
 key=os.getenv("SEMANTIC_SCHOLAR_API_KEY","").strip()
 url="https://api.semanticscholar.org/graph/v1/paper/batch?fields="+urllib.parse.quote(
   "title,externalIds,openAccessPdf,isOpenAccess",safe=",")
 result=metadata_request(url,key=key,method="POST",payload={"ids":ids})
 if not isinstance(result,list) or len(result)!=len(ids):
  raise ValueError("Semantic Scholar batch response shape unexpected")
 mapping={}
 for doi,work in zip(dois,result):
  if not work or not isinstance(work,dict):continue
  external=(work.get("externalIds") or {}).get("DOI") or ""
  if external.lower().replace("https://doi.org/","")!=doi.lower():continue
  pdf=work.get("openAccessPdf") or {}
  href=pdf.get("url") or ""
  if href.startswith("https://"):
   mapping[doi]={"url":href,"license":pdf.get("license") or "","provider":"Semantic Scholar"}
 return mapping


def unpaywall_doi(doi):
 url=("https://api.unpaywall.org/v2/"+urllib.parse.quote(doi,safe="/")+"?"+
  urllib.parse.urlencode({"email":EMAIL}))
 work=metadata_request(url)
 if str(work.get("doi") or "").lower()!=doi.lower():return []
 locations=work.get("oa_locations") or []
 if work.get("best_oa_location"):locations=[work["best_oa_location"]]+locations
 result=[]
 seen=set()
 for loc in locations:
  url=loc.get("url_for_pdf") or ""
  if url.startswith("https://") and url not in seen:
   result.append({"url":url,"license":loc.get("license") or "","provider":"Unpaywall"})
   seen.add(url)
 return result


def candidates_for(doi,from_s2,from_unpaywall):
 possibilities=[]
 seen=set()
 for c in ([from_s2] if from_s2 else [])+from_unpaywall:
  if not c or not c.get("url") or c["url"] in seen:continue
  seen.add(c["url"])
  possibilities.append(c)
 return possibilities


def eligible(record,today):
 if record.get("kind")!="scholarly" or record.get("analysis"):return False
 doi=(record.get("doi") or "").strip()
 if not DOI_RX.fullmatch(doi):return False
 q=record.get("repository_recovery") or {}
 if q.get("version")!=1:return True
 try:return dt.date.fromisoformat(q.get("next_at",""))<=today
 except (ValueError,TypeError):return True


def checkpoint(record,status,days,today,providers=None):
 q=record.setdefault("repository_recovery",{})
 q.update(version=1,status=status,
  last_at=today.isoformat(),next_at=(today+dt.timedelta(days=days)).isoformat(),
  attempts=q.get("attempts",0)+1)
 if providers:q["providers"]=providers


def recover(record,options,today):
 """Conservative acceptance: explicit supported license AND trusted PDF host."""
 if not options:return "no_oa_pdf_reported"
 licensed=[x for x in options if license_name(x.get("license"))]
 trusted=[x for x in licensed if supported_pdf(x.get("url") or "")]
 if not licensed:return "license_unverified"
 if not trusted:return "pdf_host_unapproved"
 for option in trusted[:2]:
  try:
   raw=pdf_bytes(option["url"])
   secs=extract_pdf(raw)
   if not (secs.get("results") or secs.get("discussion")):continue
   record["analysis"]={
    "provenance":option["provider"]+" independently discovered licensed OA PDF; pypdf automatic extraction",
    "license":license_name(option["license"]),
    "license_url":option["url"],
    "fulltext_url":option["url"],
    "methods":secs.get("methods",""),
    "results":secs.get("results",""),
    "discussion":secs.get("discussion",""),
    "limitations":secs.get("limitations",""),
    "figures":[],
    "key_idea":clean(secs.get("results") or secs.get("discussion"))[:280],
    "extraction_date":today.isoformat(),
    "extraction_version":1,
    "sections_available":list(secs),
    "pdf_text_extraction":"pypdf; automated section boundaries; verify original"
   }
   return "full_text_recovered"
  except urllib.error.HTTPError as e:
   if e.code==429:raise
   if e.code in (401,403,404):continue
   raise
  except (ValueError,TimeoutError,urllib.error.URLError):continue
 return "pdf_unreadable_or_blocked"


def run():
 records=json.loads(LIB.read_text(encoding="utf-8"))
 today=dt.date.today()
 candidates=[r for r in records if eligible(r,today)]
 # Prefer previously blocked XML papers, then directly AI-related records.
 candidates.sort(key=lambda r:(
  0 if (r.get("fulltext_attempt") or {}).get("status") in
    ("waiting_for_license","waiting_for_machine_text","source_unavailable") else 1,
  0 if (r.get("source_group") or "").lower()=="ai-specific" else 1,
  (r.get("repository_recovery") or {}).get("attempts",0)))
 cap=max(1,min(int(os.getenv("REPO_OA_BATCH","16")),36))
 work=candidates[:cap]
 stats={"attempted":len(work),"fulltexts_recovered":0,"license_unverified":0,
        "pdf_unreadable_or_blocked":0,"provider_limited":0,
        "no_oa_pdf_reported":0,"provider_incomplete":0,"pdf_host_unapproved":0,"provider_error":0,
        "semantic_scholar_rate_limited":0,
        "remaining_without_sections":0}
 if not work:
  stats["remaining_without_sections"]=sum(r.get("kind")=="scholarly" and not r.get("analysis") for r in records)
  print(json.dumps(stats));return stats
 dois=[r["doi"].strip().lower() for r in work]
 s2_error=False
 try:
  s2=s2_batch(dois)
 except (urllib.error.HTTPError,urllib.error.URLError,ValueError,TimeoutError) as e:
  s2_error=True
  if isinstance(e,urllib.error.HTTPError) and e.code==429:
   stats["semantic_scholar_rate_limited"]=1
  s2={}
  # A provider outage must not block independent Unpaywall attempts.
  print("Semantic Scholar metadata unavailable; trying alternative OA locations")
 unpaywall_budget=max(0,min(int(os.getenv("REPO_UNPAYWALL_LIMIT","12")),cap))
 for i,paper in enumerate(work):
  doi=dois[i]
  alternatives=[]
  provider_status=[]
  if i<unpaywall_budget:
   try:
    alternatives=unpaywall_doi(doi)
    provider_status.append("unpaywall_checked")
   except urllib.error.HTTPError as e:
    if e.code in (401,403,404):provider_status.append("unpaywall_no_entry")
    elif e.code==429:
     provider_status.append("unpaywall_rate_limited")
     unpaywall_budget=i  # skip the rest of this batch
    else:provider_status.append("unpaywall_error")
   except (ValueError,urllib.error.URLError,TimeoutError):
    provider_status.append("unpaywall_error")
  if doi in s2:provider_status.append("s2_candidate")
  opts=candidates_for(doi,s2.get(doi),alternatives)
  try:
   status=recover(paper,opts,today)
   if not opts and s2_error:
    status="provider_incomplete"
  except urllib.error.HTTPError as e:
   if e.code==429:
    status="provider_limited";stats["provider_limited"]+=1
   else:status="provider_error";stats["provider_error"]+=1
  except (ValueError,urllib.error.URLError,TimeoutError,TypeError):
   status="provider_error";stats["provider_error"]+=1
  stats[status]=stats.get(status,0)+1 if status!="provider_limited" else stats["provider_limited"]
  delay=365 if status=="full_text_recovered" else 2 if status in ("provider_error","provider_limited","provider_incomplete") else 30
  checkpoint(paper,status,delay,today,provider_status)
  time.sleep(.12)
 LIB.write_text(json.dumps(records,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
 stats["remaining_without_sections"]=sum(r.get("kind")=="scholarly" and not r.get("analysis") for r in records)
 print(json.dumps(stats))
 return stats

if __name__=="__main__":run()

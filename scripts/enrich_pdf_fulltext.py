"""Licensed OA PDF fallback for works with no reusable XML.

Downloaded PDFs are held in memory only and never committed or served. Only
machine-extractable source sections are retained in the private index, with
strong provenance and explicit license checks. This is not OCR and cannot
recover image-only PDFs. PDF errors cannot block other acquisition sources.
"""
from __future__ import annotations
import datetime as dt
import io
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
LIB=ROOT/"data/library.json"
ALLOW={"cc-by","cc-by-sa","cc0","public-domain"}
HEAD=re.compile(r"^\s*(?:(?:\d+(?:\.\d+){0,3})[\s.)-]+)?(materials and methods|methodology|methods?|study design|results?(?: and discussion)?|findings|discussion|general discussion|limitations|conclusions?(?: and future work)?|concluding remarks|empirical findings|evaluation results?|experimental results?|materials and methods|references|bibliography|acknowledgments)\s*[:.]?\s*$",re.I)
PARA=re.compile(r"\s+")
USER_AGENT="AI-Attention-Observatory/4.1 (fangcu@ucmail.uc.edu)"
def clean(t):return PARA.sub(" ",str(t or "")).strip()
def fetch(url,key="",binary=False):
 if not url.startswith(("https://api.openalex.org/works/","https://content.openalex.org/works/")):
  raise ValueError("Only official OpenAlex hosts are supported")
 if key:
  url=url+("&" if "?" in url else "?")+urllib.parse.urlencode({"api_key":key})
 req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/json,application/pdf"})
 with urllib.request.urlopen(req,timeout=30) as r:
  length=r.headers.get("Content-Length")
  if length and int(length)>18_000_000:raise ValueError("PDF too large")
  return r.read(18_000_001)
def section_name(heading):
 text=heading.lower().strip()
 if text.startswith(("material","method","study design")):return "methods"
 if text.startswith(("result","finding","empirical finding","evaluation result","experimental result")):return "results"
 if text.startswith(("discussion","general discussion","conclusion","concluding")):return "discussion"
 if text.startswith("limitation"):return "limitations"
 return None
def collect_sections(lines):
 sections={}
 current=None
 for line in lines:
  stripped=clean(line)
  if len(stripped)>280:continue
  found=HEAD.match(stripped)
  if found:
   new=section_name(found.group(1))
   if not new:break  # references and appendices are not outcomes
   current=new;continue
  if not current or not stripped or len(stripped)<35:continue
  joined=sections.get(current,"")
  if len(joined)<6800:
   sections[current]=(joined+" "+stripped).strip()[:6800]
 return sections
def extract_pdf(pdf):
 if len(pdf)>18_000_000 or not pdf.startswith(b"%PDF"):return {}
 from pypdf import PdfReader
 try:
  reader=PdfReader(io.BytesIO(pdf),strict=False)
  if reader.is_encrypted:return {}
  lines=[]
  for page in reader.pages[:35]:
   text=page.extract_text(extraction_mode="layout") or ""
   lines.extend(text.splitlines())
  sections=collect_sections(lines)
  # The Results or Discussion heading must be clearly identified.
  if not (sections.get("results") or sections.get("discussion")):return {}
  return sections
 except Exception:
  return {}
def work_url(record):
 doi=(record.get("doi") or "").lower()
 if doi:return "https://api.openalex.org/works/"+urllib.parse.quote("https://doi.org/"+doi,safe=":")
 url=(record.get("url") or "")
 if re.fullmatch(r"https://openalex\.org/W\d+",url):
  return url.replace("https://openalex.org/","https://api.openalex.org/works/")
 return ""
def eligible(record,date):
 if record.get("kind")!="scholarly" or record.get("analysis") or not work_url(record):return False
 attempt=record.get("pdf_fulltext_attempt") or {}
 if attempt.get("version")!=1:return True
 try:return dt.date.fromisoformat(attempt.get("next_at","")[:10])<=date
 except ValueError:return True
def state(record,kind,days,date):
 old=record.setdefault("pdf_fulltext_attempt",{})
 old.update(version=1,status=kind,last_at=date.isoformat(),next_at=(date+dt.timedelta(days=days)).isoformat(),
            attempts=old.get("attempts",0)+1)
def run():
 rows=json.loads(LIB.read_text())
 key=os.getenv("OPENALEX_API_KEY","").strip()
 limit=max(1,min(int(os.getenv("PDF_FULLTEXT_LOOKUPS","22")),55))
 pdf_limit=max(1,min(int(os.getenv("PDF_FULLTEXT_DOWNLOADS","9")),25))
 date=dt.date.today()
 ready=[r for r in rows if eligible(r,date)]
 # Prioritize papers where XML retrieval was already attempted and failed.
 ready.sort(key=lambda r:(0 if r.get("fulltext_attempt",{}).get("status") in ("waiting_for_machine_text","source_unavailable","missing_sections") else 1,
                          0 if r.get("doi") else 1,
                          (r.get("pdf_fulltext_attempt") or {}).get("attempts",0),
                          -(int((r.get("published") or "0000")[:4]) if (r.get("published") or "")[:4].isdigit() else 0)))
 stats={"lookup_attempts":0,"pdf_downloads":0,"fulltexts_recovered":0,
        "no_licensed_pdf":0,"no_machine_readable_sections":0,"errors":0}
 for paper in ready[:limit]:
  if stats["pdf_downloads"]>=pdf_limit:break
  try:
   raw=fetch(work_url(paper),key)
   stats["lookup_attempts"]+=1
   work=json.loads(raw)
   lic=next(((loc.get("license") or "").lower() for loc in
             [work.get("best_oa_location") or {}]+(work.get("locations") or [])
             if (loc.get("license") or "").lower() in ALLOW),"")
   url=(work.get("content_urls") or {}).get("pdf") or ""
   if not lic or not re.fullmatch(r"https://content\.openalex\.org/works/W\d+\.pdf",url):
    state(paper,"no_licensed_machine_pdf",21,date);stats["no_licensed_pdf"]+=1;continue
   stats["pdf_downloads"]+=1
   pdf=fetch(url,key,True)
   sections=extract_pdf(pdf)
   if not (sections.get("results") or sections.get("discussion")):
    state(paper,"pdf_has_no_recognized_sections",30,date)
    stats["no_machine_readable_sections"]+=1;continue
   landing=(work.get("best_oa_location") or {}).get("landing_page_url") or paper.get("url")
   if not landing or not landing.startswith("https://"):landing=paper.get("url") or ""
   paper["analysis"]={
     "provenance":"OpenAlex cached licensed OA PDF; local text extraction (not OCR)",
     "license":lic,"fulltext_url":landing,"license_url":landing,
     "methods":sections.get("methods",""),"results":sections.get("results",""),
     "discussion":sections.get("discussion",""),"limitations":sections.get("limitations",""),
     "figures":[],"key_idea":(sections.get("results") or sections.get("discussion") or "")[:280],
     "extraction_date":date.isoformat(),"extraction_version":3,
     "sections_available":list(sections),
     "pdf_text_extraction":"pypdf; section boundary heuristics; check source"}
   state(paper,"full_text",365,date)
   stats["fulltexts_recovered"]+=1
  except (urllib.error.URLError,TimeoutError,ValueError,TypeError,KeyError,json.JSONDecodeError) as err:
   stats["errors"]+=1
   state(paper,"pdf_temporary_error",2,date)
   if stats["errors"]<=3:print("PDF fallback:",str(err)[:130])
  time.sleep(.25)
 LIB.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
 stats["remaining_scholarly"]=sum(r.get("kind")=="scholarly" and not r.get("analysis") for r in rows)
 print(json.dumps(stats))
 return stats

if __name__=="__main__":run()

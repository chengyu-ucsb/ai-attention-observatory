"""Licensed OA PDF fallback for works with no reusable XML.

Downloaded PDFs are held in memory only and never committed or served. Only
machine-extractable source sections are retained in the private index, with
strong provenance and explicit license checks. This is not OCR and cannot
recover image-only PDFs. PDF errors cannot block other acquisition sources.
OpenAlex's XML and PDF stages share a persistent provider quota pause.
"""
from __future__ import annotations
import datetime as dt
import io
import json
import os
import pathlib
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

import enrich_openalex_fulltext as openalex
from academic_state_schema import strict_json_loads

ROOT=pathlib.Path(__file__).resolve().parents[1]
LIB=ROOT/"data/library.json"
ALLOW={"cc-by","cc-by-sa","cc0","public-domain"}
HEAD=re.compile(r"^\s*(?:(?:\d+(?:\.\d+){0,3})[\s.)-]+)?(materials and methods|methodology|methods?|study design|results?(?: and discussion)?|findings|discussion|general discussion|limitations|conclusions?(?: and future work)?|concluding remarks|empirical findings|evaluation results?|experimental results?|materials and methods|references|bibliography|acknowledgments)\s*[:.]?\s*$",re.I)
PARA=re.compile(r"\s+")
SURROGATE_PAIR=re.compile(r"[\ud800-\udbff][\udc00-\udfff]")
SURROGATE=re.compile(r"[\ud800-\udfff]")
USER_AGENT="AI-Attention-Observatory/4.1 (fangcu@ucmail.uc.edu)"
class PDFTextEncodingError(ValueError):
 """Malformed extraction; diagnostics contain no source passages."""
 def __init__(self,field,offset,codepoint):
  self.diagnostic={"reason":"unpaired_surrogate","field":field,
                   "offset":offset,"codepoint":f"U+{codepoint:04X}"}
  super().__init__(f"unpaired_surrogate in {field} at {offset}: U+{codepoint:04X}")

def unicode_text(text,field):
 """Join valid UTF-16 pairs without guessing or dropping malformed glyphs.

 Run before any slicing: a length cap must not split a valid pair. Scalar
 non-BMP characters, combining marks and all other source text stay unchanged.
 """
 text=SURROGATE_PAIR.sub(lambda m:chr(0x10000+((ord(m[0][0])-0xD800)<<10)
                                      +ord(m[0][1])-0xDC00),text)
 bad=SURROGATE.search(text)
 if bad:raise PDFTextEncodingError(field,bad.start(),ord(bad[0]))
 return text

def json_bytes(value):
 """Strictly encode before opening a destination, never escape bad source text."""
 return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8")

def atomic_write(path,payload):
 """Replace one file on its own filesystem only after a full successful write."""
 temporary=None
 try:
  with tempfile.NamedTemporaryFile(mode="wb",dir=path.parent,
                                   prefix="."+path.name+"-",suffix=".tmp",delete=False) as handle:
   temporary=pathlib.Path(handle.name)
   handle.write(payload)
   handle.flush()
   os.fsync(handle.fileno())
  os.replace(temporary,path)
  temporary=None
 finally:
  if temporary is not None:temporary.unlink(missing_ok=True)

def save_checkpoint(library_path,rows,state_path,provider_state,save_state):
 # This is not a cross-file transaction. Preserve an independently valid
 # active pause even when the library cannot be serialized; never let corrupt
 # article data cause repeated requests to a provider that just returned 429.
 state_payload=json_bytes(provider_state) if save_state else None
 try:
  library_payload=json_bytes(rows)
 except (ValueError,TypeError):
  if state_payload is not None and openalex.parse(provider_state.get("quota_pause_until"))>openalex.now():
   atomic_write(state_path,state_payload)
  raise
 if state_payload is not None:atomic_write(state_path,state_payload)
 atomic_write(library_path,library_payload)

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
 for number,line in enumerate(lines,1):
  stripped=clean(unicode_text(line,f"line {number}"))
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
  for number,page in enumerate(reader.pages[:35],1):
   text=page.extract_text(extraction_mode="layout") or ""
   text=unicode_text(text,f"page {number}")
   lines.extend(text.splitlines())
  sections=collect_sections(lines)
  # The Results or Discussion heading must be clearly identified.
  if not (sections.get("results") or sections.get("discussion")):return {}
  return sections
 except PDFTextEncodingError:
  raise
 except Exception:
  return {}
def work_url(record):
 doi=(record.get("doi") or "").lower()
 if doi:return "https://api.openalex.org/works/"+urllib.parse.quote("https://doi.org/"+doi,safe=":")
 url=(record.get("url") or "")
 if re.fullmatch(r"https://openalex\.org/W\d+",url):
  return url.replace("https://openalex.org/","https://api.openalex.org/works/")
 return ""
def eligible(record,date,at=None):
 if record.get("kind")!="scholarly" or record.get("analysis") or not work_url(record):return False
 attempt=record.get("pdf_fulltext_attempt") or {}
 if attempt.get("version")!=1:return True
 if attempt.get("status")=="budget_retry":
  return openalex.parse(attempt.get("next_at"))<=(at or openalex.now())
 try:return dt.date.fromisoformat(attempt.get("next_at","")[:10])<=date
 except ValueError:return True
def state(record,kind,days,date):
 old=record.setdefault("pdf_fulltext_attempt",{})
 old.pop("text_error",None)
 old.update(version=1,status=kind,last_at=date.isoformat(),next_at=(date+dt.timedelta(days=days)).isoformat(),
            attempts=old.get("attempts",0)+1)
def run(library_path=None,state_path=None):
 # Keep run() and the existing environment controls compatible. A custom library
 # uses its adjacent provider state, never the repository's live queue state.
 library_path=pathlib.Path(library_path) if library_path is not None else LIB
 state_path=pathlib.Path(state_path) if state_path is not None else library_path.with_name("fulltext-backfill-state.json")
 if library_path.resolve()==state_path.resolve():raise ValueError("library and provider state paths must differ")
 rows=strict_json_loads(library_path.read_text(encoding="utf-8"))
 provider_state=strict_json_loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
 if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
  raise ValueError("library must contain a list of records")
 if not isinstance(provider_state,dict):raise ValueError("provider state must be an object")
 # Reject corrupt pre-existing input before spending any provider requests.
 json_bytes(rows)
 json_bytes(provider_state)
 t=openalex.now()
 stats={"lookup_attempts":0,"pdf_downloads":0,"request_attempts":0,"fulltexts_recovered":0,
        "no_licensed_pdf":0,"no_machine_readable_sections":0,"invalid_unicode":0,"errors":0,"rate_limited":0,
        "status":"no_ready_sources","quota_pause_until":None,
        "remaining_scholarly":sum(r.get("kind")=="scholarly" and not r.get("analysis") for r in rows)}
 if openalex.parse(provider_state.get("quota_pause_until"))>t:
  stats.update(status="waiting_for_budget",quota_pause_until=provider_state["quota_pause_until"])
  print(json.dumps(stats))
  return stats
 pause_changed=provider_state.get("quota_pause_until") is not None
 provider_state["quota_pause_until"]=None
 key=os.getenv("OPENALEX_API_KEY","").strip()
 limit=max(1,min(int(os.getenv("PDF_FULLTEXT_LOOKUPS","22")),55))
 pdf_limit=max(1,min(int(os.getenv("PDF_FULLTEXT_DOWNLOADS","9")),25))
 date=t.date()
 ready=[r for r in rows if eligible(r,date,t)]
 # Prioritize papers where XML retrieval was already attempted and failed.
 ready.sort(key=lambda r:(0 if r.get("fulltext_attempt",{}).get("status") in ("waiting_for_machine_text","source_unavailable","missing_sections") else 1,
                          0 if r.get("doi") else 1,
                          (r.get("pdf_fulltext_attempt") or {}).get("attempts",0),
                          -(int((r.get("published") or "0000")[:4]) if (r.get("published") or "")[:4].isdigit() else 0)))
 if ready:stats["status"]="batch_processed"
 for paper in ready[:limit]:
  if stats["pdf_downloads"]>=pdf_limit:break
  previous_attempts=(paper.get("pdf_fulltext_attempt") or {}).get("attempts",0)
  url=""
  try:
   # Count requests before dispatch, including HTTP failures and timeouts.
   stats["lookup_attempts"]+=1
   stats["request_attempts"]+=1
   raw=fetch(work_url(paper),key)
   work=json.loads(raw)
   lic=next(((loc.get("license") or "").lower() for loc in
             [work.get("best_oa_location") or {}]+(work.get("locations") or [])
             if (loc.get("license") or "").lower() in ALLOW),"")
   url=(work.get("content_urls") or {}).get("pdf") or ""
   if not lic or not re.fullmatch(r"https://content\.openalex\.org/works/W\d+\.pdf",url):
    state(paper,"no_licensed_machine_pdf",21,date);stats["no_licensed_pdf"]+=1;continue
   stats["pdf_downloads"]+=1
   stats["request_attempts"]+=1
   pdf=fetch(url,key,True)
   sections={name:unicode_text(text,name) for name,text in extract_pdf(pdf).items()}
   if not (sections.get("results") or sections.get("discussion")):
    state(paper,"pdf_has_no_recognized_sections",30,date)
    stats["no_machine_readable_sections"]+=1;continue
   landing=(work.get("best_oa_location") or {}).get("landing_page_url") or paper.get("url")
   if not landing or not landing.startswith("https://"):landing=paper.get("url") or ""
   analysis={
     "provenance":"OpenAlex cached licensed OA PDF; local text extraction (not OCR)",
     "license":lic,"fulltext_url":landing,"license_url":landing,
     "methods":sections.get("methods",""),"results":sections.get("results",""),
     "discussion":sections.get("discussion",""),"limitations":sections.get("limitations",""),
     "figures":[],"key_idea":(sections.get("results") or sections.get("discussion") or "")[:280],
     "extraction_date":date.isoformat(),"extraction_version":3,
     "sections_available":list(sections),
     "pdf_text_extraction":"pypdf; section boundary heuristics; check source"}
   # Provider metadata must also be encodable before attaching any analysis.
   json_bytes(analysis)
   paper["analysis"]=analysis
   state(paper,"full_text",365,date)
   stats["fulltexts_recovered"]+=1
  except PDFTextEncodingError as err:
   state(paper,"pdf_invalid_unicode",30,date)
   paper["pdf_fulltext_attempt"]["text_error"]={**err.diagnostic,"source_pdf":url}
   stats["invalid_unicode"]+=1
   stats["errors"]+=1
   print("PDF fallback:",json.dumps({"doi":paper.get("doi"),
                                   **paper["pdf_fulltext_attempt"]["text_error"]}))
  except (urllib.error.URLError,TimeoutError,ValueError,TypeError,KeyError,json.JSONDecodeError) as err:
   if isinstance(err,urllib.error.HTTPError) and err.code==429:
    until=openalex.pause_time(err)
    provider_state.update(quota_pause_until=until,status="waiting_for_budget")
    pause_changed=True
    stats.update(status="waiting_for_budget",quota_pause_until=until)
    stats["rate_limited"]+=1
    state(paper,"budget_retry",0,date)
    paper["pdf_fulltext_attempt"].update(last_at=openalex.iso(t),next_at=until)
    # The provider is unavailable, not every remaining paper. Leave unattempted
    # rows untouched so XML and PDF can resume after the shared reset.
    break
   stats["errors"]+=1
   state(paper,"pdf_temporary_error",2,date)
   if stats["errors"]<=3:print("PDF fallback:",str(err)[:130])
  finally:
   # Retain completed outcomes and cooldowns before trying the next paper.
   # Later extraction/process failures must not replay the completed batch.
   if (paper.get("pdf_fulltext_attempt") or {}).get("attempts",0)!=previous_attempts:
    if provider_state.get("status")=="waiting_for_budget" and stats["status"]!="waiting_for_budget":
     provider_state["status"]=stats["status"]
    save_checkpoint(library_path,rows,state_path,provider_state,pause_changed)
    pause_changed=False
  time.sleep(.25)
 if pause_changed:
  if provider_state.get("status")=="waiting_for_budget" and stats["status"]!="waiting_for_budget":
   provider_state["status"]=stats["status"]
  save_checkpoint(library_path,rows,state_path,provider_state,True)
 stats["remaining_scholarly"]=sum(r.get("kind")=="scholarly" and not r.get("analysis") for r in rows)
 print(json.dumps(stats))
 return stats

if __name__=="__main__":run()

"""Create attributable reading notes from permissively licensed OA XML only."""
import json,re,pathlib,urllib.request,urllib.parse,xml.etree.ElementTree as ET,time,datetime,os
ROOT=pathlib.Path(__file__).resolve().parents[1];DATA=ROOT/"data"
def req(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"AIAttentionObservatory/1.2 academic indexing"}),timeout=18) as response:return response.read()
def clean(t):return " ".join((t or "").split())
def permitted(licenses):
 for lic in licenses:
  val=lic.lower().replace("–","-")
  if "cc by-nc" in val or "cc-by-nc" in val or "cc by-nd" in val or "cc-by-nd" in val or "noncommercial" in val or "no derivatives" in val or "noderivatives" in val:continue
  if "cc by" in val or "cc-by" in val or "cc0" in val or "creative commons zero" in val:return True
 return False
def extract_sections(root):
 """Preserve several substantive paragraphs per article section for synthesis.

 Methods, Results and Discussion remain separate. Avoid copying whole papers,
 and avoid indexing a references section as a research result.
 """
 sections={}
 for sec in root.findall(".//body//sec"):
  heading=sec.find("title")
  title=clean(" ".join(heading.itertext()) if heading is not None else "").lower()
  if not title:continue
  key=("limitations" if "limitation" in title else
       "results" if "result" in title or "finding" in title else
       "discussion" if "discussion" in title or "conclusion" in title else
       "methods" if any(x in title for x in ("method","study design","participant","procedure")) else "")
  if not key:continue
  # Exclude nested sections from a parent if both are labeled; nested text
  # can be added again by its own section if useful.
  paras=[clean(" ".join(p.itertext())) for p in sec.findall(".//p")]
  paras=[p for p in paras if len(p)>=50]
  # Method/Results samples should be meaningful, not a single heading.
  if not paras:continue
  old=sections.get(key,"")
  candidate=" ".join(paras)
  if old: candidate=old+" "+candidate
  if len(candidate)>4800:
   candidate=candidate[:4800].rsplit(" ",1)[0]
  sections[key]=candidate
 return sections
def run():
 path=DATA/"library.json";records=json.loads(path.read_text());updated=0;attempted=0
 today=datetime.date.today().isoformat();limit=max(1,min(75,int(os.getenv("OA_ENRICH_LIMIT","38"))))
 candidates=[r for r in records if r.get("kind")=="scholarly" and r.get("doi") and not r.get("analysis")]
 # A PMC-like open-access link is useful evidence that XML may already exist.
 candidates.sort(key=lambda r:(0 if any(k in (r.get("open_access_url") or "").lower() for k in ("pmc","bmc","frontiers","plos")) else 1,
                               0 if r.get("oa_checked") is None else 1,r.get("oa_checked") or ""))
 for r in candidates:
  if attempted>=limit:break
  if r.get("oa_checked") and (datetime.date.today()-datetime.date.fromisoformat(r["oa_checked"])).days<7:continue
  attempted+=1;r["oa_checked"]=today
  try:
   url="https://www.ebi.ac.uk/europepmc/webservices/rest/search?"+urllib.parse.urlencode({"query":"DOI:"+r["doi"],"format":"json","pageSize":1})
   obj=json.loads(req(url));matches=obj.get("resultList",{}).get("result",[])
   if not matches:continue
   v=matches[0];pmcid=v.get("pmcid")
   if not pmcid or v.get("isOpenAccess")!="Y":continue
   root=ET.fromstring(req("https://www.ebi.ac.uk/europepmc/webservices/rest/"+urllib.parse.quote(pmcid)+"/fullTextXML"))
   licenses=[" ".join(el.itertext()).lower() for el in root.findall(".//license")]
   # Public site cannot republish arbitrary copyrighted article excerpts.
   if not permitted(licenses):continue
   extracted=extract_sections(root)
   if not extracted:continue
   figures=[]
   for f in root.findall(".//fig")[:3]:
    label=clean(" ".join(f.find("label").itertext()) if f.find("label") is not None else "Figure")
    cap=f.find("caption");caption=clean(" ".join(cap.itertext()))[:240] if cap is not None else ""
    figures.append({"label":label,"caption":caption})
   r["analysis"]={"provenance":"Europe PMC open-access fullTextXML; automatically extracted article sections","license":licenses[0][:160],"methods":extracted.get("methods",""),"results":extracted.get("results",""),"discussion":extracted.get("discussion",""),"limitations":extracted.get("limitations",""),"figures":figures,"fulltext_url":"https://europepmc.org/articles/"+pmcid,"key_idea":(extracted.get("results") or extracted.get("discussion") or "")[:280]}
   updated+=1
  except Exception as e:print("OA extraction skipped",r.get("doi"),str(e)[:100])
  time.sleep(.15)
 path.write_text(json.dumps(records,indent=2,ensure_ascii=False)+"\n")
 print("OA records checked",attempted,"enriched",updated)
if __name__=="__main__":run()

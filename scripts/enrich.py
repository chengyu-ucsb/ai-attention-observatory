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
 sections={}
 for sec in root.findall(".//body//sec"):
  title=clean(" ".join(sec.find("title").itertext()) if sec.find("title") is not None else "").lower()
  if not title:continue
  if any(k in title for k in ("method","result","discussion","limitation")):
   text=clean(" ".join(sec.itertext()))
   name=next(k for k in ("methods","results","discussion","limitations") if k.rstrip("s") in title or k in title)
   if name not in sections:sections[name]=text[:500]
 return sections
def run():
 path=DATA/"library.json";records=json.loads(path.read_text());updated=0;attempted=0
 today=datetime.date.today().isoformat();limit=int(os.getenv("OA_ENRICH_LIMIT","22"))
 for r in records:
  if attempted>=limit:break
  if r.get("analysis") or not r.get("doi") or r.get("kind")!="scholarly":continue
  if r.get("oa_checked") and (datetime.date.today()-datetime.date.fromisoformat(r["oa_checked"])).days<45:continue
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

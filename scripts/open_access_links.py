"""Annotate DOI records with open-access locations without downloading copyrighted PDFs."""
import datetime,json,os,pathlib,time,urllib.parse,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
LIB=ROOT/"data/library.json"
def get(url):
 req=urllib.request.Request(url,headers={"User-Agent":"AttentionAIObservatory/2.1 (fangcu@ucmail.uc.edu)","Accept":"application/json"})
 with urllib.request.urlopen(req,timeout=22) as r:return json.load(r)
def main():
 items=json.loads(LIB.read_text());today=datetime.date.today().isoformat()
 # Batch DOI filters to avoid a request per paper; only recheck missing links monthly.
 todo=[r for r in items if r.get("kind")=="scholarly" and r.get("doi") and not r.get("oa_meta_checked")]
 limit=int(os.getenv("OA_LINK_LIMIT","100"));todo=todo[:limit]
 changed=0;errors=[]
 for i in range(0,len(todo),20):
  batch=todo[i:i+20]
  filt="doi:"+"|".join("https://doi.org/"+r["doi"] for r in batch)
  params={"filter":filt,"per_page":len(batch)}
  if os.getenv("OPENALEX_API_KEY"):params["api_key"]=os.environ["OPENALEX_API_KEY"]
  try:
   matches=get("https://api.openalex.org/works?"+urllib.parse.urlencode(params)).get("results",[])
   mapping={(w.get("doi") or "").replace("https://doi.org/","").lower():w for w in matches}
   for r in batch:
    r["oa_meta_checked"]=today
    w=mapping.get(r["doi"].lower())
    if not w:continue
    loc=w.get("best_oa_location") or {}
    url=loc.get("landing_page_url") or loc.get("pdf_url") or ""
    if url.startswith("https://"):
     r["open_access_url"]=url
     r["open_access_license"]=(loc.get("license") or "unknown")
     r["open_access_version"]=loc.get("version") or ""
     changed+=1
  except Exception as ex:errors.append(str(ex)[:120])
  time.sleep(.4)
 LIB.write_text(json.dumps(items,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps({"doi_checked":len(todo),"oa_links_found":changed,"errors":errors[:5]}))
if __name__=="__main__":main()

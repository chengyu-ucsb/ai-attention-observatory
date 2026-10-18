"""Add source-hosted original figures only when figure URLs AND reuse rights verify.

Europe PMC JATS graphics expose file names, not an automatic website-safe URL.
This job validates the NCBI-hosted image via HTTP HEAD before publication.
Captions suggesting a third-party image are never republished.
No images are scraped from sites with ambiguous reuse rights.
"""
import datetime,json,os,pathlib,re,urllib.parse,urllib.request,xml.etree.ElementTree as ET,time
from enrich import permitted
ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/"data/library.json"
ID=re.compile(r"PMC\d+$")
CREDIT=re.compile(r"(?:reproduced|adapted|permission|credit(?:s)?\s*:|copyright|©|all rights reserved)",re.I)
XLINK="{http://www.w3.org/1999/xlink}href"
def req(url,method="GET"):
 with urllib.request.urlopen(urllib.request.Request(url,method=method,headers={"User-Agent":"AI-Attention-Observatory/3.1 (fangcu@ucmail.uc.edu)"}),timeout=12) as r:
  if method=="HEAD":return r.headers.get("Content-Type","")
  return r.read(2800000)
def url_for(pmcid,filename):
 name=filename.strip().split("/")[-1]
 if not name or name in (".","..") or ".." in name or not re.fullmatch(r"[\w.()+\- ]{2,140}",name):return ""
 return "https://pmc.ncbi.nlm.nih.gov/articles/"+pmcid+"/bin/"+urllib.parse.quote(name,safe=".-_()+")
def run():
 data=json.loads(DATA.read_text());budget=int(os.getenv("FIGURE_VERIFY_LIMIT","5"))
 tries=0;found=0;errors=[]
 for r in data:
  if tries>=budget:break
  analysis=r.get("analysis") or {}
  figs=analysis.get("figures") or []
  if not figs or "Europe PMC" not in analysis.get("provenance",""):continue
  if r.get("figure_checked"):continue
  uri=analysis.get("fulltext_url","")
  pmcid=uri.rstrip("/").rsplit("/",1)[-1]
  if not ID.fullmatch(pmcid):continue
  tries+=1
  r["figure_checked"]=datetime.date.today().isoformat()
  try:
   root=ET.fromstring(req("https://www.ebi.ac.uk/europepmc/webservices/rest/"+pmcid+"/fullTextXML"))
   licenses=[" ".join(z.itertext()).lower() for z in root.findall(".//license")]
   if not permitted(licenses):continue
   candidates=root.findall(".//fig")
   for figure,source in zip(figs[:3],candidates[:3]):
    caption=figure.get("caption","")
    if CREDIT.search(caption):continue
    graphic=source.find(".//graphic")
    if graphic is None:continue
    name=graphic.get(XLINK) or ""
    u=url_for(pmcid,name)
    if not u:continue
    try:
     mime=req(u,"HEAD").split(";")[0].strip().lower()
     if mime in ("image/jpeg","image/png","image/webp","image/gif"):
      figure["image_url"]=u
      figure["attribution"]=r.get("title","")+" · "+(figure.get("label") or "Figure")
      figure["reuse_checked"]="Open-access parent paper (permissive license); inspect source caption for exceptions"
      found+=1
    except Exception as e:errors.append(pmcid+" "+str(e)[:65])
  except Exception as e:errors.append(pmcid+": "+str(e)[:100])
  time.sleep(.2)
 DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"figure_articles_checked":tries,"figure_images_verified":found,"errors":errors[:8]}))
if __name__=="__main__":run()

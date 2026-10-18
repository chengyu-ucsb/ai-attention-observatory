"""Validate reusable original figure media via PMC's August-2026 AWS dataset.

Never infer that a valid article page means an image is directly embeddable.
Verify parent and dataset licenses and the actual image MIME type/URL. Only
publish HTTPS S3 image links that return image content. Per-image rights notices
in captions override article-wide permissions.
"""
import datetime,json,os,pathlib,re,time,urllib.parse,urllib.request,urllib.error,xml.etree.ElementTree as ET
from enrich import permitted
ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/"data/library.json"
ID=re.compile(r"PMC\d+$")
CREDIT=re.compile(r"(?:reproduced|adapted|permission|credit(?:s)?\s*:|copyright|©|all rights reserved)",re.I)
XLINK="{http://www.w3.org/1999/xlink}href"
BASE="https://pmc-oa-opendata.s3.amazonaws.com"
LICENSABLE={"CC BY","CC BY-SA","CC0"}
MIME={"image/jpeg","image/png","image/webp","image/gif"}
def req(url,method="GET"):
 with urllib.request.urlopen(urllib.request.Request(url,method=method,headers={"User-Agent":"AIAttentionObservatory/3.2 (contact: fangcu@ucmail.uc.edu)"}),timeout=12) as r:
  if method=="HEAD":return r.headers
  return r.read(3500000)
def url_for(pmcid,filename):
 # Old PMC path retained for regression/reference; no longer used to embed.
 name=(filename or "").strip().split("/")[-1]
 if not name or name in (".","..") or ".." in name or not re.fullmatch(r"[\w.()+\- ]{2,140}",name):return ""
 return "https://pmc.ncbi.nlm.nih.gov/articles/"+pmcid+"/bin/"+urllib.parse.quote(name,safe=".-_()+")
def safe_filename(filename):
 raw=(filename or "").strip()
 if "/" in raw or "\\" in raw or ".." in raw:return ""
 return raw if raw and raw not in (".","..") and re.fullmatch(r"[\w.()+\- ]{2,140}",raw) else ""
def s3_candidates(pmcid,version,filename):
 name=safe_filename(filename)
 if not ID.fullmatch(pmcid) or not name or version not in (1,2,3):return []
 prefix=BASE+"/"+pmcid+"."+str(version)+"/"
 if re.search(r"\.(jpg|jpeg|png|webp|gif)$",name,re.I):
  variants=[name]
 elif "." in name and re.search(r"\.(tif|tiff|svg|eps)$",name,re.I):
  return []  # Do not transform an unsupported source image file.
 else:variants=[name+"."+ext for ext in ("jpg","png","jpeg","webp","gif")]
 return [prefix+urllib.parse.quote(v,safe=".-_()+") for v in variants]
def licensed_s3_version(pmcid):
 for version in (1,2,3):
  meta_url=BASE+"/"+pmcid+"."+str(version)+"/"+pmcid+"."+str(version)+".json"
  try:
   data=json.loads(req(meta_url))
  except (urllib.error.URLError,urllib.error.HTTPError,ValueError,TimeoutError):
   continue
  if data.get("pmcid")!=pmcid:continue
  license_name=(data.get("license_code") or "").upper().replace("-"," ").strip()
  if license_name in ("CC BY","CC BY SA","CC0") and str(data.get("is_pmc_openaccess","")).lower() in ("yes","true","1","y"):
   return version,license_name
 return None,None
def image_valid(url):
 try:
  headers=req(url,"HEAD")
  mime=(headers.get("Content-Type") or "").split(";")[0].strip().lower()
  content_length=headers.get("Content-Length")
  return mime in MIME and (not content_length or 0<int(content_length)<8_000_000)
 except (urllib.error.URLError,urllib.error.HTTPError,ValueError,TimeoutError):
  return False
def run():
 rows=json.loads(DATA.read_text());budget=int(os.getenv("FIGURE_VERIFY_LIMIT","5"))
 attempts=0;found=0;errors=[];deferred=0
 today=datetime.date.today()
 for paper in rows:
  if attempts>=budget:break
  analysis=paper.get("analysis") or {}
  if not analysis.get("figures") or "Europe PMC" not in analysis.get("provenance",""):continue
  checked=paper.get("figure_checked")
  if paper.get("figure_verification_method")=="pmc_aws_2026" and checked:
   try:
    if (today-datetime.date.fromisoformat(checked)).days<21:deferred+=1;continue
   except ValueError:pass
  source_url=analysis.get("fulltext_url","")
  pmcid=source_url.rstrip("/").split("/")[-1]
  if not ID.fullmatch(pmcid):continue
  attempts+=1;paper["figure_checked"]=today.isoformat();paper["figure_verification_method"]="pmc_aws_2026"
  try:
   xml=req("https://www.ebi.ac.uk/europepmc/webservices/rest/"+pmcid+"/fullTextXML")
   root=ET.fromstring(xml)
   licenses=[" ".join(el.itertext()).lower() for el in root.findall(".//license")]
   if not permitted(licenses):continue
   version,license_name=licensed_s3_version(pmcid)
   if version is None:continue
   for fig,source in zip(analysis["figures"][:3],root.findall(".//fig")[:3]):
    if CREDIT.search(fig.get("caption","")):continue
    graphic=source.find(".//graphic")
    if graphic is None:continue
    name=graphic.get(XLINK) or ""
    for candidate in s3_candidates(pmcid,version,name):
     if not image_valid(candidate):continue
     fig["image_url"]=candidate
     fig["attribution"]=paper.get("title","")+" · "+fig.get("label","Figure")
     fig["reuse_checked"]="PMC AWS media: "+license_name+"; article's caption screened for exceptions"
     found+=1;break
  except (urllib.error.URLError,urllib.error.HTTPError,ValueError,ET.ParseError,TimeoutError) as err:
   errors.append(pmcid+": "+str(err)[:110])
  time.sleep(.15)
 DATA.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"figure_articles_checked":attempts,"figure_images_verified":found,"deferred_recent_checks":deferred,"errors":errors[:6]}))
if __name__=="__main__":run()

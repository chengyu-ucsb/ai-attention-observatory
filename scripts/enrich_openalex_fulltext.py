"""Optional open-licensed paper-text enrichment via the OpenAlex content API.

Never puts PDFs or article XML into the public repository. Eligible sources:
OpenAlex records with content_urls.grobid_xml and an explicitly permissive license.
Requires OPENALEX_API_KEY. Any copyright uncertainty => do not extract.
"""
import datetime, json, os, pathlib, re, time
import urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/"data/library.json"
TODAY=datetime.date.today().isoformat()
ALLOW={"cc-by","cc-by-sa","cc0","public-domain"}
RELEVANT=re.compile(r"(?:attention|focus|cognit|think|distract|interrupt|offload|self.regulat|memory|metacognit|task.switch|ai literacy)",re.I)
SECTION_KEYS={
    "methods":("method","material","procedure","design","data collection","analysis approach","participants"),
    "results":("results","findings"),
    "discussion":("discussion","conclusion"),
    "limitations":("limitation","strengths and limitations"),
}
def get(url,key):
    url=url+("&" if "?" in url else "?")+urllib.parse.urlencode({"api_key":key})
    req=urllib.request.Request(url,headers={"User-Agent":"AI-Attention-Observatory/2.1 (fangcu@ucmail.uc.edu)","Accept":"application/xml,application/json"})
    with urllib.request.urlopen(req,timeout=22) as response:return response.read(5_000_000)
def local(tag):return tag.split("}")[-1].lower()
def content(el):return " ".join(" ".join(el.itertext()).split())
def extract(root):
    result={}
    # GROBID may contain <tei> or <TEI>, plus varying XML namespaces.
    for div in root.iter():
        if local(div.tag)!="div":continue
        head=next((content(x).lower() for x in div if local(x.tag)=="head"),"")
        if not head:continue
        section=next((k for k,words in SECTION_KEYS.items() if any(w in head for w in words)),None)
        if not section or result.get(section):continue
        paras=[content(el) for el in div.iter() if local(el.tag)=="p"]
        prose=" ".join(p for p in paras if len(p)>40)
        if prose:
            result[section]=prose[:950].rsplit(" ",1)[0]+"…" if len(prose)>950 else prose
    return result
def main():
    key=os.getenv("OPENALEX_API_KEY","").strip()
    if not key:
        print("OpenAlex full-text enrichment skipped: OPENALEX_API_KEY is not set. Europe PMC remains active.")
        return
    records=json.loads(DATA.read_text())
    eligible=[r for r in records if r.get("kind")=="scholarly" and r.get("doi")
              and not r.get("analysis") and
              (not r.get("oa_grobid_checked") or (datetime.date.fromisoformat(TODAY)-datetime.date.fromisoformat(r["oa_grobid_checked"])).days>=30)]
    # Match the observatory's focus first rather than arbitrarily checking unrelated papers.
    def priority(r):
        title=r.get("title") or ""
        title_focus=bool(RELEVANT.search(title))
        adjacent=r.get("relation")=="Adjacent digital-attention evidence"
        has_oa=bool(r.get("open_access_url"))
        return (-int(title_focus),-int(not adjacent),-int(has_oa),r.get("oa_grobid_checked") or "",r.get("published") or "")
    eligible.sort(key=priority)
    limit=int(os.getenv("OPENALEX_FULLTEXT_LIMIT","35"));complete=0;attempts=0;warnings=[];skipped={"no_licensed_location":0,"no_grobid_xml":0,"missing_sections":0}
    for r in eligible:
        if attempts>=limit:break
        attempts+=1;r["oa_grobid_checked"]=TODAY
        doi=urllib.parse.quote("https://doi.org/"+r["doi"],safe=":")
        try:
            work=json.loads(get("https://api.openalex.org/works/"+doi,key))
            oa=work.get("best_oa_location") or {}
            href=oa.get("landing_page_url") or oa.get("pdf_url")
            if href and href.startswith("https://"):r["open_access_url"]=href
            # OpenAlex's 'best' location is not necessarily its openly licensed one.
            locations=[oa]+(work.get("locations") or [])
            licensed=next((loc for loc in locations if (loc.get("license") or "").lower() in ALLOW),None)
            if not licensed:
                skipped["no_licensed_location"]+=1
                continue
            license_str=(licensed.get("license") or "").lower()
            lic_href=licensed.get("landing_page_url") or licensed.get("pdf_url") or href
            urls=work.get("content_urls") or {}
            xml_url=urls.get("grobid_xml","")
            if not xml_url.startswith("https://content.openalex.org/works/"):
                skipped["no_grobid_xml"]+=1
                continue
            root=ET.fromstring(get(xml_url,key))
            secs=extract(root)
            if not (secs.get("results") or secs.get("discussion")):
                skipped["missing_sections"]+=1
                continue
            r["analysis"]={
                "provenance":"OpenAlex open-access GROBID XML (machine-parsed, may contain errors)",
                "license":license_str,
                "license_url":licensed.get("license_id") or "",
                "methods":secs.get("methods",""),"results":secs.get("results",""),
                "discussion":secs.get("discussion",""),"limitations":secs.get("limitations",""),
                "figures":[],"fulltext_url":lic_href or work.get("doi",""),
                "key_idea":(secs.get("discussion") or secs.get("results") or "")[:280],
                "extraction_date":TODAY,
            }
            complete+=1
        except (ValueError,ET.ParseError,urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as exc:
            warnings.append(r.get("doi","")+": "+str(exc)[:100])
        time.sleep(.15)
    DATA.write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"attempted":attempts,"extracted_fulltext":complete,"skipped":skipped,"warnings":warnings[:8]},indent=2))
if __name__=="__main__":main()

"""Check publicly readable Wiley/BJET HTML independently of PDF licenses.

A CC BY-NC-ND or similar open-access article may be readable yet unsuitable
for automated republication of section extracts. This step records ACCESS
only. It never stores raw HTML, sentences, PDF bytes or copied sections.
"""
from __future__ import annotations
import datetime as dt
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
LIB=ROOT/"data/library.json"
DOMAINS={"bera-journals.onlinelibrary.wiley.com","onlinelibrary.wiley.com"}
DOI=re.compile(r"^10\.1111/[a-z0-9._-]+$",re.I)

class Headings(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tag=None;self.bits=[];self.headings=[]
    def handle_starttag(self,tag,attrs):
        if tag in ("h2","h3","h4"):self.tag=tag;self.bits=[]
    def handle_data(self,data):
        if self.tag:self.bits.append(data)
    def handle_endtag(self,tag):
        if tag==self.tag:
            self.headings.append(" ".join(" ".join(self.bits).lower().split()))
            self.tag=None;self.bits=[]

def url_for(record):
    doi=str(record.get("doi") or "").lower()
    if not DOI.fullmatch(doi):return ""
    host="bera-journals.onlinelibrary.wiley.com" if doi.startswith("10.1111/bjet.") else "onlinelibrary.wiley.com"
    return "https://"+host+"/doi/"+urllib.parse.quote(doi,safe="/")

def inspect_html(page,doi):
    # Explicit DOI plus publisher's open-access marker and results/discussion headings.
    plain=page.lower()
    if doi.lower() not in plain:return "doi_mismatch"
    if not re.search(r"open\s*access",plain,re.I):return "oa_not_confirmed"
    parser=Headings()
    parser.feed(page)
    headers=parser.headings
    if not any(re.match(r"results?\b",h) for h in headers) or not any(re.match(r"discussion\b",h) for h in headers):
        return "full_article_not_detected"
    return "public_html_verified"

def request(url):
    req=urllib.request.Request(url,headers={"User-Agent":"AttentionAIObservatory/4.3 (contact: fangcu@ucmail.uc.edu)","Accept":"text/html"})
    with urllib.request.urlopen(req,timeout=19) as res:
        host=(urllib.parse.urlparse(res.geturl()).hostname or "").lower()
        if host not in DOMAINS:raise ValueError("Unapproved publisher redirect")
        payload=res.read(5_000_001)
        if len(payload)>5_000_000:raise ValueError("HTML exceeds read limit")
        return payload.decode("utf-8","replace")

def eligible(r,today):
    if r.get("kind")!="scholarly" or r.get("analysis") or not url_for(r):return False
    old=r.get("wiley_html_attempt") or {}
    if old.get("version")!=1:return True
    try:return dt.date.fromisoformat(old.get("next_at",""))<=today
    except ValueError:return True

def run(path=LIB,today=None,fetch=request,limit=None):
    today=today or dt.date.today()
    limit=max(1,min(12,int(limit or os.getenv("WILEY_HTML_LIMIT","8"))))
    path=Path(path)
    records=json.loads(path.read_text(encoding="utf-8"))
    due=[r for r in records if eligible(r,today)]
    due.sort(key=lambda r:(0 if str(r.get("doi") or "").startswith("10.1111/bjet.") else 1,
                            -int(str(r.get("published") or "0000")[:4]) if str(r.get("published") or "")[:4].isdigit() else 0))
    stats={"wiley_due":len(due),"wiley_attempted":0,"public_html_verified":0,
           "publisher_blocked":0,"no_full_article":0}
    for row in due[:limit]:
        url=url_for(row);status="temporary_error";delay=3
        try:
            page=fetch(url)
            status=inspect_html(page,row["doi"])
            delay=90 if status=="public_html_verified" else 21
            if status=="public_html_verified":stats["public_html_verified"]+=1
            else:stats["no_full_article"]+=1
        except urllib.error.HTTPError as err:
            status="publisher_denied_http_"+str(err.code) if err.code in (401,403,404,429) else "temporary_error"
            delay=30 if err.code in (401,403,404,429) else 3
            if err.code in (401,403,404,429):stats["publisher_blocked"]+=1
        except (urllib.error.URLError,TimeoutError,ValueError):
            status="temporary_error"
        previous=row.get("wiley_html_attempt") or {}
        row["wiley_html_attempt"]={"version":1,"status":status,"checked_at":today.isoformat(),
                                   "next_at":(today+dt.timedelta(days=delay)).isoformat(),
                                   "attempts":previous.get("attempts",0)+1,
                                   "publisher_url":url}
        stats["wiley_attempted"]+=1
        time.sleep(.25)
    path.write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(stats))
    return stats

if __name__=="__main__":run()

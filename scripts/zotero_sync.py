"""Private, read-only Zotero access for the AI & Attention Observatory.

Only a specifically named Zotero collection is accessed. The API key stays in
GitHub Actions secrets (never a URL); no private Zotero metadata, attachments,
indexed full text, item keys, authors or titles are committed or printed.

On GitHub-hosted runners indexed full text is only checked in memory.
It is NOT published: institutional access is not permission to redistribute
subscribed PDFs or lengthy full-text extracts in a public repository.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE="https://api.zotero.org"
DEFAULT_COLLECTION="AI & Attention Observatory"
MAX_ITEMS=800
MAX_MATCH_CHECKS=25
DOI_RE=re.compile(r"10\.\d{4,9}/[^\s\]\[<>\"']+",re.I)


def normalized_doi(value):
    value=str(value or "").strip()
    value=re.sub(r"^https?://(?:dx\.)?doi\.org/","",value,flags=re.I)
    value=re.sub(r"^doi:\s*","",value,flags=re.I)
    match=DOI_RE.search(value)
    return match.group(0).rstrip(".,;)]}").lower() if match else ""


@dataclass
class ZoteroAPI:
    key: str
    timeout: int=20

    def request(self,path,params=None):
        """Authenticated GET restricted to Zotero's API; never log the secret."""
        if not path.startswith("/") or path.startswith("//") or ".." in path:
            raise ValueError("Invalid Zotero endpoint")
        url=BASE+path
        if params:url+="?"+urllib.parse.urlencode(params)
        req=urllib.request.Request(url,headers={
            "Zotero-API-Key":self.key,
            "Zotero-API-Version":"3",
            "Accept":"application/json",
            "User-Agent":"AIAttentionObservatory/4.2 (read-only Zotero integration)"
        })
        with urllib.request.urlopen(req,timeout=self.timeout) as response:
            return json.loads(response.read(8_000_000))

    def pages(self,path,limit=MAX_ITEMS):
        result=[]
        for offset in range(0,limit,100):
            page=self.request(path,{"format":"json","limit":min(100,limit-offset),"start":offset})
            if not isinstance(page,list):raise ValueError("Unexpected Zotero list response")
            result.extend(page)
            if len(page)<min(100,limit-offset):break
        return result


def collections_scope(collections,preferred):
    """No fallback to the complete personal library if the name is absent."""
    wanted=preferred.strip().casefold()
    roots=[c for c in collections if str((c.get("data") or {}).get("name") or "").strip().casefold()==wanted]
    if len(roots)!=1:return None
    children={roots[0].get("key")}
    changed=True
    while changed:
        count=len(children)
        children.update(c.get("key") for c in collections if (c.get("data") or {}).get("parentCollection") in children)
        changed=len(children)!=count
    return sorted(key for key in children if key and re.fullmatch("[A-Z0-9]{8}",key))


def metadata_in_collection(client,user_id,collection_keys):
    unique={}
    for key in collection_keys:
        path=f"/users/{user_id}/collections/{key}/items/top"
        for item in client.pages(path):
            row=item.get("data") or {}
            if row.get("itemType") in ("attachment","note","annotation"):continue
            k=item.get("key") or row.get("key")
            if k and re.fullmatch(r"[A-Z0-9]{8}",k):unique[k]=row
            if len(unique)>=MAX_ITEMS:break
        if len(unique)>=MAX_ITEMS:break
    return unique


def public_dois(path=ROOT/"data/library.json"):
    # Metadata already in the public repository; Zotero records remain private.
    source=json.loads(Path(path).read_text(encoding="utf-8"))
    return {doi for record in source if record.get("kind")=="scholarly"
            if (doi:=normalized_doi(record.get("doi")))}


def fulltext_check(client,user_id,keys,max_checks=MAX_MATCH_CHECKS):
    """Read indexed attachment text transiently, not download or persist PDFs."""
    scanned=0
    available=0
    for key in keys[:max_checks]:
        children=client.pages(f"/users/{user_id}/items/{key}/children",limit=100)
        scanned+=1
        for item in children:
            data=item.get("data") or {}
            if data.get("itemType")!="attachment":continue
            if data.get("contentType") not in ("application/pdf","text/html","text/plain"):continue
            attachment_key=item.get("key")
            if not attachment_key or not re.fullmatch(r"[A-Z0-9]{8}",attachment_key):continue
            try:
                body=client.request(f"/users/{user_id}/items/{attachment_key}/fulltext")
            except urllib.error.HTTPError as exc:
                if exc.code in (403,404):continue
                raise
            if len(str(body.get("content") or ""))>=500:
                available+=1
                break
    return scanned,available


def run(client=None,library_path=None):
    key=os.environ.get("ZOTERO_API_KEY","").strip()
    if client is None and not key:
        return {"status":"secret_missing"}
    client=client or ZoteroAPI(key)
    try:
        identity=client.request("/keys/current")
    except urllib.error.HTTPError as exc:
        if exc.code in (401,403):return {"status":"key_invalid_or_unpermitted"}
        if exc.code==429:return {"status":"zotero_rate_limited"}
        return {"status":"zotero_unavailable"}
    except (urllib.error.URLError,TimeoutError,ValueError,TypeError):
        return {"status":"zotero_unavailable"}
    access=(identity.get("access") or {}).get("user") or {}
    user=identity.get("userID")
    if not user or not str(user).isdigit() or access.get("library") is not True:
        return {"status":"library_permission_missing"}
    try:
        all_collections=client.pages(f"/users/{int(user)}/collections",limit=1000)
        selected=collections_scope(all_collections,os.environ.get("ZOTERO_COLLECTION",DEFAULT_COLLECTION))
        if selected is None:return {"status":"collection_missing_or_ambiguous"}
        if not selected:return {"status":"collection_key_invalid"}
        items=metadata_in_collection(client,int(user),selected)
        if not items:return {"status":"collection_empty"}
        public=public_dois(library_path or ROOT/"data/library.json")
        matched=[k for k,row in items.items() if normalized_doi(row.get("DOI")) in public]
        if not matched:return {"status":"connected_no_doi_overlap"}
        checked,available=fulltext_check(client,int(user),matched)
        return {"status":"connected_indexed_fulltext_available" if available else "connected_no_synced_fulltext",
                "matched_some":bool(matched),"indexed_fulltext_available":bool(available),
                "matches_checked":bool(checked)}
    except urllib.error.HTTPError as exc:
        if exc.code==429:return {"status":"zotero_rate_limited"}
        if exc.code in (401,403):return {"status":"library_permission_missing"}
        return {"status":"zotero_unavailable"}
    except (urllib.error.URLError,TimeoutError,ValueError,KeyError,TypeError):
        return {"status":"zotero_unavailable"}


if __name__=="__main__":
    result=run()
    # Public repository: NEVER print bibliographic records, account IDs,
    # collection names, item keys, passages, token or authentication URLs.
    print("Zotero integration status: "+result["status"])
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as out:
            out.write("### Zotero (private, read-only)\n\n")
            out.write("- Status: "+result["status"]+"\n")
            out.write("- No private article text or collection contents are committed.\n")
    if result["status"] in ("secret_missing","key_invalid_or_unpermitted","library_permission_missing"):
        sys.exit(2)

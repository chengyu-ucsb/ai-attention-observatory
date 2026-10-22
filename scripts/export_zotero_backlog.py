"""Export PUBLIC Observatory citations lacking extracted full text to Zotero RIS.

Public bibliography only. Never reads Zotero, private records, or institutional
PDFs. Zotero can import this file, then use its own Find Available PDFs feature
under the user's authorized institutional access.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
LIB=ROOT/"data/public-library.json"
OUT=ROOT/"exports/zotero-fulltext-backlog.ris"
DOI=re.compile(r"^10\.\d{4,9}/\S+$",re.I)

def field(value,limit=320):
 value=" ".join(str(value or "").split())
 return value[:limit].replace("\r"," ").replace("\n"," ").strip()
def generate(source,output):
 entries=[]
 seen=set()
 for item in json.loads(Path(source).read_text(encoding="utf-8")):
  if item.get("kind")!="scholarly":continue
  if (item.get("reading") or {}).get("level")=="full_text":continue
  doi=field(item.get("doi"),200).lower()
  title=field(item.get("title"))
  if not doi or not DOI.fullmatch(doi) or not title or doi in seen:continue
  seen.add(doi)
  block=["TY  - JOUR","TI  - "+title,"DO  - "+doi]
  authors=item.get("authors") or []
  if isinstance(authors,list):
   for author in authors[:12]:
    name=field(author if isinstance(author,str) else author.get("name"),160)
    if name:block.append("AU  - "+name)
  year=field(item.get("published"))[:4]
  if re.fullmatch("[0-9]{4}",year):block.append("PY  - "+year)
  journal=field(item.get("venue"),230)
  if journal:block.append("JO  - "+journal)
  url=field(item.get("url"),380)
  if url.startswith("https://"):block.append("UR  - "+url)
  block.append("ER  -")
  entries.append("\n".join(block))
 Path(output).parent.mkdir(parents=True,exist_ok=True)
 Path(output).write_text("\n\n".join(entries)+"\n",encoding="utf-8")
 print("Public Zotero recovery bibliography: "+str(len(entries))+" DOI-based entries")
 return len(entries)
if __name__=="__main__":
 generate(LIB,OUT)

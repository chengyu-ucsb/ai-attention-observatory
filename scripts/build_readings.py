"""Prepare source-specific reading cards from abstracts and licensed OA sections.

Extractive, provenance-labelled notes only. No generated numerical results, fabricated
methods, or LLM inference. Missing sections stay missing instead of generic prompts.
"""
import json,pathlib,re,html
ROOT=pathlib.Path(__file__).resolve().parents[1]
LIB=ROOT/"data/library.json"
STOP=("abstract unavailable","bibliographic metadata only","no abstract", "abstract not available")
METHOD=re.compile(r"\b(?:survey|interview|experiment|experimental|trial|randomi[sz]|sample|participants|students|respondents|researchers collected|data were|data was|we collected|recruited|cross.sectional|longitudinal|meta.analysis|systematic review|literature review|qualitative|quantitative|mixed.methods|thematic analysis|regression|structural equation|focus groups|we tested|models? were|analy[sz]ed|using data)\b",re.I)
RESULT=re.compile(r"\b(?:results? (?:show|suggest|indicat|reveal|demonstrat|found|support)|we (?:found|show|observed)|findings? (?:show|suggest|indicat|reveal|demonstrat)|associated with|positively (?:related|associated)|negatively (?:related|associated)|significantly|outperform|increased|decreased|mediated|moderated|higher than|lower than|effect size|was correlated|were correlated|our analys[ie]s)\b",re.I)
AIM=re.compile(r"\b(?:aims? to|investigat|examines?|explores?|seeks? to|the purpose|we study|this (?:study|paper|article|research)|designed to|evaluate)\b",re.I)
LIMIT=re.compile(r"\b(?:limitation|caution|however|cannot establish|not causal|cross.sectional|self.report|generalizab|future research|small sample|potential bias)\b",re.I)
SAMPLE=re.compile(r"\b(?:n\s*=\s*(\d{2,6})|(\d{2,6})\s+(?:participants|students|respondents|workers|people|adults|adolescents|teachers|patients))\b",re.I)

def clean(s):return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s or ""))).strip()
def sentences(text):
    s=clean(text)
    # Do not split decimals or abbreviations into phantom findings.
    s=re.sub(r"\s+"," ",s)
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-Z“(])",s) if len(p.strip())>=35]

def excerpt_from(sentences,rx,limit=400,exclude=None):
    matches=[]
    for p in sentences:
        if exclude and p in exclude:continue
        if rx.search(p):matches.append(p)
    if not matches:return ""
    joined=" ".join(matches[:2])
    if len(joined)>limit:
        joined=joined[:limit].rsplit(" ",1)[0].rstrip(" ,;")+ "…"
    return joined

def first_two(parts,limit=420):
    t=" ".join(parts[:2])
    if len(t)>limit:return t[:limit].rsplit(" ",1)[0]+"…"
    return t

def make_note(r):
    src=clean(r.get("abstract_text"))
    if len(src)<90 and r.get("preview") and not any(w in r["preview"].lower() for w in STOP):
        src=clean(r["preview"])
    full=r.get("analysis") or {}
    licensed=bool(full.get("fulltext_url"))
    if licensed:
        approach=clean(full.get("methods"))[:650]
        # Discussion interprets findings rather than listing validity statistics in first Results subsection.
        results=clean(full.get("discussion") or full.get("results"))[:780]
        caveat=clean(full.get("limitations"))[:600]
        abstract=src or clean(r.get("preview"))
        introduction=first_two(sentences(abstract),410) if abstract else ""
        kind="Licensed full-text excerpts"
        provider=full.get("provenance") or "Europe PMC licensed full text"
    elif len(src)>=90:
        parts=sentences(src)
        introduction=excerpt_from(parts,AIM,380) or first_two(parts,380)
        # Select only sentences explicitly referring to study procedures/results.
        used={introduction}
        approach=excerpt_from(parts,METHOD,450)
        results=excerpt_from(parts,RESULT,520)
        caveat=excerpt_from(parts,LIMIT,360,exclude={approach,results})
        if approach and results and approach==results:approach=""
        kind="Abstract-derived research notes"
        provider=r.get("abstract_source") or r.get("source") or "Bibliographic abstract"
    elif r.get("curated") and r.get("preview") and not any(w in r["preview"].lower() for w in STOP):
        introduction=clean(r["preview"])[:420]
        approach=results=caveat=""
        kind="Curated introductory synopsis"
        provider="Initial editorial reference list (not full-text verified)"
    else:
        return {"level":"citation_only","provenance":"Citation only","overview":"","methods":"","findings":"","limitations":"","sample":"","notice":"No accessible abstract or licensed text has been indexed for this record."}
    # Samples appear only if literally stated in the source text, never inferred.
    sm=SAMPLE.search(src or approach)
    sample=sm.group(1) or sm.group(2) if sm else ""
    if sample and not METHOD.search(approach):sample=""  # Require an actual methodological context.
    has_finding=bool(results)
    return {
        "level":"full_text" if licensed else "abstract" if len(src)>=90 else "curated",
        "provenance":provider,
        "overview":introduction,
        "methods":approach,
        "findings":results,
        "limitations":caveat,
        "sample":sample,
        "notice":("Excerpts from licensed article sections; automatically selected, not independently reviewed." if licensed else
                  "Structured highlights selected from the source abstract; not an appraisal of the full paper." if len(src)>=90 else
                  "Initial topic synopsis, not a verified paper-level analysis."),
        "reported_findings":has_finding
    }

def main():
    records=json.loads(LIB.read_text())
    counts={}
    for r in records:
        r["reading"]=make_note(r)
        k=r["reading"]["level"];counts[k]=counts.get(k,0)+1
    LIB.write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n")
    print("Reading cards:",counts)
if __name__=="__main__":main()

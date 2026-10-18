"""Condense extracted research sections into readable, provenance-labelled source notes.

Does NOT call an LLM, infer a result, or claim an automated digest is independently
reviewed. Curated items are independently worded using specific indexed source
passages; other papers receive a cautious source-derived sentence condensation.
Original extracts remain linked in the reading object for verification.
"""
from __future__ import annotations
import re,html
CURATED={
 "10.3389/feduc.2026.1861548":{
  "idea":"AI literacy may support monitoring without preventing dependence on AI outputs.",
  "approach":"The authors surveyed academic learners online and used cluster analysis to identify patterns of AI use and cognitive engagement.",
  "finding":"Three learner profiles emerged: engaged and literate, uncritical and reliant, and skeptical but minimally engaged. Critical-ethical awareness was associated with both checking outputs and cognitive shortcuts.",
  "interpretation":"The authors describe a possible illusion of independence: feeling autonomous while depending on AI without sufficiently checking its outputs.",
  "limitation":"The design uses self-reports collected at one point in time; it cannot establish the direction of the relationships.",
  "tags":["AI literacy","Output monitoring","Cognitive reliance"]
 },
 "10.21203/rs.3.rs-10373880/v1":{
  "idea":"Cognitive offloading is shaped by the learning environment, not simply AI adoption.",
  "approach":"A conceptual and critical analysis of AI-mediated higher education, especially low-resource settings; not an empirical intervention study.",
  "finding":"",
  "interpretation":"The authors argue that offloading depends on how cognitive practices, teaching arrangements and institutional conditions interact.",
  "limitation":"",
  "tags":["Cognitive offloading","Pedagogy","Institutional context"]
 },
 "10.3389/fpsyg.2026.1920947":{
  "idea":"Doctoral students' use of AI can involve both offloading work and rebuilding their understanding.",
  "approach":"A qualitative grounded-theory study examining the process of GenAI-mediated doctoral learning.",
  "finding":"The authors' analysis organized the empirical material into five main categories derived from 19 initial categories.",
  "interpretation":"The proposed framework treats AI-mediated offloading and metacognitive calibration as a process rather than a fixed consequence of tool use.",
  "limitation":"The study concerns doctoral learners in Chinese research universities; findings may not generalize to other institutional settings.",
  "tags":["Cognitive offloading","Metacognition","Doctoral learning"]
 }
}
HEAD=re.compile(r"(?:^|\s)(?:\d+(?:\.\d+)*\.?\s+)*(?:results?|discussion|methods?|materials and methods|conclusions?|limitations(?: and future research)?|introduction|abstract)\s*(?=(?:\d|[A-Z]))",re.I)
SEC=re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+){1,3}(?=[A-Za-z])")
CITATIONS=re.compile(r"\s*\(\s*(?:Table|Fig(?:ure)?|Section)\s+\d+[a-zA-Z]?\s*\)",re.I)
BRACKETS=re.compile(r"\s*\[(?:\d+[\s,;–-]*)+\]")
def clean(source):
 s=html.unescape(re.sub(r"<[^>]+>"," ",source or ""))
 s=re.sub(r"https?://\S+","",s)
 s=CITATIONS.sub("",s);s=BRACKETS.sub("",s)
 s=re.sub(r"\s+"," ",s).strip()
 s=re.sub(r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:Results|Discussion|Methods|Introduction|Abstract|Conclusion|Limitations)(?:\s+and\s+(?:future\s+research|directions))?(?:\s+\d+(?:\.\d+)*\.?)?(?:\s+[\w -]{0,50})?(?=\s+(?:The|This|These|We|Our|Data|Participants|In|First|To)\b)", "", s, flags=re.I).strip()
 for _ in range(3):
  new=SEC.sub("",s).strip()
  if new==s:break
  s=new
 return s
def sentence_list(text):
 s=clean(text)
 return [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-Z“])",s) if len(p.strip())>=35]
def condensed(text,role,maxlen=295):
 items=sentence_list(text)
 if not items:return ""
 if role=="finding":
  # Source parser often starts results with scale reliability, headers or tables.
  candidates=[x for x in items if re.search(r"associat|linked|predict|observ|group|found|suggest|indicat|identified|higher|lower|increase|decrease|effect|relationship|difference|categor|profile|participants",x,re.I)
              and not re.search(r"(?:table|model fit|Cronbach|discriminant validity|measurement model|factor analys|CFI\s*=|RMSEA\s*=)",x,re.I)]
  if not candidates:return "" # No substantive finding can be confidently identified.
  items=candidates
 elif role=="approach":
  p=[x for x in items if re.search("survey|interview|experiment|design|sample|participants|review|thematic|analysis|qualitative|quantitative",x,re.I)]
  if p:items=p
 elif role=="limitations":
  p=[x for x in items if re.search("limit|cannot|caution|self.report|cross.sectional|generaliz|sample|bias|underrepresent",x,re.I)]
  if p:items=p
 out=items[0]
 if len(out)>maxlen:
  # Finish at a clause when possible; never imply that the truncated passage is a complete direct quotation.
  clip=out[:maxlen]
  stop=max(clip.rfind(";"),clip.rfind(","),clip.rfind(" and "))
  out=(clip[:stop].strip() if stop>maxlen//2 else clip.rsplit(" ",1)[0])+"…"
 return out
def concept_tags(record):
 text=" ".join([record.get("title",""),(record.get("reading") or {}).get("overview",""),(record.get("reading") or {}).get("findings","")]).lower()
 clusters=[
  ("AI literacy",r"ai literacy|genai literacy"),("Critical thinking",r"critical thinking"),
  ("Cognitive offloading",r"cognitive offload|cognitive shortcut"),
  ("Attention",r"attention|distraction|focus"),("Metacognition",r"metacognit|self.regulat"),
  ("Learning",r"learning|academic|students"),("Wellbeing",r"wellbeing|well.being|stress"),
  ("Algorithmic design",r"algorithmic|interface|platform|notifications"),
  ("Social context",r"social|organiz|institution|context")
 ]
 tags=[label for label,pattern in clusters if re.search(pattern,text)]
 return tags[:3]
def annotate(record):
 r=record.get("reading") or {}
 base=dict(record);base["reading"]=dict(r)
 if record.get("kind")!="scholarly":
  notes=record.get("editorial_notes") or {}
  base["reading"]["digest"]={"idea":notes.get("argument") or condensed(r.get("overview"),"idea",230),
   "approach":"","finding":"","interpretation":notes.get("design_relevance") or "",
   "limitation":notes.get("caveat") or "","tags":concept_tags(record),"status":"editorial_or_publisher_synopsis"}
  return base
 curated=CURATED.get((record.get("doi") or "").lower())
 if curated and r.get("level")=="full_text":
  digest=dict(curated);digest["status"]="editorially_written_from_indexed_sections"
 else:
  digest={
   "idea":condensed(r.get("overview"),"idea",230),
   "approach":condensed(r.get("methods"),"approach",235),
   "finding":condensed(r.get("findings"),"finding",300),
   "interpretation":condensed(r.get("interpretation"),"interpretation",300),
   "limitation":condensed(r.get("limitations"),"limitations",260),
   "tags":concept_tags(record),
   "status":"automatically_condensed_source_text"
  }
 base["reading"]["digest"]=digest
 return base

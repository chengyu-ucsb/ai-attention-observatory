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
 },
 "10.3389/fpsyg.2026.1878629":{
  "idea":"The way people delegate tasks to AI matters more than treating all offloading as one behavior.",
  "approach":"A three-wave time-lagged survey compared dependent and autonomous AI offloading. Measures of cognitive functioning were self-reported.",
  "finding":"Dependent offloading was associated with ceding more cognitive authority and lower intrinsic motivation. Autonomous offloading was associated with a different pattern of agency and motivation.",
  "interpretation":"The authors argue that offloading can follow distinct pathways depending on how much cognitive agency users retain.",
  "limitation":"Time separation does not demonstrate causality. Cognitive functioning was measured by perceived capability, not performance-based tests.",
  "tags":["Dependent offloading","Autonomous offloading","Perceived capability"]
 },
 "10.3390/jintelligence14080182":{
  "idea":"AI-assisted work can raise questions about whether the result still feels like one's own.",
  "approach":"A cross-sectional survey of 239 preservice teachers in eastern China, recruited by convenience sampling.",
  "finding":"The reported model associated AI anxiety and impulsivity with GenAI dependency, and dependency with greater concern about losing ownership of teaching-design work.",
  "interpretation":"The authors propose that cognitive ownership matters when people delegate the design of educational materials.",
  "limitation":"Cross-sectional associations cannot establish the temporal order of dependency and ownership concern; the study was not an intervention.",
  "tags":["239 preservice teachers","Ownership concern","Cross-sectional"]
 },
 "10.3390/bs16071150":{
  "idea":"AI assistance can be understood through competing patterns of learner agency.",
  "approach":"A scoping review charted research concerning GenAI, learner agency and cognitive offloading in higher education.",
  "finding":"The review's final evidence base comprised 123 included studies. It identifies agency-supportive and agency-eroding patterns in the literature.",
  "interpretation":"The authors argue that a simple benefits-versus-risks account obscures differences in learning practices and conditions.",
  "limitation":"The review restricted its included literature by language, outlet type and publication window; its synthesis cannot establish causal effects.",
  "tags":["123 included studies","Scoping review","Learner agency"]
 },
 "10.2196/69533":{
  "idea":"Digital well-being tools must consider people's decision-making, not just screen-time control.",
  "approach":"A systematic research synthesis and conceptual model addressing human-centered AI for digital well-being.",
  "finding":"The review covers 240 publications between 2008 and 2024; the authors report 2 relevant publications in 2008 versus 43 in 2024.",
  "interpretation":"The authors propose a human-centered AI model of how system features relate to individual behavioral decisions and digital well-being.",
  "limitation":"The study's database and selection scope bounds its coverage; changing publication counts are not proof that a particular intervention works.",
  "tags":["240 publications","Digital well-being","Human-centered AI"]
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

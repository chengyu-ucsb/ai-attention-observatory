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
  "idea":"Knowing more about AI does not always mean relying on it less.",
  "explain":"AI literacy went hand in hand with closer checking of outputs, but also with taking cognitive shortcuts.",
  "approach":"An online survey of 848 academic learners, analyzed using regression and learner profiles.",
  "finding":"Three patterns emerged: engaged and literate, uncritical and reliant, and skeptical but minimally engaged.",
  "interpretation":"Feeling independent can coexist with trusting AI too easily. What matters is whether people keep evaluating its answers.",
  "limitation":"Self-reported behavior at one point in time cannot establish cause and effect.",
  "tags":["AI literacy","Output monitoring","Cognitive reliance"]
 },
 "10.21203/rs.3.rs-10373880/v1":{
  "idea":"Whether AI replaces thinking depends partly on how learning is organized.",
  "explain":"Teaching practices and institutional resources shape whether AI becomes a shortcut or a useful scaffold.",
  "approach":"A conceptual critique of AI-mediated higher education, particularly in low-resource settings.",
  "finding":"",
  "interpretation":"Attention to the learning environment matters as much as individual tool use.",
  "limitation":"This is an argument, not an empirical test of a learning intervention.",
  "tags":["Cognitive offloading","Pedagogy","Institutional context"]
 },
 "10.3389/fpsyg.2026.1920947":{
  "idea":"AI can make research easier to start without doing the deeper thinking for you.",
  "explain":"Doctoral learning involves moving from AI-generated starting points toward checking and rebuilding ideas.",
  "approach":"A grounded-theory study of AI-assisted doctoral research learning.",
  "finding":"The analysis organized 19 initial categories into five broader stages of AI-assisted learning.",
  "interpretation":"The key distinction is whether researchers still verify, reconstruct, and take responsibility for their arguments.",
  "limitation":"The study focuses on doctoral students at Chinese research universities; transfer to other settings is uncertain.",
  "tags":["Cognitive offloading","Metacognition","Doctoral learning"]
 },
 "10.3389/fpsyg.2026.1878629":{
  "idea":"Delegating work to AI is not the same as giving up control of your thinking.",
  "explain":"Using AI as a scaffold and depending on it to do the thinking showed different links to motivation and agency.",
  "approach":"A three-wave survey of 589 students and early-career knowledge workers.",
  "finding":"Dependent offloading was linked to lower intrinsic motivation; autonomous offloading showed more favorable associations.",
  "interpretation":"Two approaches can feel equally helpful right away, even when their longer-term self-reported outcomes differ.",
  "limitation":"The outcomes were self-reported perceptions, not measured gains or losses in cognitive ability. Causation is not established.",
  "tags":["Dependent offloading","Autonomous offloading","Perceived capability"]
 },
 "10.3390/jintelligence14080182":{
  "idea":"AI-assisted work can leave people wondering whether the work is still their own.",
  "explain":"Greater dependency on AI was linked to stronger concerns about ownership of teaching materials.",
  "approach":"A survey of 239 preservice teachers in eastern China.",
  "finding":"AI anxiety and impulsivity were associated with dependency; dependency was linked to concern about losing ownership of teaching-design work.",
  "interpretation":"The concern is not only about productivity, but about who retains responsibility for the ideas.",
  "limitation":"A cross-sectional convenience sample cannot show which factor came first.",
  "tags":["239 preservice teachers","Ownership concern","Cross-sectional"]
 },
 "10.3390/bs16071150":{
  "idea":"AI can support learner independence or weaken it, depending on how it is used.",
  "explain":"Across the literature, guided, reflective use looks different from uncritical reliance.",
  "approach":"A scoping review of 123 studies on AI, cognitive offloading, and agency in higher education.",
  "finding":"The review identified both agency-supportive and agency-eroding patterns in the existing literature.",
  "interpretation":"The synthesis suggests focusing on learning practices, rather than treating AI as simply good or bad.",
  "limitation":"The evidence varies widely and cannot be combined into a single causal effect. The search excluded some languages and publication types.",
  "tags":["123 included studies","Scoping review","Learner agency"]
 },
 "10.2196/69533":{
  "idea":"Better digital well-being tools must help with decisions, not just screen time.",
  "explain":"A human-centered approach asks how people respond to prompts, habits, and digital environments.",
  "approach":"A systematic synthesis of 240 publications on intelligent computing and digital well-being.",
  "finding":"The included literature grew from two publications in 2008 to 43 in 2024.",
  "interpretation":"A proposed design framework links system features, personal decisions, and well-being.",
  "limitation":"Publication growth does not show that a particular digital well-being intervention works.",
  "tags":["240 publications","Digital well-being","Human-centered AI"]
 },
 "10.58304/ijts.260930":{
  "idea":"AI literacy may matter most when students use it to solve problems, not just find answers.",
  "explain":"Better AI literacy was associated with critical thinking through AI-assisted problem-solving and reliance.",
  "approach":"A survey of 450 non-English-major undergraduates in northern China, followed by 20 interviews.",
  "finding":"AI literacy was positively linked to AI-assisted problem-solving. The model also found indirect associations with critical thinking.",
  "interpretation":"Active evaluation of AI responses may be more important than simply limiting reliance on the tool.",
  "limitation":"Survey associations and interviews do not prove that AI literacy improves critical thinking.",
  "tags":["450 survey respondents","20 interviews","AI literacy"]
 },
 "10.3389/fpsyg.2026.1930030":{
  "idea":"Stress and social-media time stood out as signals of academic difficulty.",
  "explain":"Digital interruptions may matter for attention, but this study did not examine generative AI.",
  "approach":"Two cross-sectional survey datasets covering 799 adolescents, analyzed using predictive models.",
  "finding":"Stress (0.384) and social-media duration (0.297) had the largest positive LASSO coefficients among the factors reported.",
  "interpretation":"Stress and digital habits may help identify adolescents at risk of academic difficulties.",
  "limitation":"The surveys were self-reported and cross-sectional. Prediction is not proof of causation.",
  "tags":["799 adolescents","Digital distraction","Predictive analysis"]
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
# Research findings are different from checks on the measurement instruments.
# Fail closed when neither the extracted Results nor the source abstract
# contains a clearly stated substantive result.
DIAGNOSTIC = re.compile(
 r"\b(?:Harman(?:'s)?|common method bias|single.factor test|Cronbach|"
 r"internal consistency|composite reliability|average variance extracted|"
 r"discriminant validity|convergent validity|measurement model|"
 r"confirmatory factor analys(?:is|es)|factor loadings?|"
 r"unrotated factor|normality|skewness|kurtosis|"
 r"goodness.of.fit|model fit|fit indices|reliability and validity|"
 r"sampling adequacy|collinearity|multicollinearity|"
 r"hypothesis testing outcomes|software version)\b",re.I)
FINDING_VERBS = re.compile(
 r"\b(?:associat(?:ed|ion|ions)|correlat(?:ed|ion|ions)|predict(?:ed|or|ors|s)?|"
 r"identif(?:ied|ies|y)|observed|found|show(?:ed|s)?|reveal(?:ed|s)?|"
 r"indicat(?:ed|es)?|increas(?:ed|es)?|decreas(?:ed|es)?|"
 r"higher|lower|stronger|weaker|significant(?:ly)?|"
 r"mediati(?:on|ng)|moderati(?:on|ng)|"
 r"relationship|differences?|patterns?|profiles?|themes?|"
 r"positively|negatively|attenuat(?:ed|es)?|buffer(?:ed|s)?)\b",re.I)
RESULT_CLAIM = re.compile(
 r"\b(?:results? (?:show(?:ed)?|suggest(?:ed)?|indicat(?:ed|e)?|reveal(?:ed)?|found)|"
 r"findings? (?:show|suggest|indicat|reveal)|"
 r"(?:we|the authors) (?:found|find|observed)|"
 r"(?:was|were|is|are) (?:positively |negatively |significantly )?associated|"
 r"(?:positively|negatively) (?:associated|correlated)|"
 r"(?:analysis|analyses) (?:identified|revealed|showed)|"
 r"(?:was|were) (?:higher|lower)|"
 r"(?:predicted|increased|decreased|moderated|mediated))\b",re.I)
UNTESTED = re.compile(
 r"\b(?:hypothesi[sz]|we (?:propose|expect|aim|seek|explore|test)|"
 r"the present study (?:examines|investigates|aims)|"
 r"may (?:be|lead|affect)|future research|should be studied|"
 r"previous research (?:suggests|shows)|prior studies|recent work|"
 r"evidence on whether|evidence (?:is|remains) (?:mixed|divided)|"
 r"sharply divided|remains? unclear|little is known)\b",re.I)
STOPWORDS = {"the","and","with","from","into","among","through","between",
             "about","under","using","used","study","studies","analysis",
             "effects","effect","model","models","role","research","findings"}

def reported_result(source,title="",maxlen=300):
 """Select one explicitly source-reported substantive result; never infer a claim.

 Scientific abstracts are a conservative fallback for incomplete full-text
 extraction. This routine is extractive: it must not invent significance,
 direction, numeric values or causal language.
 """
 words={x for x in re.findall(r"[a-z]{4,}",(title or "").lower())
        if x not in STOPWORDS}
 candidates=[]
 for position,s in enumerate(sentence_list(source or "")):
  if len(s)<45 or DIAGNOSTIC.search(s) or UNTESTED.search(s):continue
  if not FINDING_VERBS.search(s):continue
  # Context words alone ("associated", "effects") are insufficient if the
  # sentence is merely introducing the research question.
  if not RESULT_CLAIM.search(s):continue
  shared=len(words.intersection(re.findall(r"[a-z]{4,}",s.lower())))
  # Prefer findings that name the question's constructs, not generic model
  # statistics or statements about analysis procedures.
  score=shared*3
  if re.search(r"\b(?:ai|genai|attention|offloading|cogniti(?:on|ve)|"
               r"wellbeing|critical thinking|learning|performance|agency|"
               r"workers|participants|students|notifications|stress)\b",s,re.I):
   score+=2
  if re.search(r"\b(?:positively|negatively|higher|lower|predict(?:ed|s)?|"
               r"correlated|associated|moderated|mediated)\b",s,re.I):score+=3
  if re.search(r"\b(?:we (?:find|found)|results? (?:showed|indicated)|"
               r"findings? (?:show|indicate)|analysis (?:revealed|identified))\b",s,re.I):score+=2
  candidates.append((score,-position,s))
 if not candidates:return ""
 s=max(candidates)[2]
 if len(s)>maxlen:
  clip=s[:maxlen]
  stop=max(clip.rfind(";"),clip.rfind(","),clip.rfind(" and "))
  s=(clip[:stop].strip() if stop>maxlen//2 else clip.rsplit(" ",1)[0])+"…"
 return s

def condensed(text,role,maxlen=295):
 items=sentence_list(text)
 if not items:return ""
 if role=="finding":
  return reported_result(text,maxlen=maxlen)
 if role=="approach":
  p=[x for x in items if re.search("survey|interview|experiment|design|sample|participants|review|thematic|analysis|qualitative|quantitative",x,re.I)]
  if p:items=p
 elif role=="limitations":
  p=[x for x in items if re.search("limit|cannot|caution|self.report|cross.sectional|generaliz|sample|bias|underrepresent",x,re.I)]
  if p:items=p
 out=items[0]
 if len(out)>maxlen:
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
  digest=dict(curated);digest["status"]="editorially_written_from_indexed_sections";digest["finding_source"]="editorial"
 else:
  fulltext=r.get("level")=="full_text"
  results=(record.get("analysis") or {}).get("results") if fulltext else ""
  if not results:results=r.get("findings") or ""
  finding=reported_result(results,record.get("title",""))
  finding_source="full_text" if finding and fulltext else "abstract" if finding else "none"
  if not finding and r.get("level") in ("abstract","full_text"):
   # An extracted Results section can consist entirely of psychometrics.
   # A substantive result explicitly stated in the abstract is preferable
   # to presenting Cronbach alpha or CFA diagnostics as the finding.
   finding=reported_result(record.get("abstract_text") or "",record.get("title",""))
   finding_source="abstract" if finding else "none"
  digest={
   "idea":condensed(r.get("overview"),"idea",230),
   "approach":condensed(r.get("methods"),"approach",235),
   "finding":finding,
   "finding_source":finding_source,
   "interpretation":condensed(r.get("interpretation"),"interpretation",300),
   "limitation":condensed(r.get("limitations"),"limitations",260),
   "tags":concept_tags(record),
   "status":"automatically_condensed_source_text"
  }
 base["reading"]["digest"]=digest
 return base

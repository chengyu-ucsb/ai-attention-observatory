"""Condense extracted research sections into readable, provenance-labelled source notes.

Does NOT call an LLM, infer a result, or claim an automated digest is independently
reviewed. Curated items are independently worded using specific indexed source
passages; other papers receive a cautious source-derived sentence condensation.
Original extracts remain linked in the reading object for verification.
"""
from __future__ import annotations
import re,html
from editorial_readings import MORE_EDITORIAL
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

CURATED.update(MORE_EDITORIAL)

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

def readable_excerpt(text,role="finding",limit=195):
 """Make a *source excerpt* more readable without changing its evidentiary claim.

 No abstract claims are rewritten into stronger findings; certainty markers
 such as 'may', 'associated' and 'suggests' are preserved. When the source
 cannot be condensed cleanly, a visibly abbreviated excerpt is safer than
 inventing a narrative.
 """
 s=clean(text)
 if not s:return ""
 substitutions=[
  (r"^(?:the authors|the researchers|we) (?:found|observed|reported|showed) that\s+",""),
  (r"^(?:the study|this study|the research) (?:found|reports|reported|showed) that\s+",""),
  (r"^(?:our )?(?:results|findings) (?:show|showed|indicate|indicated|suggest|suggested) that\s+",""),
 ]
 for pattern,replacement in substitutions:
  updated=re.sub(pattern,replacement,s,flags=re.I)
  if updated!=s:
   s=updated
   break
 # Argument and interpretation are not facts; keep attribution/uncertainty.
 s=re.sub(r"^(?:the authors|the researchers) (?:argue|argued|suggest|suggested|propose|proposed) that\s+",
          "One interpretation is that ",s,flags=re.I)
 s=re.sub(r"^(?:the authors|the researchers) (?:describe|described)\s+",
          "The paper describes ",s,flags=re.I)
 s=s[0].upper()+s[1:] if s else ""
 # Prefer an intact first sentence when it communicates a full thought.
 parts=sentence_list(s)
 if parts and len(parts[0])<=limit:
  return parts[0]
 if len(s)<=limit:return s
 # Clause boundary preferred; never quietly turn a fragment into a claim.
 window=s[:limit]
 breaks=[i for i in (window.rfind("; "),window.rfind(", "),window.rfind(" and ")) if i>=limit//2]
 if breaks:window=window[:max(breaks)]
 else:window=window.rsplit(" ",1)[0]
 return window.rstrip(" ,;")+"…"

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
def source_snippet(text, role, limit=185):
 """Surface only interpretable source statements, not truncated section dumps."""
 if not text:return ""
 phrase=condensed(text,role,maxlen=260) if role!="idea" else first_source_sentence(text)
 phrase=readable_excerpt(phrase,role,limit)
 # An ellipsis is honest, but on a reading card it obscures the claim.
 # Leave the raw source available in the disclosure instead.
 if phrase.endswith("…") or len(phrase)<30:return ""
 if re.match(r"^(?:\d+(?:\.\d+)*\s+)?(?:methods?|results?|discussion|conclusions?|limitations?)\b",phrase,re.I):
  return ""
 return phrase

def first_source_sentence(text):
 parts=sentence_list(text)
 return parts[0] if parts else clean(text)

# A reader can learn which question a paper asks without mistaking an indexed
# title for an editorial finding. Topic prompts have no empirical direction.
TOPIC_QUESTIONS=[
 (r"notifications?|alerts?|hover effect","When do notifications disrupt attention?"),
 (r"(?:attention|digital) fragmentation|fragmented attention","What does attention fragmentation mean, and how can it be studied?"),
 (r"attention switching|attentional shifting|switching attention|task switching|task.switch|multitask","How does switching between tasks affect attention?"),
 (r"critical thinking.*offload|offload.*critical thinking","How does offloading thinking to AI relate to critical judgment?"),
 (r"cognitive offloading|cognitive dependency|ai dependenc","When does AI assistance become cognitive dependence?"),
 (r"ai literacy|genai literacy|digital literacy","How does knowing more about AI affect the way people use it?"),
 (r"metacognit|self.regulat","How do people monitor and regulate their thinking with technology?"),
 (r"cognitive effort|mental effort|cognitive load","How does AI change the effort people invest in thinking?"),
 (r"critical thinking|critical reason","What happens to critical thinking when people use AI?"),
 (r"digital distraction|digital multitask|smartphone|social media","How do digital habits relate to distraction and learning?"),
 (r"focus|sustained attention|attentional control","What makes sustained attention easier or harder?"),
 (r"well.being|wellbeing|technostress|stress","How does digital technology relate to well-being and strain?"),
 (r"algorithmic management|gig work|employee|workplace|knowledge work","How does AI reshape work and the people doing it?"),
 (r"recommendation|platform|synthetic content|attention economy","How do AI platforms shape attention, discovery, and trust?"),
 (r"interface|app design|digital wellbeing tool|digital well.being tool","How could technology be designed to support better attention?"),
 (r"policy|governance|regulat|ethic","What governance questions does AI raise for human attention?"),
 (r"teaching|pedagog|student|learning|education|classroom|university","How might AI change the way people learn?"),
 (r"mental health|adolescent","What can the research tell us about digital well-being?"),
]
def research_question(record):
 title=clean(record.get("title") or "").lower()
 for pattern,question in TOPIC_QUESTIONS:
  if re.search(pattern,title,re.I):
   return question
 lane=record.get("lane") or ""
 return {
  "Fragmentation":"What fragments attention in digital environments?",
  "AI & cognition":"How does AI change human thinking?",
  "Interventions":"What might help people manage digital attention?",
  "Technology & society":"What does AI change about our digital lives?"
 }.get(lane,"What question does this source explore?")

def short_source_context(record):
 """One intact line of the indexed abstract, not an invented answer."""
 abstract=record.get("abstract_text") or (record.get("reading") or {}).get("overview") or ""
 # Avoid repeating sweeping scene-setting paragraphs; select an attributable
 # method or aim that directly concerns this source.
 for line in sentence_list(abstract):
  line=readable_excerpt(line,"approach",225)
  if len(line)>225 or line.endswith("…"):continue
  if len(line)<45:continue
  if re.search(r"(?i)\b(?:aims? to|examines?|investigates?|explores?|survey|interviews?|experiment|review|proposes?|framework|model|participants?)\b",line):
   return line
 return ""

def annotate(record):
 r=record.get("reading") or {}
 base=dict(record);base["reading"]=dict(r)
 level=r.get("level")
 if record.get("kind")!="scholarly":
  notes=record.get("editorial_notes") or {}
  idea=readable_excerpt(notes.get("argument") or r.get("overview") or "", "idea",165)
  if idea.endswith("…"):idea=research_question(record)
  base["reading"]["digest"]={
   "idea":idea or research_question(record),
   "explain":short_source_context(record),"approach":"","finding":"",
   "finding_source":"none",
   "interpretation":source_snippet(notes.get("design_relevance"),"interpretation",175),
   "limitation":source_snippet(notes.get("caveat"),"limitation",170),
   "tags":concept_tags(record),"status":"editorial_or_publisher_synopsis"}
  return base
 curated=CURATED.get((record.get("doi") or "").lower())
 if curated and level in ("abstract","full_text"):
  digest=dict(curated)
  digest["status"]="editorially_written_from_indexed_sections"
  digest["editorial_basis"]="full_text" if level=="full_text" else "abstract"
  digest["finding_source"]="editorial" if digest.get("finding") else "none"
 else:
  # Never promote an introduction, source section heading, or model-fit check
  # to an editorial insight. The repository provides a traceable source note.
  fulltext=level=="full_text"
  results=(record.get("analysis") or {}).get("results") if fulltext else ""
  if not results:results=r.get("findings") or ""
  finding=reported_result(results,record.get("title",""))
  finding_source="full_text" if finding and fulltext else "abstract" if finding else "none"
  if not finding and level in ("abstract","full_text"):
   finding=reported_result(record.get("abstract_text") or "",record.get("title",""))
   finding_source="abstract" if finding else "none"
  reported=readable_excerpt(finding,"finding",185) if finding else ""
  if reported.endswith("…") or len(reported)<36:
   reported="";finding_source="none"
  question=research_question(record)
  digest={
   "idea":reported or question,
   "explain":short_source_context(record) if not reported else "",
   "approach":source_snippet(r.get("methods") or record.get("abstract_text") or "","approach",175),
   "finding":reported,
   "finding_source":finding_source,
   "interpretation":"",
   "limitation":source_snippet(r.get("limitations"),"limitations",170),
   "tags":concept_tags(record),
   "status":"automatically_condensed_source_text",
   "editorial_basis":"full_text" if fulltext else "abstract",
   "reading_mode":"finding" if reported else "research_question"
  }
 base["reading"]["digest"]=digest
 return base

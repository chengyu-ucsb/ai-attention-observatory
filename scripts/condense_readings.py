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
SEC=re.compile(r"^\s*(?:\d+\.(?:\d+\.?)*\s+){1,3}(?=[A-Za-z])")
CITATIONS=re.compile(r"\s*\(\s*(?:Table|Fig(?:ure)?|Section)\s+\d+[a-zA-Z]?\s*\)",re.I)
BRACKETS=re.compile(r"\s*\[(?:\d+[\s,;–-]*)+\]")
def clean(source):
 s=html.unescape(re.sub(r"<[^>]+>"," ",source or ""))
 s=re.sub(r"https?://\S+","",s)
 s=CITATIONS.sub("",s);s=BRACKETS.sub("",s)
 s=re.sub(r"\s+"," ",s).strip()
 # Only strip structural labels. "Results suggest that the students…" is prose.
 s=re.sub(r"^(?:\d+(?:\.\d+)*\.?\s+)?(?i:results?|discussion|methods?|introduction|abstract|conclusions?|limitations?)\b"
          r"(?:\s*[:|]\s*|\s+(?=\d+(?:\.\d+)*\.?\s)|\s+(?=(?:The|This|These|We|Our|Data|Participants|In|First|To)\b))",
          "",s).strip()
 for _ in range(3):
  new=SEC.sub("",s).strip()
  if new==s:break
  s=new
 return s
def source_sentences(text):
 """Split prose without cutting figure references, initials or decimal values."""
 source = clean(text)
 start = 0
 for boundary in re.finditer(r"(?<=[.!?])\s+(?=[A-Z0-9“(])", source):
  prefix = source[start:boundary.start()]
  if (re.search(r"\b(?:figs?|eqs?|refs?|e\.g|i\.e|et al|dr|prof|vs|no)\.$", prefix, re.I)
      or re.search(r"\b[A-Z]\.$", prefix)):
   continue
  yield prefix.strip()
  start = boundary.end()
 if source[start:].strip():
  yield source[start:].strip()


def sentence_list(text):
 return [part for part in source_sentences(text) if len(part) >= 35]


def complete_statement(sentence):
 """Reject broken references and cut-off selections even if they end in a period."""
 return (bool(re.search(r'[.!?]["”’)\]]*$', sentence))
         and not sentence.endswith(("…", "..."))
         and sentence.count("(") == sentence.count(")")
         and sentence.count("[") == sentence.count("]")
         and not re.search(r"\b(?:figs?|eqs?|e\.g|i\.e|et al)\.$", sentence, re.I))

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
 r"identif(?:ied|ies|y)|observed|found|suggest(?:ed|s)?|show(?:ed|s)?|reveal(?:ed|s)?|"
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
 r"(?:participants|students|respondents|workers|patients) (?:in [^.]{0,100} )?reported (?:significantly )?(?:higher|lower)|"
 r"(?<![-–—])(?:predicted|increased|decreased|moderated|mediated))\b",re.I)
UNTESTED = re.compile(
 r"\b(?:hypothesi[sz]\w*|we (?:propos(?:e|ed)|expect(?:ed|s)?|aim(?:ed|s)?|seek|sought|explore(?:d|s)?|test(?:ed|s)?)|"
 r"(?:this|the present) study (?:examines|investigates|aims)|"
 r"may (?:be|lead|affect)|future research|should be studied|"
 r"previous research (?:suggests|shows)|prior studies|recent work|"
 r"evidence on whether|evidence (?:is|remains) (?:mixed|divided)|"
 r"sharply divided|remains? unclear|little is known|"
 r"(?:examine[ds]?|investigate[ds]?|explore[ds]?|test(?:ed|s)?) whether|"
 r"(?:aim|aimed|aims|seek|seeks|sought) to|research questions?|"
 r"(?:previous|prior|earlier) (?:research|studies|work)|"
 r"concluding subsection|same pattern|"
 r"(?:to|we) (?:examine|investigate|explore|test)|"
 r"(?:study|paper) (?:employed|examined|investigated|explored)|"
 r"will (?:examine|test|explore))\b",re.I)
# Explicit nulls, observed actions and participant accounts may be the main
# result even when the author never uses "significant" or "we found".
OBSERVED_OUTCOME = re.compile(
 r"\b(?:there (?:was|were) no (?:statistically )?(?:significant )?(?:difference|effect|association)s? (?:in|on|between)|"
 r"(?:groups|conditions) did not differ (?:in|on)|"
 r"(?:\d+(?:\.\d+)?%? (?:of (?:the )?\d+ )?(?:sessions|students|participants|respondents|workers|teachers|patients)) "
 r"(?:submitted|answered|completed|recalled|chose|selected|returned|reported)|"
 r"(?:participants|interviewees|teachers|workers|students) (?:described|reported) (?:how|that|feeling|having|using|difficulty)|"
 r"(?:the )?(?:observed|between.group) difference was)\b", re.I)

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
  if len(s)>maxlen or not complete_statement(s) or DIAGNOSTIC.search(s) or UNTESTED.search(s):continue
  # Context words alone ("associated", "effects") are insufficient if the
  # sentence is merely introducing the research question.
  if not ((FINDING_VERBS.search(s) and RESULT_CLAIM.search(s)) or OBSERVED_OUTCOME.search(s)):continue
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
 return max(candidates)[2] if candidates else ""

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
  (r"^(?:our )?(?:results|findings) (?:show|showed) that\s+",""),
 ]
 for pattern,replacement in substitutions:
  updated=re.sub(pattern,replacement,s,flags=re.I)
  if updated!=s:
   s=updated
   break
 # "Suggest", "argue", and "may" carry the authors' degree of certainty.
 # Preserve those clauses verbatim, including who proposed the interpretation.
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
def method_specificity(line):
 """Prefer the actual design/sample to preliminary administrative procedures."""
 patterns=[
  (8,r"\bn\s*=\s*\d+|\b\d+\s+(?:(?:valid|university|college|school|undergraduate|graduate)\s+)?(?:participants|students|respondents|responses|teachers|workers|adults)\b"),
  (5,r"\b(?:randomly assigned|randomi[sz]ed|cross.sectional|longitudinal|systematic review|meta.analysis|mixed.methods)\b"),
  (3,r"\b(?:survey|interview|experiment|sample|participants|recruited|were compared|thematic analysis)\b"),
  (1,r"\b(?:regression|data were collected)\b")]
 return sum(weight for weight,pattern in patterns if re.search(pattern,line,re.I))

LIMITATION_CONTENT=re.compile(
 r"\b(?:cannot|could not|limited|limits?|lack|absence|small|not representative|"
 r"nonrepresentative|not representatively|solely|only|self.report\w*|cross.sectional|"
 r"generalizability|generalisation|generalization|selection bias|convenience sampl\w*|"
 r"confound\w*|unmeasured|not measured|not assessed|not tested|no follow.up|possibility|bias|missed)\b",re.I)

def source_snippet(text, role, limit=600):
 """Return a complete specific statement, never a generic section introduction."""
 from build_readings import METHOD, LIMIT
 if not text:return ""
 candidates=sentence_list(text)
 if role=="approach":
  candidates=sorted(candidates,key=method_specificity,reverse=True)
 for line in candidates:
  if len(line)>limit or not complete_statement(line):continue
  if role=="approach" and (not (METHOD.search(line) or re.search(r"\b(?:interviews|surveys|experiments|randomly assigned|randomi[sz]ed (?:controlled|trial|experiment|study|comparison))\b",line,re.I)) or re.search(r"\b(?:future research|prior studies|previous research|one study|another study|(?:studies|research)[^.]{0,100}(?:needed|required)|should be|could be)\b",line,re.I)):continue
  if role=="limitations" and (not LIMITATION_CONTENT.search(line) or not (LIMIT.search(line) or re.search(
      r"\b(?:(?:cannot|could not) (?:establish|infer|determine|conclude|disentangle|rule out|exclude|generaliz\w*)|limited to|self.report\w*|cross.sectional|generalizability|generalisation|generalization|selection bias|convenience sampl\w*|absence of|limits? the|not representatively)\b",line,re.I))):continue
  phrase=readable_excerpt(line,role,limit)
  if phrase.endswith("…") or len(phrase)<30:continue
  if re.match(r"^(?:\d+(?:\.\d+)*\s+)?(?:methods?|results?|discussion|conclusions?|limitations?)\b",phrase,re.I):continue
  return phrase
 return ""

def reported_result_bundle(source, title="", limit=600):
 """Keep adjacent contrasting/null outcomes with an explicit result sentence.

 This is still source extraction, not an original narrative. Never draw a new
 finding from Discussion or add an unsupported caveat. Complete sentences and
 their original ordering are preserved; no clause is clipped to fit a card.
 """
 primary=reported_result(source,title,maxlen=limit)
 if not primary:return ""
 # Do not filter short sentences: an intervening caveat breaks adjacency.
 parts=list(source_sentences(source))
 if primary not in parts:return ""
 start=parts.index(primary)
 selected=[readable_excerpt(primary,"finding",limit)]
 for line in parts[start+1:start+3]:
  if UNTESTED.search(line) or DIAGNOSTIC.search(line) or not complete_statement(line):break
  if re.search(r"\b(?:it is possible|perhaps|might|may|could|would|"
      r"we (?:believe|argue|suggest)|the authors (?:believe|argue|suggest)|"
      r"their sample|another sample|et al\.)|\b[A-Z][a-z]+(?: and [A-Z][a-z]+)? \(\d{4}\)",line):break
  contrast=re.match(r"^(?:However|Further|Nevertheless|In contrast|By contrast|Conversely|Yet)\b",line,re.I)
  adjacent_null=re.match(r"^(?:(?:The|These|Both) (?:groups|conditions) did not|"
      r"There (?:was|were) no|No (?:statistically )?significant)\b",line,re.I)
  observed=re.search(r"\b(?:demonstrated (?:significantly )?(?:higher|lower)|"
    r"did not (?:differ|show)|(?:was|were) no (?:statistically )?significant|"
    r"no (?:statistically )?significant (?:differences?|effects?|associations?)|"
    r"(?:was|were) (?:higher|lower))\b",line,re.I)
  if not ((contrast or adjacent_null) and (reported_result(line,title,maxlen=limit) or observed)):break
  addition=readable_excerpt(line,"finding",limit)
  if addition.endswith("…") or len(" ".join(selected+[addition]))>limit:break
  selected.append(addition)
 return " ".join(selected)


def source_title_headline(record):
 """Use attribution when no source-checked editorial headline is available.

 An extracted result is evidence for the body, not an edited headline, even
 when it happens to be short. Never manufacture a claim from a topic, remove
 statistical qualifiers, or select only one side of a result to fit a heading.
 Preserve the complete publication title, including subtitles and qualifiers.
 """
 return re.sub(r"\s+", " ", html.unescape(record.get("title") or "")).strip() or "Untitled source"


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

# Reader introductions written from these publications' indexed abstracts.
ABSTRACT_LEADS = {
 "https://openalex.org/W7164777577": "During a reading task, researchers tracked where people looked when they could block a distraction themselves or someone else blocked it for them.",
 "https://openalex.org/W7161620989": "The authors propose interviewing employees and managers about when a chatbot feels trustworthy enough to take over part of their thinking.",
 "10.1016/j.ijhcs.2025.103653": "A review of AI well-being tools asks what designers need to know about users, which interventions to offer, and how to protect personal data.",
 "10.3389/feduc.2025.1697554": "The authors propose giving students an AI novice to teach. Its questions would help them notice gaps in their explanations.",
 "10.3389/fpsyg.2023.1261955": "Two university English classes followed different lessons, one with AI support. Researchers compared their language skills, motivation, and ability to manage their own learning.",
 "10.3389/feduc.2026.1953305": "International policies on AI and academic integrity assign different responsibilities to students and universities. The paper asks how those policies draw the line between authorship and cheating.",
 "10.3389/fpsyg.2026.1929666": "A survey of 1,760 terminology practitioners examined how they prompt language models, how confident they feel using them, and how mentally demanding they find the work.",
 "10.3389/feduc.2026.1944529": "The authors propose that students’ use of AI in academic writing depends on both the demands of the assignment and the support their teacher provides.",
 "10.1016/j.chbr.2026.101420": "Researchers followed a group of medical students for eight months to examine how patterns of worry and attention relate to problematic smartphone app use.",
}

def short_source_context(record):
 """One intact line of the indexed abstract, not an invented answer."""
 abstract=record.get("abstract_text") or ""
 # Avoid repeating sweeping scene-setting paragraphs; select an attributable
 # method or aim that directly concerns this source.
 for line in sentence_list(abstract):
  line=readable_excerpt(line,"approach",225)
  if len(line)>225 or line.endswith("…"):continue
  if len(line)<45:continue
  if re.search(r"(?i)\b(?:aims? to|examines?|investigates?|explores?|survey|interviews?|experiment|review|proposes?|framework|model|participants?)\b",line):
   return line
 return ""

# Brief, attributed public-facing readings for non-academic sources; these are
# descriptions of ideas, not measurements of the ideas' effectiveness.
PUBLIC_COMMENTARY={
 "why-calling-for-a-kill-switch":"Shutting down AI with a single switch may be less realistic than designing systems that remain governable.",
 "what-is-the-socratic-method":"Questioning assumptions can reveal gaps in understanding that fluent AI answers might otherwise conceal.",
 "heres-how-a-learning-strategy":"Faster answers are not the same as stronger learning. Asking AI for questions and feedback may keep learners engaged.",
 "what-happens-to-language":"Communication depends on listeners as well as speakers; conversational AI changes both sides of that exchange.",
  "faster! louder! brighter!":"Fast-moving children’s media can hold the gaze while leaving too little room to think through what is happening.",
 "the-internet-was-built-for-human-agency":"AI agents acting on our behalf make accountability and meaningful user choice harder to define.",
 "when-an-ai-agent-says":"Automated decisions complicate what meaningful user consent looks like.",
 "the-paradox-of-ai-assistance":"AI can make a completed assignment look better without proving that its author learned more.",
 "how-ai-powered-emotional-surveillance":"Systems that classify people's emotions or attention can become tools of surveillance and control.",
 "how-ai-driven-search":"AI search tools change how people discover information and decide which sources to trust.",
 "new-perspectives-on-ai-agentiality":"User-controlled AI intermediaries could give people more influence over what reaches their attention.",
 "intention tracking":"Asking why an app is being opened adds a moment of reflection before an automatic habit.",
 "freedom — app and website blocking":"Blocking distracting apps can create a more predictable work period without measuring anyone's mental state.",
 "focus filters":"Focus settings let apps adjust their behavior to a user's preferences and chosen context.",
 "android focus mode":"Device-level focus controls can pause apps and manage interruptions without guessing how attentive someone is.",
 "the battle for cognitive liberty":"As AI reshapes digital experiences, people may need stronger control over how their attention is influenced."
}
def public_commentary_idea(record):
 url=(record.get("url") or "").lower()
 title=clean(record.get("title") or "").lower()
 for key,idea in PUBLIC_COMMENTARY.items():
  if key in url or key in title:
   return idea
 return ""


# In-depth, independently written, source-specific readings. These are not
# generated from headlines: their argument structure was checked against the
# original public essays. Product notes below are based on published feature
# descriptions and explicitly make no effectiveness claim.
DEEP_PERSPECTIVES = {
  "faster! louder! brighter!": {
   "reasoning":"Kucirkova distinguishes the amount of time spent watching from the time a story gives a child to interpret an event. Rapid cuts, songs, and rewards may continually restart attention; a coherent narrative, repetition, and pauses can leave space for prediction, emotion, and memory. She argues that a screen can look engaging without supporting the reflective work its lesson requires.",
   "examples":"The essay contrasts the rapid, stimulus-heavy transitions in programmes such as Ask the StoryBots and Paw Patrol with the narrative pacing and moments for interpretation in Bluey, Sesame Street, Daniel Tiger’s Neighbourhood, and Mister Rogers’ Neighborhood. Her Kids’ Slow Media Project develops observational criteria for age-sensitive pacing rather than treating minutes watched as a quality rating.",
   "tension":"Slow is not always educational, and fast is not necessarily harmful. The appropriate pace depends on the child's age, situation, temperament, and the material; an observational evaluation of programmes does not itself demonstrate lasting causal effects on attention.",
   "open_question":"Could attention-supporting AI interfaces be evaluated for the time they leave users to interpret, question, and recover a thought—not merely how quickly they deliver an answer?",
   "basis":"Editorial analysis of the original Guardian long read, September 17, 2026 (also originally published in Aeon)"
  },
 "the-internet-was-built-for-human-agency": {
  "reasoning": "The authors distinguish an agent's technical capability from the authority it legitimately exercises. Traditional Internet governance tends to focus on identities and network standards; AI governance tends to focus on model behavior. Neither alone answers who approved a particular action, for how long, or whether it can be audited and reversed.",
  "examples": "They place existing authorization work, including tool-access protocols, agent-to-agent interoperability, and proposals for verifiable delegation, within a broader need for an Internet authority layer. The principal–agent relationship is their organizing analogy.",
  "tension": "More autonomy can reduce friction for users while increasing the distance between a person's intention and the actions attributed to that person. Technical authorization may prove that a system had permission without establishing that its action reflected informed preferences.",
  "open_question": "What evidence would show that people understand, can inspect, and can revoke the decisions an attention assistant makes for them?",
  "basis": "Editorial analysis of the public essay"
 },
 "when-an-ai-agent-says": {
  "reasoning": "The essay arranges delegation along a continuum, from AI preparing a choice for human confirmation to agents orchestrating multi-step transactions. As autonomy expands, the author argues that limits on authority, verifiable mandates, disclosure, and opportunities to review the decision matter more.",
  "examples": "The article discusses competing claims around AI shopping agents, then considers European legal concepts such as mandates, digital identity attestations, online contracting, and payment authentication. Those examples show why clicking on behalf of someone raises legal as well as interface questions.",
  "tension": "Convenience may expand available options yet also hide defaults and narrow users' opportunities to intervene. Legal permission and a good user experience are related but not equivalent.",
  "open_question": "Which decisions can an attention assistant safely automate, and which should always return to the person for explicit approval?",
  "basis": "Editorial analysis of the public essay"
 },
 "new-perspectives-on-ai-agentiality": {
  "reasoning": "The authors separate agenticity, the capacity to perform increasingly complex tasks, from agentiality, the quality of the agent's relationship to the person it represents. They argue that a technically capable assistant could still serve platform or provider interests rather than its user.",
  "examples": "Their proposed direction involves interoperable, user-serving intermediaries and attention guardians. The article asks who an agent serves when people's priorities and a platform's incentives are misaligned.",
  "tension": "An assistant designed around personal preferences still operates within social relationships and competing obligations. Serving an individual well does not automatically settle collective questions about information access and democratic accountability.",
  "open_question": "Could a user-controlled attention guardian explain whose priorities shape its filtering choices, and allow the person to contest them?",
  "basis": "Editorial analysis of the public essay"
 },
 "how-ai-powered-emotional-surveillance": {
  "reasoning": "The author argues that emotion-recognition systems threaten more than privacy because their classifications can influence behavior under conditions of institutional power. Improving a classifier's accuracy would not resolve the underlying question of whether an organization should infer private emotional states in the first place.",
  "examples": "The essay discusses attention-monitoring headbands tested in schools, emotion-detection trials in border screening, and surveillance trials on public transport. These cases show how a stated goal such as safety or productivity can shift into monitoring and pressure.",
  "tension": "A system that claims to help people pay attention can become coercive when an employer, teacher, or authority defines which mental states count as acceptable. Voluntary self-reflection and involuntary emotional classification are different design choices.",
  "open_question": "How can an attention-support tool help people reflect on their goals without turning inferred cognitive or emotional states into scores for others?",
  "basis": "Editorial analysis of the public essay"
 },
 "https://developer.apple.com/documentation/appintents/focus/": {
  "thesis": "Apple lets people choose which parts of a participating app belong in a particular Focus, such as which email account can send alerts during work.",
  "reasoning": "When someone turns on a Focus, the system calls the filter the developer has built into the app. The app uses the configuration for that Focus to change its behavior and decide which incoming notifications to show.",
  "examples": "Apple gives the example of personal email or messages during a Work Focus. Account-specific filtering lets work communications still get through while alerts from a personal account stay quiet.",
  "qualification": "The developer has to implement the filter. The available choices depend on what the particular app exposes when someone configures a Focus.",
  "basis": "Analysis of published product documentation"
 },
 "https://www.android.com/productivity/": {
  "thesis": "Android users can pause selected apps during a focused period. They can also see which apps use the most time or send the most notifications before deciding where to set a limit.",
  "reasoning": "Focus Mode changes what is available on the phone while it is active. Digital Wellbeing also shows how time and notifications are distributed across apps, so a person can choose which apps warrant a daily limit.",
  "examples": "Android lists games, social media and communication apps as things a person can pause. Someone who wants to understand repeated interruptions can instead check which app sends the most notifications before choosing a limit.",
  "qualification": "Time spent in an app and the number of alerts describe phone activity. The guide gives no measure of how well a person concentrated during that time.",
  "basis": "Analysis of published product documentation"
 },
 "intention-tracking": {
  "reasoning": "The product introduces a small decision point before an app opens. Its mechanism is deliberate friction and self-reflection, rather than continuous measurement of attention.",
  "examples": "The described intention picker asks what a person wants to do before entering a distracting app. A design comparison would need to distinguish noticing an intention from actually changing subsequent behavior.",
  "tension": "Additional friction may discourage automatic use, but can also become irritating or easy to ignore. The product description does not establish which outcome dominates.",
  "open_question": "Does an intention prompt change what people do next, or merely add an extra tap?",
  "basis": "Analysis of published product documentation"
 },
 "freedom — app and website blocking": {
  "reasoning": "This is an environment-changing intervention: rather than coaching attention moment by moment, it prevents access to selected digital distractions during a user-defined interval.",
  "examples": "The product describes blocking selected apps and websites during scheduled sessions, including multi-device use. That makes it a useful comparison condition for a softer reminder or reflection tool.",
  "tension": "Blocking can simplify choices but may also interfere with legitimate interruptions or make people feel less in control.",
  "open_question": "When do people prefer firm restrictions to an assistant that helps them make each choice?",
  "basis": "Analysis of published product documentation"
 }
}
def checked_machine_document(record):
 """Only the document reader's validated, fully covered output can become reader prose."""
 machine=record.get("deep_analysis")
 if not isinstance(machine,dict) or machine.get("source_depth") not in ("full_text","source_html"):
  return {}
 from prepared_reading_schema import validate_analysis
 try:
  validate_analysis(machine,kind=record.get("kind"))
 except ValueError:
  return {}
 record_doi=str(record.get("doi") or "").lower()
 source_record_doi=str(machine["coverage"].get("record_doi") or "").lower()
 if source_record_doi and record_doi!=source_record_doi:
  return {}
 return machine


def machine_research_account(record):
 if record.get("kind")!="scholarly" or record.get("verified_article_review") or record.get("original_reading"):
  return {}
 from reading_headlines import reader_genre
 if reader_genre(record) not in ("research","review","proposal","conceptual"):
  return {}
 machine=checked_machine_document(record)
 if not any(machine.get(k) for k in ("research_question","study_design","reported_results","authors_interpretation")):
  return {}
 account={key:machine[key] for key in ("research_question","study_design","reported_results",
  "authors_interpretation","critical_context","limitations","open_question") if machine[key]}
 if reader_genre(record) in ("conceptual","proposal"):
  account.pop("reported_results",None)
 if not any(account.get(k) for k in ("research_question","study_design","reported_results","authors_interpretation")):
  return {}
 return {**account,"source_url":machine["source_url"],"source_version":machine["coverage"]["document_version"],
         "review_status":machine["review_status"]}


def deep_perspective(record,notes):
 """Only add interpretive depth when an original source has been examined."""
 reviewed=record.get("source_review") or {}
 if reviewed:
  return {
   "thesis":reviewed["thesis"],"reasoning":reviewed["reasoning"],
   "examples":reviewed["examples"],"tension":reviewed["tension"],
   "implications":reviewed["implications"],"open_question":reviewed["open_question"],
   "qualification":reviewed["qualification"],"basis":reviewed["reading_basis"],
   "source_depth":"read_article"
  }
 # Prefer a source-checked, editorially authored reading when available.
 key=((record.get("url") or "")+" "+(record.get("title") or "")).lower()
 extra=next((v for token,v in DEEP_PERSPECTIVES.items() if token in key),{})
 machine=checked_machine_document(record) if not extra.get("basis","").startswith("Editorial analysis") else {}
 if machine and machine["kind"]=="nonacademic":
  return {
   **{field:machine.get(field,"") for field in ("thesis","reasoning","examples","tension","implications","open_question","qualification")},
   "basis":machine.get("basis","AI-assisted source analysis"),
   "source_depth":"machine_read_full_article","source_url":machine["source_url"],"review_status":machine["review_status"]
  }
 argument=notes.get("argument") or ""
 overview=(record.get("reading") or {}).get("overview") or ""
 return {
  "thesis":extra.get("thesis") or argument or overview,
  "reasoning":extra.get("reasoning",""),
  "examples":extra.get("examples",""),
  "tension":extra.get("tension",""),
  "implications":notes.get("design_relevance") or "",
  "open_question":extra.get("open_question",""),
  "qualification":extra.get("qualification") or notes.get("caveat") or "",
  "basis":extra.get("basis") or ("Editorially prepared synopsis" if argument else "Publisher description only"),
  "source_depth":"read_article" if extra.get("basis","").startswith("Editorial analysis") else
                 "product_documentation" if extra.get("basis","").startswith("Analysis of published product") else
                 "editorial_synopsis" if argument else "publisher_synopsis"
 }

# Source-specific paraphrases, keyed to the original publication DOI. These
# journal articles advance arguments, including when the publisher calls the
# format a review. Their examples do not supply measured effects.
JOURNAL_ARGUMENTS = {
 "10.3389/feduc.2026.1997466": {
  "thesis": "Danny Glick and colleagues ask how AI can help learners plan their work and use feedback while leaving decisions about learning in their hands.",
  "reasoning": "The editors bring together four papers. One review found more consistent benefits for planning than for following through, a distinction the editors use to explain why learners still need opportunities to act on their plans.",
  "examples": "One contributor proposes that an AI partner challenge a learner’s explanation. Another paper compares AI feedback with peer feedback in a Hong Kong classroom. The editors use them to illustrate different ways learners might stay involved in judging their work.",
 },
 "10.1080/00131857.2026.2733624": {
  "thesis": "Nin Kirkham argues that teaching critical thinking means giving students room to reach conclusions their instructors might disagree with.",
  "reasoning": "Drawing on her experience teaching philosophy and ethics, Kirkham questions the practice of presenting each new threat, including AI, as a crisis that critical thinking can solve.",
  "examples": "She recommends having students take an unfamiliar position seriously and give reasons for their own. A class that rewards only one acceptable conclusion would defeat that purpose.",
 },
 "10.3389/fpsyg.2025.1699320": {
  "thesis": "Ginto Chirayath and colleagues ask when AI helps people cope with stress and when the work of monitoring themselves becomes another source of strain.",
  "reasoning": "Their argument turns on who interprets the experience. A person decides what to record in a diary. A mood-tracking app can also assign a score or suggest what the person should do next.",
  "examples": "The authors contrast tools that free people from remembering routine tasks with tools that invite constant checking of emotional feedback. They present these as two possible uses of a tool, not as an estimate of how often either occurs.",
 },
 "10.1007/s00146-025-02405-8": {
  "thesis": "Gunter Bombaerts and colleagues argue in this manifesto that attention policy should ask what technology helps people care for, alongside how much of their time it takes.",
  "reasoning": "Drawing on Buddhist philosophy, the authors describe attention as a practice shaped by the body, social relationships and values. They propose evaluating designs by whether those designs help people notice and respond to suffering.",
  "examples": "The authors ask how a design could make its underlying values visible to the people using it. They offer this as a question for further research and design.",
 },
}


def annotate(record):
 from original_readings import public_record, note_for
 record=public_record(record)
 original=note_for(record)
 if original is not None:
  return {**record,"reading":original}
 r=record.get("reading") or {}
 base=dict(record);base["reading"]=dict(r)
 base["reading"].pop("machine_account",None)
 account=machine_research_account(record)
 if account:
  base["reading"]["machine_account"]=account
  base["reading"]["level"]="full_text"
 level=base["reading"].get("level")
 if record.get("kind")!="scholarly":
  notes=record.get("editorial_notes") or {}
  rewritten=public_commentary_idea(record)
  depth=deep_perspective(record,notes)
  if record.get("source")=="Official product documentation" and depth["qualification"] == (
      "Product documentation is a description of features, not independently established evidence of effectiveness."):
   depth["qualification"]=""
  # Only an explicitly edited takeaway is a headline. A thesis excerpt may
  # omit the qualification in its next sentence; retain it in the body.
  idea=record.get("editorial_takeaway") or rewritten or source_title_headline(record)
  base["reading"]["digest"]={
   "idea":idea,
   "explain":depth["thesis"] or "",
   "approach":"",
   "finding":"",
   "finding_source":"none",
   "interpretation":depth["implications"],
   "limitation":depth["qualification"],
   "longform":depth,
   "tags":concept_tags(record),
   "status":"edited_perspective" if depth["source_depth"]=="read_article" else
            "locally_analyzed_article" if depth["source_depth"]=="machine_read_full_article" else "publisher_or_editorial_synopsis",
   "editorial_basis":depth["basis"]
  }
  return base
 from reading_headlines import reader_genre
 genre=reader_genre(record)
 if genre in ("editorial", "opinion", "commentary", "analysis") and record.get("kind")=="scholarly":
  argument=JOURNAL_ARGUMENTS.get((record.get("doi") or "").lower(), {})
  thesis=argument.get("thesis", "")
  base["reading"].update(research_type="editorial" if genre=="editorial" else "opinion", methods="", findings="", sample="",
                         reported_findings=False, overview=thesis, interpretation=argument.get("reasoning", ""), limitations="")
  base["reading"]["digest"]={"idea":thesis, "explain":thesis, "approach":"", "finding":"",
      "finding_source":"none", "interpretation":"", "limitation":"", "tags":concept_tags(record),
      "longform":{**argument, "source_depth":"journal_argument"} if argument else {},
      "status":"journal_argument" if argument else "journal_abstract_preview", "editorial_basis":level}
  return base
 if record.get("research_type")=="conceptual_framework":
  framework=record.get("framework_notes") or {}
  checked=record.get("verified_article_review") or {}
  edited=(record.get("editorial_digest") or {}) if checked else {}
  idea=edited.get("idea") or framework.get("idea") or source_title_headline(record)
  base["reading"]["digest"]={
   "idea":idea,
   "explain":edited.get("explain") or framework.get("idea") or "",
   "approach":edited.get("approach") or framework.get("approach") or "Conceptual framework based on published literature.",
   "finding":"",
   "finding_source":"none",
   "interpretation":edited.get("interpretation") or " ".join(framework.get("stages") or []),
   "limitation":edited.get("limitation") or framework.get("qualification") or "This is a theoretical proposal.",
   "tags":concept_tags(record),
   "status":"conceptual_framework",
   "editorial_basis":"publisher_full_article_paraphrased" if checked else "publisher_source_abstract",
   "reading_mode":"conceptual_proposal"
  }
  return base
 curated=record.get("editorial_digest") or CURATED.get((record.get("doi") or "").lower())
 if curated and level in ("abstract","full_text"):
  digest=dict(curated)
  digest["status"]="editorially_written_from_indexed_sections"
  digest["editorial_basis"]="publisher_full_article_paraphrased" if record.get("verified_article_review") or (record.get("analysis") or {}).get("original_paraphrases_only") else "full_text" if level=="full_text" else "abstract"
  digest["finding_source"]="editorial" if digest.get("finding") else "none"
 else:
  # Never promote an introduction, source section heading, or model-fit check
  # to an editorial insight. The repository provides a traceable source note.
  fulltext=level=="full_text"
  results=(record.get("analysis") or {}).get("results") if fulltext else ""
  # A row can have full-text methods and only an abstract result. The selected
  # sentence, not the article's best available section, determines its basis.
  result_basis="full_text" if results else "abstract"
  if not results:
   results=(r.get("findings") if not fulltext else "") or record.get("abstract_text") or ""
  finding=reported_result_bundle(results,record.get("title",""))
  finding_source=result_basis if finding else "none"
  if not finding and level in ("abstract","full_text"):
   finding=reported_result_bundle(record.get("abstract_text") or "",record.get("title",""))
   finding_source="abstract" if finding else "none"
  reported=finding
  if reported.endswith("…") or len(reported)<36:
   reported="";finding_source="none"
  methods=((record.get("analysis") or {}).get("methods") or r.get("methods") or "") if fulltext else record.get("abstract_text") or r.get("methods") or ""
  approach=source_snippet(methods,"approach")
  approach_source=("full_text" if fulltext else "abstract") if approach else "none"
  abstract_approach=source_snippet(record.get("abstract_text") or "","approach")
  # A full-text label does not make a generic procedure more informative than
  # the abstract's explicit design/sample. Retain the selected line's own basis.
  if abstract_approach and (not approach or method_specificity(abstract_approach)>method_specificity(approach)):
   approach=abstract_approach
   approach_source="abstract"
  limitation=source_snippet((record.get("analysis") or {}).get("limitations") or r.get("limitations"),"limitations")
  paraphrase=ABSTRACT_LEADS.get(record.get("doi") or record.get("url"))
  context=(paraphrase or short_source_context(record)) if not reported else ""
  digest={
   "idea":source_title_headline(record),
   "explain":context,
   "approach":approach,
   "approach_source":approach_source,
   "finding":reported,
   "finding_source":finding_source,
   "interpretation":"",
   "limitation":limitation,
   "limitation_source":("full_text" if fulltext else "abstract") if limitation else "none",
   "tags":concept_tags(record),
   "status":"automatically_condensed_source_text",
   "editorial_basis":"full_text" if fulltext else "abstract",
   "reading_mode":"finding" if reported else "research_question"
  }
  if context:
   digest["explain_source"]="abstract_paraphrase" if paraphrase else "abstract_excerpt"
 base["reading"]["digest"]=digest
 return base

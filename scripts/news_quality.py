"""Verify that an RSS/Atom description actually contains a synopsis.

Google News often provides the headline plus publisher name rather than an
article body. Its redirect URL is not a publisher article URL. Such records
are internal leads, not article-based public analysis.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from nonacademic_reading_voice import distinct_support
from source_quality import AI, emerging_human_topic
from urllib.parse import urlsplit

def normalized_words(s):
    return re.findall(r"[a-z0-9]+",str(s or "").lower())

def useful_description(title,description,source=""):
    description=str(description or "").strip()
    words=normalized_words(description)
    title_words=normalized_words(title)
    if len(description)<90 or len(words)<15:
        return False
    if title_words:
        prefix=" ".join(title_words)
        remainder=" ".join(words)
        if remainder.startswith(prefix):
            # Many Google RSS entries read "[same headline] — [publisher]".
            tail=remainder[len(prefix):].strip()
            if len(tail.split())<15:
                return False
    if len(set(words))<10:
        return False
    return True

def publisher_url(url):
    try:
        p=urlsplit(str(url or ""))
        return (p.scheme=="https" and bool(p.hostname) and
                p.hostname not in ("news.google.com","google.com") and
                not p.hostname.endswith(".google.com"))
    except ValueError:
        return False

def commentary_reading_depth(record):
    """Measure actual source-specific analysis, never feed-length metadata."""
    longform=((record.get("reading") or {}).get("digest") or {}).get("longform") or {}
    source_depth=longform.get("source_depth")
    if source_depth not in ("read_article","machine_read_full_article"):
        return False
    if not publisher_url(record.get("url")):
        return False
    if not record.get("source_review") and source_depth=="read_article" and not (
        (longform.get("basis") or "").startswith("Editorial analysis")):
        return False
    if source_depth == "machine_read_full_article" and not distinct_support(longform):
        return False
    lengths={name:len(str(longform.get(name) or "").strip())
             for name in ("thesis","reasoning","examples","tension","qualification")}
    # Missing any two layers is not an in-depth article analysis. Require
    # concrete supporting examples and a source-specific qualification.
    return (lengths["thesis"]>=70 and lengths["reasoning"]>=150
            and lengths["examples"]>=100 and lengths["tension"]>=90
            and lengths["qualification"]>=60)

def substantive_article(record):
    if record.get("source")=="Official product documentation":
        # Product documentation is a separate source category, explicitly
        # distinguished from researched journalism and empirical evidence.
        return bool((record.get("reading") or {}).get("overview") or
                    (record.get("editorial_notes") or {}).get("design_relevance")) and publisher_url(record.get("url"))
    if record.get("companion_to"):
        # A verified secondary explainer is preserved ONLY as a companion
        # to its original research, not counted as an independent reading.
        return bool((record.get("reading") or {}).get("overview")) and publisher_url(record.get("url"))
    return commentary_reading_depth(record)


# Classify the checked central argument. Incidental examples, generic topic
# labels, RSS descriptions and reviewers' suggested design applications do not
# establish a public reading's subject.
ATTENTION_MECHANISM = re.compile(
    r"\b(?:attentional|attention (?:economy|capture|span|control|residue|allocation)|"
    r"(?:human|student|sustained|selective|divided|visual|collective) attention|"
    r"(?:capture|hold|sustain|redirect|compete for)(?:s|ing)? (?:\w+ ){0,2}attention|"
    r"(?:digital|mental|phone|screen|classroom|workplace) distractions?|task[- ]switching|multitasking|"
    r"digital well[- ]?being|deep work|focus (?:mode|filters?|timers?)|"
    r"(?:filter|silence|batch|pause|limit)\w* (?:\w+ ){0,2}notifications?|"
    r"cognitive (?:load|offloading|control)|mental workload|alert fatigue)\b", re.I)
ATTENTION_BEHAVIOR = re.compile(
    r"\b(?:distract(?:ed|ing|ions?)?|interruptions?|concentrat(?:e|ion)|"
    r"stay(?:ing)? focused|sustain(?:ing)? focus)\b", re.I)
BEHAVIOR_CONTEXT = re.compile(
    r"\b(?:people|students?|learners?|workers?|employees?|readers?|participants?|"
    r"clinicians?|teachers?|users?|children|kids|smartphones?|notifications?|"
    r"classrooms?|study sessions?|study habits|work periods?|at work|distracting apps?)\b", re.I)
SYSTEM_EVALUATION = re.compile(
    r"\b(?:benchmarks?|model[- ]only|model architecture|training (?:data|compute)|"
    r"inference (?:speed|cost)|tokens per second|transformers?)\b", re.I)
HUMAN_AI_USE = re.compile(
    r"\b(?:human (?:oversight|control|decisions?|agency)|agency|agentiality|"
    r"delegat\w*|consent\w*|autonomy|on (?:people.s|\w+ users?.?|their) behalf|"
    r"(?:assistant|app)[- ](?:level|access)|user controls?|control over|"
    r"learning|learners?|studying|thinking|reasoning|recall|judg(?:e)?ments?|tutor(?:s|ing)?|"
    r"decision[- ]making|writing|readers?|reliance|rely(?:ing)? on|overreliance|"
    r"(?:teachers?|students?|employees?|workers?) (?:use|using|used|adopt\w*)|"
    r"(?:work|study) (?:habits|practices)|reflection|cognitive|attention)\b", re.I)
# These phrases describe the work or choice a person keeps. Check only the
# source's central argument, never a feed category or a list of examples.
HUMAN_PRACTICE = re.compile(
    r"\b(?:(?:develop(?:ing)?|build(?:ing)?|practis(?:e|ing)|practic(?:e|ing)) "
    r"(?:\w+ ){0,3}skills?|(?:displac|replac|bypass|skip)\w* "
    r"(?:\w+ ){0,2}(?:practice|problem[- ]solving)|"
    r"(?:research|review|evidence|studies)\b[^.!?]{0,70}"
    r"\b(?:AI|artificial intelligence) in (?:education|teaching|classrooms?))\b", re.I)
HUMAN_AI_ACCESS = re.compile(
    r"\b(?:access to|enabl\w*|disabl\w*|opt\w* (?:in|out)|"
    r"turn\w* (?:on|off))\b[^.!?]{0,65}\b(?:AI|artificial intelligence)\b", re.I)
# A title can identify which system the thesis discusses, but cannot supply
# the topic on its own. These aliases retain checked accounts of AI agents or
# classifications without admitting unrelated skill/attention pieces merely
# because their headline mentions AI.
AI_ARGUMENT_ALIAS = re.compile(
    r"\b(?:automated (?:agents?|assistants?|systems?|moderation)|"
    r"machine (?:classifications?|decisions?|recommendations?)|"
    r"language models?|chatbots?)\b", re.I)
TECHNICAL_OR_FIGURATIVE = re.compile(
    r"\b(?:(?:self|cross|multi[- ]?head|scaled dot[- ]product)[- ]attention|"
    r"(?:machine|deep|reinforcement|representation|transfer) learning|"
    r"(?:pay(?:s|ing)?|paid|draw(?:s|ing)?|drew|attract(?:s|ed|ing)?) "
    r"(?:\w+ ){0,2}attention to|attention to detail)\b", re.I)


@lru_cache(maxsize=1)
def checked_topic_decisions():
    path = Path(__file__).resolve().parents[1] / 'data/editorial-topic-decisions.json'
    return {item['url']: item for item in json.loads(path.read_text(encoding='utf-8'))['entries']}


def commentary_topic(record):
    """Return direct or adjacent only for a source-supported central topic."""
    note = record.get('original_reading') or {}
    decision = checked_topic_decisions().get(record.get('url'))
    if decision and decision['source_sha256'] == (note.get('source') or {}).get('source_sha256'):
        return decision['topic']
    reading = record.get('reading') or {}
    longform = (reading.get('digest') or {}).get('longform') or {}
    argument = (note.get('summary') or {}).get('thesis') or longform.get('thesis') or ''
    if record.get('source') == 'Official product documentation':
        # The official feature name can state the attention mechanism more precisely
        # than a plain-language description of what people see on screen.
        argument += ' ' + str(record.get('title') or '') + ' ' + (reading.get('overview') or '')
    # A verified explainer links to its source and is never an independent
    # publication. Its checked synopsis can describe the source's subject.
    if record.get('companion_to'):
        argument += ' ' + (reading.get('overview') or '')
    argument = TECHNICAL_OR_FIGURATIVE.sub(' ', argument)
    title = TECHNICAL_OR_FIGURATIVE.sub(' ', str(record.get('title') or ''))
    attention = (ATTENTION_MECHANISM.search(argument) or
                 (ATTENTION_BEHAVIOR.search(argument) and BEHAVIOR_CONTEXT.search(argument)))
    if SYSTEM_EVALUATION.search(argument) and not BEHAVIOR_CONTEXT.search(argument):
        return None
    human_use = (HUMAN_AI_USE.search(argument) or emerging_human_topic(argument)
                 or HUMAN_PRACTICE.search(argument)
                 or (HUMAN_AI_ACCESS.search(argument) and BEHAVIOR_CONTEXT.search(argument)))
    central_ai = AI.search(argument) or (AI.search(title) and AI_ARGUMENT_ALIAS.search(argument))
    reviewed = record.get('source_review') or {}
    if central_ai and not human_use and reviewed.get('thesis') == longform.get('thesis') and reviewed.get('source_url'):
        # Let a checked explanation disambiguate which decisions a person keeps.
        # The central thesis must already describe people's use of AI. Incidental
        # examples or suggested applications cannot supply that missing topic.
        human_role = re.search(r"\b(?:buyers?|shoppers?|consumers?|people|users?|students?|teachers?|workers?|readers?)\b", argument, re.I)
        if human_role and commentary_reading_depth(record):
            reasoning = TECHNICAL_OR_FIGURATIVE.sub(' ', reviewed.get('reasoning') or '')
            human_use = HUMAN_AI_USE.search(reasoning) or HUMAN_PRACTICE.search(reasoning)
    if central_ai and (human_use or attention):
        return 'direct'
    if attention:
        return 'adjacent'
    return None

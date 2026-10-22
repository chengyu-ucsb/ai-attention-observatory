"""Conservative, auditable quality screen for the public Observatory.

Venue reputation is a *discovery prior*, never an article-level quality claim.
Unverified, weak-fit and preprint items remain in the internal acquisition index
for later checking; no venue is labeled predatory by heuristic inference.
"""
from __future__ import annotations
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
RULES=ROOT/"data/venue-standards.json"

AI=re.compile(r"\b(?:generative(?:\s+artificial)?\s+ai|chatgpt|genai|copilot|llms?|large language models?|artificial intelligence|ai[- ](?:assisted|based|powered|generated|enabled)|human[- ]ai|\bAI\b)\b",re.I)
FOCUS=re.compile(r"(?:\battention\b|attentional|sustained focus|distraction|interruptions?|task[- ]switching|multitask|cognitive (?:offload|effort|engagement|load|control|autonomy|process)|critical thinking|metacognit|self[- ]regulat|reasoning|human[- ]ai collaboration|cognitive dependency|ai dependenc|learning (?:engagement|strategy|strategies)|pedagogical scaffolding|digital well[- ]?being|digital distraction|attention economy|epistemic agency)",re.I)
ADJACENT=re.compile(r"(?:attention|attentional|digital distraction|interruptions?|notification|task[- ]switching|multitask|focus|cognitive control|self[- ]regulat)",re.I)
ENGINEERING=re.compile(r"(?:cross[- ]attention|transformer|gru|tabtransformer|image recognition|object detection|satellite|convolutional|computer vision)",re.I)
PREPRINT=re.compile(r"(?:arxiv|research square|zenodo|osf|preprint|ssrn|ed.?arxiv)",re.I)
UNRESOLVED=re.compile(r"^(?:crossref|openalex|unknown|unavailable|repository|no venue|not available)$",re.I)
 
def normal(s):
    return re.sub(r"[^a-z0-9]+"," ",str(s or "").lower()).strip()

def standards():
    return json.loads(RULES.read_text(encoding="utf-8"))

def venue_class(venue,rules=None):
    rules=rules or standards()
    name=normal(venue)
    if not name or UNRESOLVED.match(name):
        return "unverified"
    if PREPRINT.search(name):
        return "preprint"
    for level in ("priority","specialist"):
        for names in (rules.get(level) or {}).values():
            if name in {normal(j) for j in names}:
                return level
    return "unverified"

def topic_class(record):
    title=str(record.get("title") or "")
    abstract=str(record.get("abstract_text") or "")
    text=title+" "+abstract
    direct=bool(AI.search(text))
    focused=bool(FOCUS.search(text))
    attention=bool(ADJACENT.search(text))
    # A code paper using 'cross-attention' is not human-attention research.
    if ENGINEERING.search(title) and not FOCUS.search(title.replace("cross-attention","").replace("Cross-Attention","")) and not re.search(r"participants|students|users|human attention|human cognition",abstract,re.I):
        return "off_topic"
    if direct and focused and (FOCUS.search(title) or (len(abstract)>160 and FOCUS.search(abstract))):
        return "direct"
    if not direct and attention and ADJACENT.search(title):
        return "adjacent"
    return "uncertain"

def screen(record,rules=None):
    if record.get("kind")!="scholarly":
        # Nonacademic screening belongs to the news-source authenticity check.
        return {"decision":"editorial","venue_level":"not_applicable","topic":"not_applicable","reason":"nonacademic"}
    venue=venue_class(record.get("venue"),rules)
    topic=topic_class(record)
    if record.get("research_type")=="conceptual_framework" and "editorially verified" in str(record.get("source") or "").lower():
        return {"decision":"include","venue_level":venue,"topic":"direct","reason":"verified_primary_conceptual_work"}
    if topic=="off_topic":
        return {"decision":"hold","venue_level":venue,"topic":topic,"reason":"computational_attention_not_human_attention"}
    if topic=="uncertain":
        return {"decision":"hold","venue_level":venue,"topic":topic,"reason":"topical_fit_needs_review"}
    if venue=="preprint":
        return {"decision":"hold","venue_level":venue,"topic":topic,"reason":"preprint_requires_article_screen"}
    if venue=="unverified":
        return {"decision":"hold","venue_level":venue,"topic":topic,"reason":"publication_venue_unverified"}
    return {"decision":"include","venue_level":venue,"topic":topic,"reason":"field_venue_and_explicit_relevance"}

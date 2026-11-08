"""Original, deterministic editorial illustrations for already-public readings.

Run ``python scripts/build_public.py`` for the full publication-gated loop, or
``python scripts/article_art.py --report /tmp/art.json --contact-sheet /tmp/art.html``
to regenerate the existing public projection and inspect its covers. No network,
API key, image service, source figures, timestamps, or third-party code is used.

The renderer composes source-grounded subjects and contextual relationships.
Identity hashes never alter geometry. Ungrounded or repeated candidates carry
review-needed metadata without a cover. These are illustrations,
not empirical graphics. build_visuals.visual_spec remains the evidence layer.

Optional data/article-art-overrides.json schema::

    {"version": 1, "overrides": {"doi:10.1234/example": {
      "src": "assets/editorial-covers/example.webp",
      "alt": "A hand rebuilding a bridge beside a closed screen.",
      "concept": "Reconstructing an idea after assistance is removed.",
      "provenance": "Original editorial art; not a source figure."
    }}}

Keys use canonical_identity(). Overrides are validated local raster assets, never
remote URLs; invalid manifests fail before publication. Generated files are
content-addressed and written only when changed. No auto-deletion occurs, so an
older deployed public payload can safely coexist with a subsequent build.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
import unicodedata
import struct
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
RENDERER_VERSION = "editorial-svg-2"
RED, INK, PAPER, MUTED = "#E00122", "#171714", "#F4F0E8", "#D8D1C5"
MAX_SVG_BYTES = 32_000
MAX_OVERRIDE_BYTES = 2_000_000
GENERATED_DIR = "assets/article-art"


def normalized(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def canonical_identity(record: dict) -> str:
    """DOIs are case-insensitive; URL paths remain case-sensitive.

    Tracking/fragment noise is removed, but meaningful URL query parameters stay.
    Title fallback is explicit and hashed: title content is never a filesystem path.
    """
    doi = normalized(record.get("doi"))
    if doi:
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
        return "doi:" + unquote(doi).lower()
    url = normalized(record.get("url"))
    if url:
        p = urlsplit(url)
        if p.scheme.lower() not in ("http", "https") or not p.hostname or p.username or p.password:
            raise ValueError("Article art requires a canonical HTTP(S) source URL or DOI")
        if p.hostname.lower() in ("doi.org", "dx.doi.org"):
            return "doi:" + unquote(p.path.lstrip("/")).lower()
        host = p.hostname.lower()
        if ":" in host:
            host = "[" + host + "]"
        port = p.port
        if port and (p.scheme.lower(), port) not in (("https", 443), ("http", 80)):
            host += ":" + str(port)
        query = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                       if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid"))
        return "url:" + urlunsplit((p.scheme.lower(), host, p.path or "/", urlencode(query), ""))
    title = normalized(record.get("title"))
    if not title:
        raise ValueError("Article art requires a DOI, URL, or nonempty title")
    return "title:" + hashlib.sha256(title.encode()).hexdigest()


def public_inputs(record: dict) -> dict:
    """Only public editorial text informs art; dates, findings, stats and IDs do not.

    Findings are deliberately excluded as instructions for shapes: e.g. a reported
    effect must not silently become a directional chart in editorial illustration.
    A digest checksum still invalidates the cached asset when public text changes.
    """
    reading = record.get("reading") or {}
    digest = reading.get("digest") or {}
    return {"title": normalized(record.get("title")),
            "idea": normalized(digest.get("idea")),
            "explain": normalized(digest.get("explain")),
            "overview": normalized(reading.get("overview")) if not digest else "",
            "source_context": normalized(" ".join(str(v or "") for v in (digest.get("approach"), reading.get("methods"), record.get("abstract_text"), digest.get("explain"), reading.get("overview"), (digest.get("longform") or {}).get("reasoning"), (digest.get("longform") or {}).get("examples")))),
            "tags": sorted({normalized(t) for t in digest.get("tags", []) if isinstance(t, str)}),
            "content_revision": hashlib.sha256(json.dumps({"digest": digest,
                "overview": reading.get("overview", "")}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}


# Phrases describe subject matter, never a result, causal direction, or effect size.
# Higher specificity wins equal scores; ordering is stable, not hash-dependent.
MOTIFS = {
    "reconstruction": (("without ai", "no-ai", "reconstruct", "staged use", "gradual release", "independent no"),
        "a hand setting a plank across an unfinished bridge beside a closed screen", "rebuilding a skill when assistance is removed"),
    "offloading": (("offload", "outsourc", "delegat", "substitution", "deskilling"),
        "a small crane moving loose pages between an open notebook and a screen", "the transfer of cognitive work between a person and a tool"),
    "verification": (("critical thinking", "verif", "hallucinat", "reliab", "judgment", "judgement", "accountab"),
        "a magnifying glass held over branching paper trails", "examining and checking ideas rather than accepting an answer at face value"),
    "reflection": (("metacognit", "reflect", "self-regulat", "calibration", "monitoring", "cognitive mirror"),
        "an open notebook facing a standing mirror with a turned page", "looking back at one's own thinking and learning choices"),
    "collaboration": (("collaborat", "co-intelligence", "co-creat", "shared control", "peer-likeness", "ai peer", "co-regulation", "shared decisions", "parenting"),
        "two different hands bringing interlocking pieces together above an open book", "negotiating a shared task between human and machine participants"),
    "interruptions": (("distract", "interrupt", "notification", "disruption", "smartphone", "multitask"),
        "a reading lamp and open book surrounded by incoming envelopes and a phone", "attention meeting competing digital invitations"),
    "switching": (("task switching", "switch readiness", "switching between", "switching in"),
        "a railway switch dividing into two tracks that end at different workbooks", "moving attention between competing tasks"),
    "autonomy": (("autonom", "agency", "agential", "intention", "blocking", "focus mode", "focus filter", "pause apps", "user-controlled", "exclude apps"),
        "a hand adjusting a shutter between a phone and a quiet open book", "choosing what reaches one's attention"),
    "governance": (("governance", "consent", "consenting", "democracy", "surveillance", "policy", "integrity", "rules", "elections", "content moderation"),
        "a key held beside an open gate and a folded document", "deciding who has permission to act and under which rules"),
    "language": (("language education", "language instruction", "foreign language", "efl", "l2 ", "translanguag", "terminology", "language and vision"),
        "two speech-shaped paper cutouts joined by a folded bridge", "working between language, expression, and understanding"),
    "writing": (("writing", "composing", "authorship", "ownership", "is it mine", "lesson plan"),
        "a large pen touching a sheet that unfolds from a screen into a notebook", "the boundary between generated material and a person's own composition"),
    "creative": (("creative", "creativity", "art education", "innovation", "imagination"),
        "a brush and scissors opening a paper window onto an unfinished shape", "making and revising an idea with tools"),
    "music": (("music", "singing", "vocal", "listening"),
        "headphones suspended above a tuning fork and an open practice book", "listening, practice, and the mediation of musical attention"),
    "wellbeing": (("wellbeing", "well-being", "stress", "coping", "insomnia", "sleep", "emotional", "socio-emotional"),
        "a quiet chair and a growing plant beside a tilted, resting phone", "the space between digital demands and personal wellbeing"),
    "memory": (("transactive memory", "working memory", "remember", "recall", "cognitive load", "mental effort", "cognitive overload"),
        "an open filing drawer with paper bundles balanced beside a notebook", "the work of holding, retrieving, and organizing information"),
    "scaffolding": (("scaffold", "support-dependence", "supporting independent", "support mechanisms"),
        "a temporary scaffold standing around a stairway made of books", "the relationship between support and a learner's own structure"),
    "inquiry": (("inquiry", "problem-solving", "problem solving", "mathemat", "math learning", "learning to code", "scientific"),
        "a lens, a loose puzzle piece, and an unfinished path across an open workbook", "working through a problem rather than only collecting its answer"),
    "attention": (("sustained attention", "attention economy", "attending", "attentional", "attention", "concentration"),
        "a large aperture focusing a pool of light onto a single open book", "selecting a place for attention amid a wider field"),
    "learning": (("learning", "literacy", "education", "students", "teacher", "engagement"),
        "an open book becoming a short stairway beside a tool box", "building understanding through practice and the use of tools"),
    "reading": ((), "a folded page, an open book, and a compass-like reading lens", "exploring the source's subject through reading"),
}


# A second literal subject, independent of the primary metaphor. These cues are
# editorial nouns in public text, not statistical values or inferred findings.
SUBJECTS = {
    "craft": (("complex problem-solving", "vocational"), "a tool box with a separate hand tool", "workbench"),
    "math": (("mathemat", "math learning", "stem "), "a compass and an unfinished geometric puzzle", "workbench"),
    "writing": (("writing", "composing", "authorship", "ownership", "mine or not"), "a pen crossing a folded manuscript", "studio"),
    "language": (("efl", "l2 ", "foreign language", "language instruction", "terminology", "translanguag"), "two folded speech-shaped pages", "folded_paper"),
    "music": (("music", "vocal", "singing"), "a tuning fork and headphones", "studio"),
    "code": (("programming", "learning to code", "computational thinking"), "a hinged computer screen", "workbench"),
    "art": (("art education", "creative agency", "visual art"), "a brush opening a paper aperture", "studio"),
    "sleep": (("insomnia", "sleep", "rest"), "a crescent moon behind a shuttered window", "night_window"),
    "games": (("game-based", "game based", "gaming"), "a controller and a loose puzzle piece", "digital_window"),
    "dashboard": (("dashboard",), "a viewing window and an adjustable lens", "digital_window"),
    "policy": (("governance", "policy", "accountability", "consent", "democracy"), "a key beside a folded agreement", "threshold"),
    "integrity": (("cheating", "integrity", "responsib", "rigor", "commitment"), "a seal and an unclosed document", "threshold"),
    "teacher": (("teacher", "teaching", "educator", "lesson plan", "instruction"), "a book resting on a teaching stand", "classroom"),
    "medical": (("medical", "clinical", "adhd", "pediatric", "neuropsych"), "a blank clipboard beside a waiting chair", "quiet_room"),
    "aging": (("older adults", "aging", "companionship"), "two chairs facing an open window", "quiet_room"),
    "stress": (("technostress", "stress", "emotional", "coping", "well-being", "wellbeing"), "a plant beside a folded resting screen", "quiet_room"),
    "agency": (("autonom", "agency", "agential", "intention", "decision-making", "human agency"), "a hand holding a small steering lever", "threshold"),
    "blocking": (("blocking", "block distracting", "restriction", "hard blocking"), "a closed shutter with a movable latch", "threshold"),
    "filtering": (("focus filter", "filter notifications", "filtering"), "a sliding paper filter in front of a window", "digital_window"),
    "pause": (("focus mode", "pause apps", "pause, schedule", "manage interruptions"), "a resting phone in a small cradle", "quiet_room"),
    "phone": (("smartphone", "phone use", "social-media", "social media", "multitask", "notification"), "a phone surrounded by folded envelopes", "digital_window"),
    "review": (("systematic review", "critical review", "narrative review", "literature review", "synthesis", "manifesto"), "several source books standing on a shelf", "library"),
    "measurement": (("scale", "validation", "assessment", "variability", "calibration"), "a pair of dividers examining a blank card", "workbench"),
    "interview": (("accounts", "qualitative", "perspectives", "grounded theory", "interview"), "two seated figures facing an open interview notebook", "folded_paper"),
    "feedback": (("feedback", "prompting", "prompt strategy", "chat", "help-seeking"), "a paper loop returning to an open envelope", "folded_paper"),
    "offload": (("offload", "outsourc", "delegat", "substitution", "deskilling"), "a bundle of pages held by a small hook", "workbench"),
    "metacognition": (("metacognit", "self-regulat", "reflect", "monitoring"), "a pocket mirror beside an open page", "quiet_room"),
    "effort": (("cognitive load", "mental effort", "overload", "cognitive effort"), "a handle carrying a bundle of paper", "workbench"),
    "literacy": (("literacy", "familiarity", "knowledge", "understanding"), "an open field guide with a magnifying tab", "library"),
    "critical": (("critical thinking", "judgment", "judgement", "uncertain", "trust"), "a magnifier crossing an unmarked manuscript", "workbench"),
    "support": (("scaffold", "support", "capability", "engagement"), "a small trestle holding an unfinished plank", "workbench"),
    "inequality": (("unequal", "inequal", "equitable"), "a doorway with two different-height steps", "threshold"),
    "practice": (("learning", "student", "education", "practice"), "an unfinished exercise book and a pencil", "classroom"),
}

# Specific research settings and tasks outrank broad themes. These are literal
# subject cues, not labels inferred from statistical results.
SUBJECTS.update({
    "knowledge": (("knowledge innovation", "knowledge production"), "an open notebook with interlocking folded paper tabs", "library"),
    "fact_check": (("hallucinations", "reliable generative"), "a document assembled from separate paper pieces under inspection", "workbench"),
    "making": (("co-creators", "co-creation", "co-creating"), "two hands assembling an unfinished paper shape", "studio"),
    "feedback_literacy": (("feedback literacy",), "an opened reply envelope beside a reading lens", "folded_paper"),
    "experiment": (("randomized controlled", "randomised controlled"), "blank task cards being separated between two work trays", "workbench"),
    "lesson": (("lesson planning", "lesson plan"), "an open lesson planner with removable paper tabs", "classroom"),
    "ecology": (("ecology", "manifesto"), "a branching plant growing around a reading window", "quiet_room"),
    "trust": (("trust in generative", "ai trust", "trust reduces"), "two hands holding opposite ends of a loose bridge", "workbench"),
    "doctoral": (("doctoral", "dissertation"), "a bound dissertation with a graduation cap", "library"),
    "hci": (("hci research", "human-computer interaction"), "a hand-operated pointer beside a screen", "digital_window"),
    "surveillance": (("surveillance", "classify emotions", "emotion recognition"), "an eye-shaped camera beside a privacy shutter", "threshold"),
    "consent": (("consenting", "consent", "i agree"), "an unsigned agreement and a pen held above it", "threshold"),
    "network": (("internet", "ai agents", "agentiality"), "a gate within an interconnected web", "threshold"),
    "science": (("scientific inquiry", "scientific reasoning"), "a microscope and an open observation notebook", "workbench"),
    "ownership": (("ownership", "mine or not mine", "authorship"), "two hands reaching for a single manuscript", "studio"),
    "time": (("wait", "switch readiness", "response time", "intention tracking"), "an hourglass beside an unfinished task", "workbench"),
    "physical": (("physical education", "sports", "exercise"), "a whistle and a folded training plan", "classroom"),
    "vision": (("language and vision", "visual perception", "eye-tracking", "eye tracking"), "an eye-shaped viewing window", "digital_window"),
    "eap": (("eap writing", "academic writing"), "a fountain pen and a bound manuscript", "studio"),
    "terminology": (("terminology", "vocabulary"), "a ring of blank index cards", "folded_paper"),
    "preservice": (("preservice", "student teachers", "teacher education"), "a teaching stand beside a graduation cap", "classroom"),
    "children": (("children", "adolescents", "adolescent", "pediatric"), "a small school chair and an open exercise book", "classroom"),
    "workplace": (("workplace", "occupational", "professional learning", "work tasks"), "a work desk with a hinged screen", "workbench"),
    "explanation": (("explainable", "explainability"), "an open mechanical box with a viewing flap", "digital_window"),
    "multimodal": (("multimodal",), "a folded composition combining a page and a picture frame", "studio"),
    "framework": (("framework", "conceptual", "theoretical", "scaffolding", "scaffolding, substitution"), "an unfinished structure on temporary supports", "workbench"),
    "undergraduate": (("undergraduate", "university students", "college students"), "a graduation cap beside an exercise book", "classroom"),
    "chatbot": (("chatgpt", "chatbot", "conversational", "siri", "ai assistant"), "a screen holding an open conversation bubble", "digital_window"),
    "routes": (("switching", "switch readiness"), "a branching railway switch", "workbench"),
    "aperture": (("sustained attention", "attention economy", "attending", "cognitive science"), "an adjustable optical aperture", "workbench"),
    "market": (("political economy", "attention economy"), "a market awning above a viewing window", "threshold"),
    "ballot": (("elections", "voting", "democracy"), "a ballot box with an unmarked folded card", "threshold"),
    "parenting": (("parent", "family"), "a larger and smaller open book side by side", "classroom"),
    "apps": (("apps", "app permissions", "app and website", "focus filters", "ios", "android"), "a phone with separately shuttered app windows", "digital_window"),
    "comparison": (("performance and metacognition", "support-dependence discrepancy", "dependent and autonomous"), "two separated work surfaces connected by a loose paper ribbon", "workbench"),
})

# All noun choices retain the exact source phrase and field that licensed them.
# Generic generated questions and tags cannot supply the required context.
def contextual_subjects(inputs: dict, spec: dict) -> list[dict]:
    ranked = []
    for order, (name, (cues, _, _)) in enumerate(SUBJECTS.items()):
        hits = matches(inputs["title"], cues)
        field = "title"
        if not hits:
            hits = matches(inputs.get("source_context", ""), cues)
            field = "source_context"
        if not hits:
            continue
        generic = name in {"practice", "support", "literacy", "critical", "metacognition", "effort", "feedback", "offload"}
        score = (100 if field == "title" else 0) + max(map(len, hits)) - (38 if generic else 0)
        if name in {"knowledge", "fact_check", "making", "feedback_literacy", "experiment", "lesson", "ecology", "trust", "doctoral", "hci", "surveillance", "consent", "network", "science", "ownership", "time", "physical", "vision", "eap", "terminology", "preservice", "children", "workplace", "explanation", "multimodal", "comparison", "framework", "undergraduate", "routes", "market", "ballot", "parenting", "apps"}:
            score += 24
        ranked.append((score, -order, {"subject": name, "field": field, "phrases": sorted(hits)}))
    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
    # Some vocabulary entries deliberately share a glyph. Do not count them as
    # different objects, nor let them fake a unique visual pair.
    equivalent = {}
    selected, seen = [], set()
    for _, _, item in ranked:
        glyph = equivalent.get(item["subject"], item["subject"])
        if glyph in seen:
            continue
        seen.add(glyph)
        selected.append(item)
        if len(selected) == 2:
            break
    return selected


# Avoid echoing the main metaphor when a different explicit subject is available.
ECHO_SUBJECTS = {
    "offloading": {"offload"}, "reflection": {"metacognition"}, "verification": {"critical"},
    "wellbeing": {"stress"}, "language": {"language"}, "writing": {"writing"},
    "music": {"music"}, "autonomy": {"agency"}, "governance": {"policy"},
    "scaffolding": {"support"}, "interruptions": {"phone"}, "memory": {"effort"},
    "learning": {"practice"}, "creative": {"art"},
}


def second_subject(inputs: dict, family: str) -> tuple[str, str, list[str]]:
    title = inputs["title"]
    prose = " ".join(inputs[k] for k in ("idea", "explain", "overview"))
    ranked = []
    for index, (name, (cues, _, _)) in enumerate(SUBJECTS.items()):
        if name in ECHO_SUBJECTS.get(family, set()):
            continue
        th, dh = matches(title, cues), matches(prose, cues)
        if th or dh:
            # An explicit title subject wins generic words introduced by a digest.
            score = (100 if th else 0) + max((len(x) for x in th + dh), default=0)
            if name in ("practice", "support", "critical", "metacognition", "literacy"):
                score -= 35
            ranked.append((score, -index, name, th, dh))
    if not ranked:
        return "reading", "topic_fallback", []
    _, _, name, th, dh = max(ranked)
    return name, "title" if th else "digest", sorted(set(th + dh))


def matches(text: str, phrases: tuple) -> list[str]:
    text = normalized(text).lower().replace("–", "-").replace("—", "-").replace("‐", "-")
    stems = {"offload", "outsourc", "delegat", "reconstruct", "verif", "hallucinat", "reliab", "accountab",
             "metacognit", "reflect", "self-regulat", "collaborat", "co-creat", "distract", "interrupt",
             "autonom", "agential", "translanguag", "responsib", "neuropsych", "pedagog", "independen", "mathemat", "multitask"}
    found = []
    for phrase in phrases:
        pattern = r"(?<!\w)" + re.escape(phrase) + ("" if phrase in stems or phrase.endswith(" ") else r"(?:s|es)?(?!\w)")
        for match in re.finditer(pattern, text):
            # Negated topic mentions cannot silently become the depicted action.
            prefix = text[max(0, match.start()-65):match.start()]
            if re.search(r"\b(?:not|never|without|rather than|instead of|avoid)\b[^.;:!?]{0,55}$", prefix) and phrase not in {"without ai", "no-ai"}:
                continue
            found.append(phrase)
            break
    return found


def choose_concept(inputs: dict) -> dict:
    title = inputs["title"]
    prose = " ".join(inputs[k] for k in ("idea", "explain", "overview"))
    ranked = []
    for index, (name, (phrases, objects, meaning)) in enumerate(MOTIFS.items()):
        title_hits, digest_hits = matches(title, phrases), matches(prose, phrases)
        # Prefer specific title subjects over generic generated question templates.
        score = sum(8 + min(len(p), 20) / 10 for p in title_hits)
        score += sum(2 + min(len(p), 20) / 30 for p in digest_hits)
        if name == "learning":
            score *= .35
        if name == "attention":
            score *= .65
        ranked.append((score, -index, name, title_hits, digest_hits))
    score, _, family, title_hits, digest_hits = max(ranked)
    basis = "title_and_digest" if title_hits and digest_hits else "title" if title_hits else "digest"
    if not score:
        tag_text = " ".join(inputs["tags"])
        family = next((name for name, (phrases, _, _) in MOTIFS.items() if matches(tag_text, phrases)), "reading")
        basis = "topic_fallback"
    objects, meaning = MOTIFS[family][1:]
    text = (title + " " + prose).lower()
    # These secondary subjects materially change objects/placement, not just color.
    context = next((name for name, cues in (
        ("classroom", ("student", "education", "learning", "teacher", "classroom")),
        ("workplace", ("workplace", "professional", "worker", "work tasks")),
        ("mobile", ("phone", "app ", "digital", "notification")),
        ("language", ("language", "writing", "terminology")),
    ) if any(cue in text for cue in cues)), "reading")
    relation = next((name for name, cues in (
        ("rebuild", ("reconstruct", "without ai", "no-ai", "independen", "gradual release")),
        ("shared", ("collaborat", "co-regulat", "shared", "peer")),
        ("question", ("critical", "verif", "trust", "judgment", "uncertain")),
        ("protected", ("block", "autonom", "intention", "filter", "pause")),
    ) if any(cue in text for cue in cues)), "open")
    subject, subject_basis, subject_cues = second_subject(inputs, family)
    subject_object, setting = SUBJECTS[subject][1:] if subject in SUBJECTS else ("a loose source page", "reading_room")
    if relation == "open" and re.search(r"\b(?:between|contrast|disconnect|or|different)\b", text):
        relation = "comparison"
    arrangement = {"shared": "shared_table", "question": "inspection", "protected": "threshold",
                   "rebuild": "separated_support", "comparison": "facing_panels", "open": "side_by_side"}[relation]
    title_label = f'For “{title}”, ' if title else "For this reading, "
    concept = title_label + objects + " evokes " + meaning + "."
    if basis == "topic_fallback":
        concept = "Topic-based illustration: " + title_label + objects + "; " + meaning + "."
    concept += " Paired with " + subject_object + ", the scene connects that metaphor to the article's " + subject.replace("_", " ") + " theme."
    signature = "|".join((family, subject, context, relation, setting))
    spec = {"motif": family, "semantic_basis": basis, "context": context, "relation": relation,
            "secondary_subject": subject, "secondary_basis": subject_basis, "secondary_cues": subject_cues,
            "setting": setting, "arrangement": arrangement, "semantic_signature": signature,
            "uniqueness": "source_theme_composition",
            "matched_cues": sorted(set(title_hits + digest_hits)), "concept": concept,
            "alt": "Editorial illustration of " + objects + ", paired with " + subject_object + ". Not a depiction of study results."}
    subjects = contextual_subjects(inputs, spec)
    spec["source_grounding"] = subjects
    spec["visual_subjects"] = [x["subject"] for x in subjects]
    # No source context means no invented contextual artwork. The caller exposes
    # review state without replacing it with a reused topic image.
    spec["review_reasons"] = [] if len(subjects) >= 2 else ["insufficient_specific_context"]
    spec["semantic_signature"] = "|".join([family] + spec["visual_subjects"])
    spec["uniqueness"] = "contextual_object_pair"
    if len(subjects) >= 2:
        a, b = (SUBJECTS[x["subject"]][1] for x in subjects)
        spec["alt"] = "Editorial illustration: " + a + " with " + b + ". Not a depiction of study results."
        spec["concept"] = title_label + a + " and " + b + " frame " + meaning + "."
        if set(spec["visual_subjects"]) == {"apps", "pause"}:
            spec["alt"] = "Editorial illustration of a phone resting sideways in a cradle with a pause symbol. Not a depiction of study results."
    return spec



class Canvas:
    """A tiny closed SVG vocabulary: no user markup, fonts, refs, or embedded assets."""
    def __init__(self):
        self.parts = []

    def tag(self, name, **attrs):
        safe = " ".join(f'{k.replace("_", "-")}="{html.escape(str(v), quote=True)}"' for k, v in attrs.items())
        self.parts.append(f"<{name} {safe}/>")

    def path(self, d, fill=INK, stroke="none", width=3, **attrs):
        self.tag("path", d=d, fill=fill, stroke=stroke, stroke_width=width, **attrs)

    def line(self, x1, y1, x2, y2, color=INK, width=4, **attrs):
        self.tag("path", d=f"M{x1} {y1} L{x2} {y2}", fill="none", stroke=color, stroke_width=width,
                 stroke_linecap="round", **attrs)

    def rect(self, x, y, w, h, fill=INK, **attrs):
        self.tag("rect", x=x, y=y, width=w, height=h, fill=fill, **attrs)

    def circle(self, x, y, r, fill=INK, **attrs):
        self.tag("circle", cx=x, cy=y, r=r, fill=fill, **attrs)

    def group(self, x=0, y=0, scale=1, rotate=0):
        self.parts.append(f'<g transform="translate({x} {y}) rotate({rotate}) scale({scale})">')

    def end(self):
        self.parts.append("</g>")


def page(c, x, y, scale=1, angle=0, color=PAPER):
    c.group(x, y, scale, angle)
    c.path("M0 0 H116 L150 34 V182 H0 Z", color, INK, 4)
    c.path("M116 0 V34 H150", "none", INK, 3)
    # Fold and blank margins are visual objects, not fake text or data rows.
    c.line(18, 151, 127, 151, MUTED, 3)
    c.end()


def book(c, x, y, scale=1, angle=0):
    c.group(x, y, scale, angle)
    c.path("M0 22 Q70 -2 140 27 Q210 -2 280 22 V160 Q211 139 140 163 Q70 139 0 160 Z", INK)
    c.path("M8 12 Q75 -9 140 18 Q205 -9 272 12 V148 Q205 125 140 151 Q75 125 8 148 Z", PAPER, INK, 4)
    c.path("M140 18 V151 M25 29 Q75 15 121 32 M159 32 Q207 16 254 29", "none", INK, 3)
    c.path("M217 6 V71 L230 58 L243 72 V9 Z", RED)
    c.end()


def screen(c, x, y, scale=1, angle=0, closed=False):
    c.group(x, y, scale, angle)
    if closed:
        c.path("M0 65 H210 L240 92 H-20 Z", INK)
        c.line(8, 77, 206, 77, PAPER, 3)
    else:
        c.rect(0, 0, 210, 145, INK, rx=9)
        c.rect(13, 13, 184, 116, PAPER, rx=2)
        c.path("M-18 146 H228 L242 166 H-30 Z", INK)
        c.path("M70 48 L47 70 L70 92 M140 48 L163 70 L140 92 M113 40 L97 100", "none", RED, 7)
    c.end()


def phone(c, x, y, scale=1, angle=0):
    c.group(x, y, scale, angle)
    c.rect(0, 0, 95, 165, INK, rx=16)
    c.rect(8, 15, 79, 129, PAPER, rx=5)
    c.rect(32, 6, 31, 5, PAPER, rx=2)
    c.circle(48, 154, 4, PAPER)
    c.path("M34 52 L62 52 L62 92 L34 92 Z", RED)
    c.end()


def hand(c, x, y, scale=1, angle=0, color=INK):
    c.group(x, y, scale, angle)
    c.path("M-130 35 L-8 35 Q11 35 20 16 L47 -29 Q55 -42 65 -35 Q74 -29 67 -15 L57 5 L119 4 Q139 4 139 17 Q139 28 120 29 L86 29 L133 30 Q150 31 149 43 Q148 54 130 54 L84 54 L126 56 Q143 58 140 69 Q138 80 120 80 L79 80 L112 83 Q127 86 121 97 Q117 106 97 105 L37 104 Q10 103 -4 87 L-130 87 Z", color, PAPER, 2)
    c.line(-12, 39, -12, 86, PAPER if color == INK else INK, 3)
    c.end()


def envelope(c, x, y, scale=1, angle=0, color=PAPER):
    c.group(x, y, scale, angle)
    c.rect(0, 0, 102, 68, color, stroke=INK, stroke_width=3)
    c.path("M0 0 L51 37 L102 0 M0 68 L35 29 M102 68 L67 29", "none", INK, 3)
    c.end()


def lens(c, x, y, scale=1, angle=0):
    c.group(x, y, scale, angle)
    c.circle(0, 0, 90, PAPER, stroke=INK, stroke_width=13)
    c.circle(0, 0, 72, "none", stroke=RED, stroke_width=4)
    c.path("M59 67 L146 162", "none", INK, 29, stroke_linecap="round")
    c.path("M-46 -31 Q-32 -56 -6 -58", "none", MUTED, 8, stroke_linecap="round")
    c.end()


def plant(c, x, y, scale=1):
    c.group(x, y, scale)
    c.path("M0 0 L16 83 H95 L111 0 Z", RED)
    c.path("M54 0 Q30 -52 61 -130 M56 -37 Q5 -41 4 -85 Q50 -88 56 -37 M55 -70 Q100 -122 123 -88 Q108 -52 55 -70", "none", INK, 7)
    c.end()


def draw_setting(c: Canvas, spec: dict):
    """Semantic settings use different negative space, framing, and surfaces."""
    setting = spec["setting"]
    if setting == "library":
        c.path("M0 0 H1200 V122 H166 V760 H0 Z", RED)
        c.path("M878 159 H1154 V654 H878 Z", MUTED)
        c.line(872, 650, 1166, 650, INK, 9)
    elif setting == "studio":
        c.path("M54 54 H1147 V706 H54 Z", "none", RED, 21)
        c.path("M857 55 L1145 55 L1145 705 L1021 705 Z", RED)
    elif setting == "folded_paper":
        c.path("M0 0 H883 L1062 183 L939 760 H0 Z", PAPER)
        c.path("M883 0 L1062 183 L940 760 H1200 V0 Z", RED)
        c.path("M883 0 V193 L1062 183", "none", INK, 3)
        c.line(74, 687, 847, 687, INK, 3)
    elif setting == "night_window":
        c.rect(0, 0, 1200, 760, INK)
        c.rect(58, 63, 1084, 634, PAPER)
        c.path("M789 64 H1142 V440 H789 Z", RED)
        c.circle(1008, 191, 85, PAPER)
        c.circle(1048, 162, 79, RED)
        c.line(793, 344, 1143, 344, INK, 8)
    elif setting == "digital_window":
        c.rect(57, 60, 1086, 635, PAPER, stroke=INK, stroke_width=8, rx=18)
        c.rect(62, 65, 1076, 48, INK)
        for x in (87, 110, 133):
            c.circle(x, 89, 5, PAPER)
        c.path("M900 117 H1137 V690 H900 Z", RED)
    elif setting == "threshold":
        c.path("M814 0 H1200 V760 H814 V614 H1087 V144 H814 Z", INK)
        c.path("M1079 144 L939 229 V760 H1079 Z", RED)
        c.path("M0 683 H815 L940 760 H0 Z", MUTED)
    elif setting == "classroom":
        c.path("M0 0 H1200 V129 H0 Z", INK)
        c.path("M0 129 H166 V760 H0 Z", RED)
        c.path("M869 185 H1125 V642 H869 Z", "none", INK, 6)
        c.line(849, 655, 1144, 655, INK, 10)
    elif setting == "quiet_room":
        c.path("M822 0 H1200 V760 H1100 V113 H822 Z", RED)
        c.path("M843 144 H1100 V507 H843 Z", MUTED)
        c.line(971, 145, 971, 506, PAPER, 7)
        c.line(844, 316, 1098, 316, PAPER, 7)
        c.path("M0 648 H1200 V760 H0 Z", MUTED)
    elif setting == "workbench":
        c.path("M0 0 H1200 V95 H0 Z", RED)
        c.path("M0 642 L1200 603 V760 H0 Z", INK)
        c.path("M828 187 L1114 151 L1157 530 L870 567 Z", MUTED)
    else:
        c.path("M0 0 H137 V760 H0 Z", RED)
        c.path("M0 664 H1200 V760 H0 Z", MUTED)
    if spec["arrangement"] == "facing_panels":
        c.line(823, 163, 823, 599, RED, 7)
    elif spec["arrangement"] == "shared_table":
        c.path("M94 603 Q550 556 1126 606 V630 H94 Z", MUTED)
    elif spec["arrangement"] == "separated_support":
        c.path("M818 566 H873 M1014 566 H1122", "none", RED, 14)


def draw_subject(c: Canvas, spec: dict, *, x=966, y=None, scale=.77):
    subject = spec["secondary_subject"]
    # Each subject is a different large object assembly. Its relationship to the
    # main metaphor is a two-subject editorial composition, not an effect diagram.
    y = y if y is not None else {"inspection": 300, "shared_table": 427, "threshold": 370,
         "separated_support": 281, "facing_panels": 377, "side_by_side": 354}[spec["arrangement"]]
    c.group(x, y, scale)
    if subject == "knowledge":
        book(c,-139,27,.99)
        c.path("M-96 -131 H-6 V-91 H35 V-4 H-96 Z",RED,INK,5)
        c.path("M20 -131 H115 V-4 H58 V-57 H20 Z",PAPER,INK,6)
        c.path("M-96 -131 L-60 -95 H-96 Z",PAPER,INK,4)
    elif subject == "fact_check":
        c.path("M-112 -141 H26 V-30 H-21 V154 H-112 Z",PAPER,INK,7)
        c.path("M47 -129 H122 V-12 H76 V160 H1 V-12 H47 Z",RED,INK,7)
        lens(c,70,77,.63,12)
    elif subject == "making":
        c.path("M-81 -43 H21 V-77 H91 V25 H50 V103 H-81 Z", RED, INK, 7)
        hand(c,-133,80,.58,-20)
        hand(c,139,-99,.58,160,RED)
    elif subject == "feedback_literacy":
        envelope(c,-143,48,1.65,-8)
        lens(c,18,-63,.86,5)
    elif subject == "experiment":
        page(c,-67,-145,.7,-11)
        c.path("M-159 56 H-14 V151 H-159 Z M22 56 H168 V151 H22 Z",PAPER,INK,9)
        c.path("M-39 12 L-88 67 M50 12 L97 67", "none",RED,15)
    elif subject == "lesson":
        book(c,-143,-53,1)
        for yy in (-34,12,58):
            c.rect(72,yy,91,27,RED,stroke=INK,stroke_width=3)
        c.path("M-107 -71 V133 M-75 -71 V133", "none", INK, 5)
    elif subject == "ecology":
        c.rect(-99,-128,198,277,PAPER,stroke=INK,stroke_width=9)
        plant(c,53,75,1.34)
        c.path("M-132 140 Q-195 -13 -108 -84", "none", RED, 14)
    elif subject == "trust":
        c.path("M-134 -8 Q0 130 134 -8", "none", INK, 20)
        c.path("M-134 -8 Q0 130 134 -8", "none", RED, 9)
        hand(c,-118,-18,.58,26)
        hand(c,124,-18,.58,154,RED)
    elif subject == "framework":
        c.path("M-130 -140 V181 M131 -140 V181 M-149 -100 H152 M-149 119 H152", "none", INK, 12)
        c.path("M-130 -100 L131 119 M131 -100 L-130 119", "none", MUTED, 9)
        c.path("M-73 121 V-35 H75 V121", "none", RED, 20)
    elif subject == "undergraduate":
        book(c,-133,40,.96)
        c.path("M-129 -88 L7 -145 L146 -88 L7 -32 Z", RED, INK, 5)
        c.path("M-69 -56 V-7 Q5 32 83 -7 V-56", INK)
    elif subject == "chatbot":
        screen(c,-125,-86,1.05)
        c.path("M-74 -45 H55 V20 H4 L-18 42 V20 H-74 Z", RED, PAPER, 4)
    elif subject == "routes":
        c.path("M-16 187 V64 Q-16 -54 -133 -123 M24 187 V64 Q24 -54 141 -123", "none", INK, 12)
        c.path("M-34 132 H43 M-34 87 H43 M-40 36 L43 25 M-64 -13 L12 -43 M30 -10 L95 21", "none", RED, 10)
    elif subject == "aperture":
        c.circle(0,12,134,INK)
        c.circle(0,12,105,PAPER)
        for angle in (0,60,120,180,240,300):
            c.group(0,12,1,angle);c.path("M-27 -99 L64 -79 L23 -25 L-18 -31 Z",RED);c.end()
    elif subject == "market":
        c.path("M-154 -41 L-99 -130 H111 L160 -41 Z", INK)
        for xx in (-98,-27,44):
            c.path(f"M{xx} -123 H{xx+36} L{xx+51} -41 H{xx-15} Z",RED)
        c.rect(-126,-38,261,194,PAPER,stroke=INK,stroke_width=10)
        c.rect(-94,-5,193,119,MUTED)
    elif subject == "ballot":
        c.path("M-132 -38 L-48 -83 L137 -38 V164 H-132 Z", RED, INK, 8)
        c.path("M-82 -24 H84", "none", INK, 12)
        page(c,-49,-174,.57,-12)
    elif subject == "parenting":
        book(c,-151,-65,.95,-5)
        book(c,-34,86,.56,7)
    elif subject == "apps":
        phone(c,-74,-151,1.56)
        for xx,yy in ((-50,-103),(9,-103),(-50,-45),(9,-45)):
            c.rect(xx,yy,40,40,PAPER,stroke=INK,stroke_width=3)
            c.path(f"M{xx} {yy+8} H{xx+40} M{xx} {yy+22} H{xx+40}","none",RED,7)
    elif subject == "doctoral":
        book(c, -125, 25, 1.0)
        c.path("M-140 -95 L0 -155 L148 -95 L0 -40 Z", INK)
        c.path("M-76 -65 V-14 Q0 36 79 -14 V-65", RED, INK, 6)
        c.path("M121 -82 V29", "none", INK, 8)
    elif subject == "hci":
        screen(c, -125, -85, 1.05)
        c.path("M-12 -25 L-12 85 L14 64 L43 118 L68 105 L39 53 L78 53 Z", RED, PAPER, 5)
    elif subject in ("surveillance", "vision"):
        c.path("M-151 6 Q0 -144 151 6 Q0 154 -151 6 Z", PAPER, INK, 10)
        c.circle(0, 6, 61, RED)
        c.circle(0, 6, 27, INK)
        if subject == "surveillance":
            c.path("M-121 -77 L121 115", "none", INK, 22)
            c.path("M-121 -77 L121 115", "none", PAPER, 9)
    elif subject == "consent":
        page(c, -130, -116, 1.1)
        c.path("M44 -123 L69 -114 L31 44 L5 77 L-1 37 Z", RED, INK, 4)
        hand(c, 70, -91, .52, 96)
    elif subject == "network":
        c.path("M-151 -104 L0 -26 L154 -107 M0 -26 L-133 155 M0 -26 L153 141", "none", INK, 12)
        for xx, yy in ((-151,-104),(154,-107),(-133,155),(153,141)):
            c.rect(xx-22, yy-22, 44, 44, PAPER, stroke=INK, stroke_width=6)
        c.rect(-50,-72,100,130,RED,stroke=INK,stroke_width=6)
        c.path("M-13 -25 V36 H27 V-25", "none", PAPER, 8)
    elif subject == "science":
        c.path("M-57 -115 L19 -142 L72 -3 L0 22 Z", RED, INK, 6)
        c.path("M91 -49 Q164 83 45 117 H-110 M-81 115 V153 H120", "none", INK, 18)
        c.path("M-116 63 H40", "none", INK, 9)
    elif subject == "ownership":
        page(c, -56, -84, .92, 9)
        hand(c, -124, 87, .64, -22)
        hand(c, 145, -69, .64, 158, RED)
    elif subject == "time":
        c.path("M-94 -133 H103 M-94 161 H103", "none", INK, 17)
        c.path("M-76 -124 Q-76 -32 3 15 Q87 63 85 152 H-76 Q-76 58 3 15 Q85 -33 85 -124 Z", PAPER, INK, 8)
        c.path("M-55 132 Q-5 65 65 132 Z M-50 -92 H60 Q5 -20 -50 -92 Z", RED)
    elif subject == "physical":
        c.path("M-102 -68 H65 V-13 Q136 7 109 93 Q75 145 -3 109 L-102 29 Z", RED, INK, 8)
        c.circle(59, 54, 29, PAPER, stroke=INK, stroke_width=7)
        c.path("M-100 -63 Q-167 -167 -205 -80", "none", INK, 9)
    elif subject == "eap":
        book(c,-145,-10,1)
        c.path("M-40 -154 L8 -134 L-8 -46 L-63 47 L-78 -60 Z", RED, INK, 6)
        c.line(-44,-127,-61,19,INK,4)
    elif subject == "terminology":
        for xx, yy, angle in ((-142,-70,-18),(-48,-90,0),(53,-67,18)):
            page(c,xx,yy,.68,angle)
        c.path("M-112 -81 Q0 -171 112 -81", "none", RED, 13)
    elif subject == "preservice":
        book(c,-124,-13,.9)
        c.path("M-112 142 H139 M12 143 V207", "none", INK, 12)
        c.path("M-112 -85 L7 -132 L127 -85 L7 -39 Z", RED, INK, 5)
    elif subject == "children":
        c.rect(-83,-126,165,166,RED,stroke=INK,stroke_width=8,rx=12)
        c.path("M-104 52 H104 M-83 54 V175 M84 54 V175", "none", INK, 13)
        book(c,-103,-6,.74)
    elif subject == "workplace":
        screen(c,-109,-99,.88)
        c.path("M-155 72 H153 M-135 73 V192 M132 73 V192", "none", INK, 15)
    elif subject == "explanation":
        c.path("M-119 -37 L4 -108 L132 -35 V132 L5 199 L-119 126 Z", PAPER, INK, 8)
        c.path("M-119 -37 L5 37 L132 -35 M5 37 V199", "none", INK, 6)
        c.path("M-119 -37 L-168 -120 L-46 -185 L4 -108 Z", RED, INK, 6)
        c.circle(-25,-11,29,INK)
        c.circle(35,-42,29,RED)
    elif subject == "multimodal":
        page(c,-132,-126,1.18)
        c.rect(-81,-24,200,147,PAPER,stroke=INK,stroke_width=7)
        c.path("M-67 108 L-5 39 L38 81 L70 61 L105 108 Z", RED)
        c.circle(72,10,21,INK)
    elif subject == "comparison":
        c.rect(-148,-95,118,208,PAPER,stroke=INK,stroke_width=8)
        c.rect(36,-95,118,208,RED,stroke=INK,stroke_width=8)
        c.path("M-111 7 Q5 130 116 7", "none", INK, 18)
        c.path("M-111 7 Q5 130 116 7", "none", PAPER, 7)
    elif subject == "craft":
        c.path("M-122 -30 H126 V151 H-122 Z M-57 -31 V-77 H62 V-31", PAPER, INK, 9)
        c.path("M-108 13 H112 M-14 1 V26", "none", RED, 13)
        c.path("M79 -109 Q56 -150 85 -167 L91 -142 L112 -140 L119 -167 Q153 -132 119 -108 L83 -49 L62 -62 Z", INK)
    elif subject == "math":
        c.path("M-75 -87 L-121 147 M-75 -87 L48 112", "none", INK, 13)
        c.circle(-75, -87, 14, RED)
        c.path("M-116 109 Q-55 153 38 111", "none", RED, 6)
        c.path("M33 -61 H79 V-79 Q106 -105 115 -74 V-61 H157 V27 H33 Z", PAPER, INK, 5)
    elif subject == "writing":
        page(c, -85, -99, 1.08, -5)
        c.path("M90 -123 L116 -109 L-9 124 L-39 143 L-36 107 Z", RED, INK, 4)
    elif subject == "interview":
        c.circle(-96,-95,30,INK);c.circle(96,-95,30,RED)
        c.path("M-132 -49 Q-94 -74 -56 -49 L-43 57 H-135 Z",INK)
        c.path("M132 -49 Q94 -74 56 -49 L43 57 H135 Z",RED)
        c.path("M-112 54 V158 M111 54 V158", "none", INK, 17)
        book(c,-72,18,.51)
    elif subject == "language":
        c.path("M-134 -101 H57 V17 H-53 L-103 59 V17 H-134 Z", PAPER, INK, 6)
        c.path("M-36 53 H151 V167 H121 V201 L79 167 H-36 Z", RED, INK, 5)
    elif subject == "music":
        c.path("M-91 -112 V11 Q-91 67 -51 67 Q-11 67 -11 11 V-112 M-51 68 V174", "none", INK, 13)
        c.path("M40 70 V21 Q40 -35 103 -35 Q167 -35 167 21 V70", "none", INK, 15)
        c.rect(28, 58, 34, 59, RED, rx=12)
        c.rect(148, 58, 34, 59, RED, rx=12)
    elif subject == "code":
        screen(c, -125, -36, 1.1, -9)
    elif subject == "art":
        c.circle(18, 25, 99, PAPER, stroke=INK, stroke_width=10)
        c.path("M-44 -104 L-11 -107 L12 126 L-17 132 Z", INK)
        c.path("M-17 132 Q-48 193 16 207 Q43 167 12 126 Z", RED)
        c.path("M53 -43 L105 21 L43 76 L2 22 Z", RED)
    elif subject == "sleep":
        c.circle(0, 0, 111, INK)
        c.circle(45, -35, 93, PAPER)
        c.path("M-127 154 H151", "none", INK, 8)
    elif subject == "games":
        c.path("M-104 -27 Q-131 0 -132 88 Q-119 125 -81 85 L-42 58 H50 L90 92 Q130 125 145 89 Q143 -4 107 -26 Z", PAPER, INK, 8)
        c.path("M-71 -2 V49 M-97 22 H-45", "none", RED, 12)
        c.circle(78, 8, 10, INK)
        c.circle(105, 31, 10, INK)
    elif subject == "dashboard":
        c.rect(-119, -96, 253, 190, PAPER, stroke=INK, stroke_width=8)
        c.line(-98, -63, 112, -63, RED, 9)
        lens(c, 26, 40, .73, 13)
    elif subject in ("policy", "integrity"):
        page(c, -97, -88, 1.03, -5)
        if subject == "policy":
            c.circle(63, 48, 39, INK)
            c.circle(63, 48, 18, PAPER)
            c.path("M89 73 L143 130 L124 150 L107 132 L94 142 L78 126 L92 112 L67 87 Z", INK)
        else:
            c.circle(57, 73, 33, RED)
            c.path("M38 98 L31 170 L56 155 L76 174 L81 99 Z", RED, INK, 3)
    elif subject in ("teacher", "practice", "literacy"):
        book(c, -127, -68, .94, -3)
        if subject == "teacher":
            c.path("M-118 98 H149 M12 97 V193 M-54 193 H78", "none", INK, 12)
        elif subject == "literacy":
            lens(c, 105, 106, .42, 20)
        else:
            c.path("M135 -86 L153 -76 L54 136 L36 150 L37 126 Z", RED, INK, 3)
    elif subject == "medical":
        c.rect(-91, -93, 167, 224, PAPER, stroke=INK, stroke_width=7, rx=5)
        c.rect(-48, -113, 81, 37, INK, rx=8)
        c.path("M-30 -7 H22 M-4 -32 V20", "none", RED, 11)
        c.path("M117 51 V137 M91 137 H157 M97 137 V195 M149 137 V195", "none", INK, 9)
    elif subject == "aging":
        for x in (-112, 42):
            c.path(f"M{x} -53 H{x+89} V75 H{x} Z", PAPER, INK, 7)
            c.path(f"M{x-9} 79 H{x+99} M{x+6} 81 V168 M{x+80} 81 V168", "none", INK, 9)
    elif subject == "stress":
        plant(c, -60, 40, 1.25)
        screen(c, -133, 131, .64, -5, closed=True)
    elif subject == "agency":
        c.path("M-34 117 L64 -77", "none", INK, 16)
        c.circle(64, -77, 23, RED)
        c.path("M-92 141 L26 141 L57 167 H-122 Z", INK)
        hand(c, -65, -7, .8, -20, RED)
    elif subject in ("blocking", "filtering"):
        c.rect(-98, -119, 192, 283, PAPER, stroke=INK, stroke_width=7)
        if subject == "blocking":
            for yy in range(-99, 150, 50):
                c.rect(-88, yy, 172, 33, RED)
            c.path("M61 -43 V57 H127", "none", INK, 11)
        else:
            c.path("M-72 -89 L113 -133 V108 L-72 149 Z", RED, INK, 5)
            c.path("M-49 -50 L88 -85 M-49 8 L88 -27 M-49 67 L88 32", "none", PAPER, 9)
    elif subject == "pause":
        phone(c, -51, -104, 1.1, 14)
        c.path("M-104 141 Q12 219 133 141 L111 192 H-82 Z", INK)
    elif subject == "phone":
        phone(c, -25, -116, 1.15, 8)
        envelope(c, -141, 60, .76, -22)
        envelope(c, 67, 119, .65, 16)
    elif subject == "review":
        for x, h in ((-117, 179), (-61, 226), (-5, 199), (51, 238)):
            c.rect(x, 128-h, 44, h, PAPER, stroke=INK, stroke_width=5)
            c.rect(x+5, 100-h, 34, 14, RED)
        c.line(-142, 133, 124, 133, INK, 10)
    elif subject == "measurement":
        page(c, -104, -45, .87, -7)
        c.path("M35 -115 L-39 137 M35 -115 L126 121 M-19 61 Q54 94 108 55", "none", INK, 11)
        c.circle(35, -115, 14, RED)
    elif subject == "feedback":
        envelope(c, -114, 81, 1.45, -5)
        c.path("M-47 66 C-158 -57 -3 -166 87 -69 Q142 -9 81 42", "none", RED, 18)
        c.path("M102 11 L78 46 L63 9", "none", RED, 12)
    elif subject == "offload":
        page(c, -116, -56, .93, -9)
        page(c, -79, -76, .93, 9, RED)
        c.path("M39 -150 V-82 Q39 -42 74 -60", "none", INK, 10)
    elif subject == "metacognition":
        c.path("M-54 -101 Q-54 -143 11 -143 Q78 -143 78 -101 V77 H-54 Z", PAPER, INK, 9)
        c.path("M-26 -67 L51 -115 M-26 -26 L51 -74", "none", MUTED, 8)
        c.path("M-36 78 L-74 168 H102 L61 78", "none", INK, 10)
    elif subject == "effort":
        c.path("M-69 -35 V-79 Q-69 -126 13 -126 Q94 -126 94 -79 V-35", "none", INK, 13)
        for y, angle in ((-35, -6), (-11, 3), (12, -2)):
            page(c, -91, y, .89, angle)
        c.path("M-92 57 H56", "none", RED, 11)
    elif subject == "critical":
        page(c, -123, -102, 1.03, 8)
        lens(c, 39, 29, .79, -5)
    elif subject == "support":
        c.path("M-120 9 H142 V34 H-120 Z", RED, INK, 5)
        c.path("M-69 35 L-104 166 M-69 35 L-24 166 M87 35 L48 166 M87 35 L126 166", "none", INK, 11)
    elif subject == "inequality":
        c.path("M-101 -137 H100 V149 H-101 Z", "none", INK, 12)
        c.path("M-136 149 H-3 V191 H-136 Z M4 106 H133 V191 H4 Z", PAPER, INK, 6)
    else:
        page(c, -86, -83, 1.08, -4)
    c.end()


def render_svg(identity: str, inputs: dict, spec: dict, *, microvariation: bool = True) -> bytes:
    """Two source-specific subjects occupy the cover, rather than a stock scene.

    Identity, colors, tiny ornaments and title hashes do not alter geometry. The
    same concept produces the same image, so collision checks cannot be gamed by
    a filename or a negligible shift. microvariation is retained for compatibility.
    """
    c = Canvas()
    c.rect(0, 0, 1200, 760, PAPER)
    subjects = spec.get("visual_subjects", [])
    if len(subjects) < 2:
        raise ValueError("Contextual illustration needs two grounded subjects")
    contextual = render_contextual_scene(spec)
    if contextual:
        return contextual
    motif = spec["motif"]
    # Layout is a visible conceptual relationship, never a random arrangement.
    x1,y1,z1,x2,y2,z2 = 330,350,1.45,870,350,1.45
    if motif == "offloading":
        c.path("M579 133 H1079 V158 H579 Z M587 133 V629 H620 V157", INK)
        c.path("M609 132 L797 42 L1025 132", "none", INK, 10)
        c.line(856,159,856,217,INK,8)
        c.path("M856 217 V252 Q856 291 891 270", "none", RED, 14)
        c.path("M562 630 H669", "none", INK, 14)
        x1,y1,z1,x2,y2,z2=305,407,1.45,900,435,1.18
    elif motif == "reflection":
        # Do not put every reflection article inside the same giant mirror.
        # The actual context objects carry the silhouette; the returning paper
        # path conveys revisiting a task without depicting an empirical effect.
        c.path("M130 642 C254 689 424 689 547 609 Q615 562 693 602 L1085 674", "none", RED, 18)
        x1,y1,z1,x2,y2,z2=324,302,1.73,910,375,1.46
    elif motif == "verification":
        c.circle(351,330,242,PAPER,stroke=INK,stroke_width=24)
        c.path("M518 511 L660 674", "none", INK, 56)
        c.path("M518 511 L660 674", "none", RED, 27)
        x1,y1,z1,x2,y2,z2=346,301,1.15,914,360,1.38
    elif motif == "collaboration":
        c.path("M97 596 Q599 499 1104 596 V626 H97 Z", INK)
        hand(c,193,630,1.03,-14)
        hand(c,1008,630,1.03,194,RED)
        x1,y1,z1,x2,y2,z2=354,315,1.31,840,315,1.31
    elif motif in ("autonomy","governance"):
        c.path("M570 73 H637 V688 H570 Z", INK)
        c.path("M638 74 L735 131 V632 L638 688 Z", RED)
        c.circle(689,393,12,PAPER)
        x1,y1,z1,x2,y2,z2=295,332,1.4,953,340,1.13
    elif motif == "reconstruction":
        c.path("M84 600 H462 V626 H84 Z M741 600 H1111 V626 H741 Z", INK)
        c.path("M201 626 V720 M1017 626 V720", "none", INK, 22)
        c.path("M477 550 H727 V580 H477 Z", RED)
        hand(c,595,496,.9,90)
        x1,y1,z1,x2,y2,z2=295,322,1.3,927,319,1.3
    elif motif == "scaffolding":
        c.path("M94 113 H1109 M128 113 V686 M1076 113 V686 M99 679 H1100", "none", INK, 16)
        c.path("M128 113 L1076 679 M1076 113 L128 679", "none", MUTED, 10)
        c.path("M108 544 H1111", "none", RED, 17)
        x1,y1,z1,x2,y2,z2=338,320,1.28,874,320,1.28
    elif motif in ("interruptions","switching"):
        c.path("M104 649 Q569 652 622 352 Q646 111 1100 100", "none", INK, 23)
        c.path("M104 107 Q567 110 619 351 Q649 650 1100 649", "none", RED, 16)
        x1,y1,z1,x2,y2,z2=302,323,1.3,901,323,1.3
    elif motif == "language":
        c.path("M62 78 H525 V584 L400 686 V584 H62 Z", INK)
        c.path("M77 94 H509 V571 H77 Z", PAPER)
        c.path("M673 134 H1138 V640 H1064 V713 L969 640 H673 Z", RED)
        c.path("M690 151 H1120 V620 H690 Z", PAPER)
        x1,y1,z1,x2,y2,z2=296,304,1.12,903,363,1.12
    elif motif == "writing":
        c.path("M449 671 L733 111 L781 135 L499 694 L443 726 Z", RED, INK, 7)
        x1,y1,z1,x2,y2,z2=267,326,1.32,941,374,1.32
    elif motif == "creative":
        c.path("M45 52 H1150 V706 H45 Z", "none", INK, 14)
        c.path("M527 50 L664 50 L664 706 L527 706 Z", RED)
        c.path("M545 50 L730 50 L664 165 Z", PAPER, INK, 5)
        x1,y1,z1,x2,y2,z2=287,344,1.28,922,344,1.28
    elif motif == "memory":
        c.path("M50 85 H1150 V676 H50 Z", INK)
        c.path("M70 107 H566 V650 H70 Z M586 107 H1130 V650 H586 Z", PAPER)
        c.rect(477,128,68,20,RED)
        c.rect(1044,128,68,20,RED)
        x1,y1,z1,x2,y2,z2=313,349,1.3,868,349,1.3
    elif motif == "attention":
        c.path("M610 73 L85 676 H1139 Z", RED, fill_opacity="0.12")
        c.path("M494 77 Q606 5 718 77", "none", INK, 21)
        c.line(605,75,605,157,INK,12)
        x1,y1,z1,x2,y2,z2=346,405,1.32,866,405,1.32
    elif motif == "wellbeing":
        c.path("M69 651 Q582 713 1128 651", "none", INK, 15)
        plant(c,603,521,1.25)
        x1,y1,z1,x2,y2,z2=293,328,1.34,945,328,1.34
    elif motif == "music":
        c.path("M112 566 Q275 60 594 365 Q883 669 1101 169", "none", RED, 21)
        x1,y1,z1,x2,y2,z2=311,333,1.38,902,333,1.38
    elif motif == "inquiry":
        c.path("M69 659 H386 V619 H565 V661 H790 V606 H1121", "none", RED, 18)
        x1,y1,z1,x2,y2,z2=326,323,1.42,879,323,1.42
    else:
        c.path("M74 646 H531 V591 H718 V537 H1111", "none", RED, 21)
        x1,y1,z1,x2,y2,z2=326,318,1.4,887,318,1.4
    for subject,x,y,z in ((subjects[0],x1,y1,z1),(subjects[1],x2,y2,z2)):
        draw_subject(c,{**spec,"secondary_subject":subject},x=x,y=y,scale=z)
    body="".join(c.parts)
    result=('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 760" width="1200" height="760" role="img">'+body+'</svg>\n').encode()
    if len(result)>MAX_SVG_BYTES:
        raise ValueError("Editorial SVG exceeds its size budget")
    return result


def render_contextual_scene(spec: dict) -> bytes | None:
    """Task-specific compositions replace repeated family backdrops.

    Containers, controls and research instruments determine the actual scene.
    These are semantic drawing rules, never per-identity offsets or random noise.
    """
    subjects = spec["visual_subjects"]
    pair = set(subjects)
    c = Canvas(); c.rect(0,0,1200,760,PAPER)
    def object_at(name,x,y,z=1.4):
        draw_subject(c,{**spec,"secondary_subject":name},x=x,y=y,scale=z)
    def other(name):
        return next(s for s in subjects if s != name)
    if "apps" in pair and "blocking" in pair:
        object_at("apps",427,345,1.95)
        c.path("M606 91 H1062 V648 H606 Z",PAPER,INK,10)
        for y in (130,230,330,430,530): c.rect(627,y,415,64,RED)
        c.path("M1009 248 V443 H1119", "none", INK, 23)
    elif "apps" in pair and "filtering" in pair:
        object_at("apps",327,356,1.95)
        c.path("M560 167 L823 82 V621 L560 706 Z",MUTED,INK,8)
        c.path("M744 219 L1059 116 V638 L744 739 Z",RED,INK,8)
        for y in (283,394,505): c.path(f"M778 {y} L1028 {y-80}","none",PAPER,21)
    elif "apps" in pair and "pause" in pair:
        c.group(606,332,2.75,73);phone(c,-48,-82);c.end()
        c.path("M205 470 Q601 714 1008 470 L910 653 H310 Z",INK)
        c.rect(539,298,39,108,RED);c.rect(615,298,39,108,RED)
    elif "apps" in pair and "time" in pair:
        object_at("time",390,318,1.95);object_at("apps",925,433,1.08)
        c.path("M636 566 Q783 702 1051 639", "none",RED,19)
    elif "apps" in pair and "chatbot" in pair:
        object_at("apps",320,339,1.85)
        c.path("M627 126 H1093 V458 H938 L846 553 V458 H627 Z",RED,INK,10)
        c.path("M647 611 H1010", "none",INK,16)
        hand(c,829,584,1.25,-12)
    elif "measurement" in pair:
        context=other("measurement")
        if context=="phone":
            object_at("phone",377,312,2.05);object_at("measurement",930,424,1.35)
            c.path("M667 102 V649", "none",RED,17)
        elif context=="writing":
            object_at("writing",431,332,2.13);object_at("measurement",983,475,1.06)
            c.path("M89 652 H733", "none", RED, 22)
        else:
            object_at("measurement",464,306,2.05);object_at(context,976,486,1.08)
            c.path("M104 659 H771", "none", RED, 23)
            c.path("M756 114 H783 V657", "none",INK,11)
    elif "review" in pair:
        context=other("review")
        if context in ("hci","chatbot"):
            object_at(context,403,312,2.01);object_at("review",1014,467,1.02)
            if context=="hci":
                c.path("M109 603 H773 M446 603 V687", "none",INK,17)
            else:
                c.path("M102 77 H740 V545 H648 L552 636 V545 H102 Z", "none",RED,14)
        else:
            object_at("review",343,394,2.02);object_at(context,921,253,1.56)
            c.path("M690 587 H1123", "none",RED,20)
            page(c,787,586,.41,-9);page(c,953,592,.39,8)
    elif "dashboard" in pair:
        object_at("dashboard",462,332,2.19);object_at(other("dashboard"),1008,466,1.07)
        c.path("M91 595 H795 M447 595 V686", "none",INK,17)
    elif "explanation" in pair:
        object_at("explanation",409,328,2.04);object_at(other("explanation"),950,418,1.27)
        c.path("M749 115 Q871 61 1038 174", "none",RED,16)
    elif "framework" in pair:
        context=other("framework")
        if context=="metacognition":
            object_at("framework",604,386,1.78);object_at("metacognition",604,261,1.59)
        elif context=="critical":
            object_at("framework",375,349,1.76);object_at("critical",842,283,1.64)
            c.path("M96 695 H628", "none",RED,21)
        elif context=="feedback":
            object_at("feedback",318,311,1.93);object_at("framework",919,413,1.24)
            c.path("M598 586 Q733 687 1101 649", "none",RED,16)
        elif context=="stress":
            object_at("framework",403,377,1.47);object_at("stress",791,234,1.85)
        elif context=="language":
            object_at("framework",777,399,1.43);object_at("language",344,275,1.65)
        elif context=="eap":
            object_at("eap",401,301,2.02);object_at("framework",1009,478,1.02)
            c.path("M93 659 H743", "none",RED,20)
        else:
            object_at("framework",438,325,1.96);object_at(context,980,403,1.11)
            c.path("M95 688 H1121", "none", RED, 21)
    elif "policy" in pair and "integrity" in pair:
        object_at("integrity",390,311,2.04);object_at("policy",908,442,1.3)
        c.path("M706 90 V657", "none", RED, 20)
    elif "policy" in pair and "effort" in pair:
        object_at("effort",397,380,1.92);object_at("policy",932,275,1.38)
        c.path("M105 665 Q594 577 1104 665", "none", INK, 21)
    elif "medical" in pair and "phone" in pair:
        object_at("phone",366,321,1.96);object_at("medical",970,430,1.22)
        c.path("M692 127 V650", "none",RED,15,stroke_dasharray="31 35")
    elif "experiment" in pair:
        object_at("experiment",478,340,2.02);object_at(other("experiment"),1010,474,1.02)
        c.path("M84 664 H783", "none", RED, 20)
    elif "multimodal" in pair:
        object_at("multimodal",452,332,2.1);object_at(other("multimodal"),1009,434,1.16)
        c.path("M807 151 L1121 93 V648", "none", RED, 15)
    elif "teacher" in pair and "critical" in pair:
        object_at("teacher",337,343,1.99);object_at("critical",961,286,1.44)
        c.path("M628 612 H1114", "none",RED,20)
    elif "language" in pair and spec["motif"]=="language":
        object_at("language",350,326,1.8);object_at(other("language"),944,429,1.35)
        c.path("M668 93 Q554 219 703 346 Q839 478 704 668", "none",RED,15)
    elif "ecology" in pair:
        object_at("ecology",401,322,2.03);object_at(other("ecology"),968,425,1.18)
    elif "market" in pair:
        object_at("market",421,327,2.06);object_at(other("market"),1000,458,1.05)
    elif "children" in pair and "practice" in pair:
        object_at("children",359,325,1.93);object_at("practice",978,434,1.2)
        envelope(c,837,84,.93,14)
        c.path("M661 238 Q717 326 660 422", "none", RED, 18)
    else:
        return None
    result=('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 760" width="1200" height="760" role="img">'+"".join(c.parts)+'</svg>\n').encode()
    if len(result)>MAX_SVG_BYTES: raise ValueError("Editorial SVG exceeds its size budget")
    return result


def write_if_changed(path: Path, content: bytes) -> bool:
    if path.exists() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return True


def validate_raster(root: Path, src: str) -> tuple[str, int, int]:
    """Allow only explicitly owned local cover folders and real raster headers."""
    path = PurePosixPath(src)
    if (not re.fullmatch(r"assets/(?:editorial-covers|article-art)/[a-z0-9-]+\.(?:webp|png|jpg)", src)
            or any(p in ("", ".", "..") for p in src.split("/")) or path.is_absolute()):
        raise ValueError("Override src must be a safe local raster path under assets/editorial-covers/ or assets/article-art/")
    target = (root / src).resolve()
    if not target.is_relative_to(root / "assets") or not target.is_file():
        raise ValueError("Override image must exist inside the local assets directory")
    data = target.read_bytes()
    if len(data) > MAX_OVERRIDE_BYTES:
        raise ValueError("Override image exceeds 2 MB")
    width = height = 0
    if path.suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR" and len(data) >= 33:
        width, height = struct.unpack(">II", data[16:24])
    elif path.suffix == ".webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        if int.from_bytes(data[4:8], "little") + 8 != len(data):
            raise ValueError("Override WebP is incomplete")
        if data[12:16] == b"VP8X":
            width, height = (1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little"))
        elif data[12:16] == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width, height = struct.unpack("<HH", data[26:30])
            width, height = width & 16383, height & 16383
        elif data[12:16] == b"VP8L" and data[20] == 47:
            bits = int.from_bytes(data[21:25], "little")
            width, height = 1 + (bits & 16383), 1 + ((bits >> 14) & 16383)
    elif path.suffix in (".jpg", ".jpeg") and data.startswith(b"\xff\xd8\xff"):
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 255:
                break
            marker = data[pos + 1]
            length = int.from_bytes(data[pos + 2:pos + 4], "big")
            if marker in (192, 193, 194) and length >= 7 and pos + 9 <= len(data):
                height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
                break
            if length < 2:
                break
            pos += 2 + length
    if not width or not height or width > 10000 or height > 10000:
        raise ValueError("Override image has an invalid or unsupported raster header")
    return hashlib.sha256(data).hexdigest(), width, height


def load_overrides(root: Path, manifest: Path | None = None) -> dict:
    """Validate every override before use. A mistake cannot publish a broken image."""
    root = Path(root).resolve()
    manifest = manifest or root / "data/article-art-overrides.json"
    if not manifest.exists():
        return {}
    payload = json.loads(manifest.read_text())
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("overrides"), dict):
        raise ValueError("Article art overrides require version 1 and an overrides object")
    result = {}
    seen_assets = set()
    for identity, value in payload["overrides"].items():
        if not isinstance(identity, str) or not identity.startswith(("doi:", "url:", "title:")):
            raise ValueError("Override keys must be canonical doi:, url:, or title: identities")
        if identity.startswith("doi:") and canonical_identity({"doi": identity}) != identity:
            raise ValueError("Override DOI keys must be canonical lower-case identities")
        if identity.startswith("url:") and canonical_identity({"url": identity[4:]}) != identity:
            raise ValueError("Override URL keys must be canonical identities without tracking or fragments")
        if not isinstance(value, dict):
            raise ValueError("Each article art override must be an object")
        for key in ("src", "alt", "concept", "provenance"):
            if not isinstance(value.get(key), str) or not value[key].strip():
                raise ValueError("Article art overrides require explicit src, alt, concept, and provenance")
        src = value["src"]
        seen_assets.add(src)
        asset_hash, width, height = validate_raster(root, src)
        for key, actual in (("width", width), ("height", height)):
            if key in value and (type(value[key]) is not int or value[key] != actual):
                raise ValueError("Override dimensions must match the actual image")
        resolved = {**value, "asset_fingerprint": asset_hash, "width": width, "height": height}
        if "thumbnail_src" in value:
            if not isinstance(value["thumbnail_src"], str):
                raise ValueError("Override thumbnail_src must be a local raster path")
            thash, twidth, theight = validate_raster(root, value["thumbnail_src"])
            if twidth > width or theight > height or abs(twidth / theight - width / height) > .02:
                raise ValueError("Override thumbnail must be no larger than its cover and preserve its aspect ratio")
            resolved.update(thumbnail_fingerprint=thash, thumbnail_width=twidth, thumbnail_height=theight)
        result[identity] = resolved
    return result


def create_art(record: dict, root: Path = ROOT, overrides: dict | None = None, *, write_asset: bool = True) -> dict:
    """Build one candidate. Collection-wide acceptance belongs to attach_art."""
    identity, inputs = canonical_identity(record), public_inputs(record)
    spec = choose_concept(inputs)
    fingerprint = hashlib.sha256(json.dumps({"identity": identity, "inputs": inputs,
        "renderer_version": RENDERER_VERSION}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    metadata = {"kind": "editorial_illustration", "status": "ready", "renderer_version": RENDERER_VERSION,
                "input_fingerprint": fingerprint, **spec,
                "provenance": "Original procedurally composed editorial SVG; not a source figure or empirical diagram."}
    if identity in (overrides or {}):
        override = overrides[identity]
        return {**metadata, **{k: override[k] for k in ("src", "alt", "concept", "provenance", "asset_fingerprint", "width", "height", "thumbnail_src", "thumbnail_fingerprint", "thumbnail_width", "thumbnail_height") if k in override},
                "renderer_version": "editorial-override-1", "semantic_basis": "editor_selected",
                "motif": "editor_selected", "format": Path(override["src"]).suffix.lstrip("."),
                "review_reasons": [], "visual_subjects": [],
                "semantic_signature": "editor_selected|" + normalized(override["concept"]).casefold(),
                "source_grounding": [{"field": "editorial_override.concept", "subject": "editor_selected",
                                      "phrases": [override["concept"]]}],
                "uniqueness": "editor_declared_concept_and_raster_bytes"}
    if spec.get("review_reasons"):
        return {**metadata, "status": "needs_review"}
    content = render_svg(identity, inputs, spec)
    metadata["composition_fingerprint"] = hashlib.sha256(render_svg(identity, inputs, spec, microvariation=False)).hexdigest()
    # Ordering or a different frame must not make the same dominant noun pair
    # look like a new contextual illustration. Compare actual foreground glyphs
    # too: separate subject labels may intentionally share the same drawing.
    metadata["foreground_signature"] = "|".join(sorted(spec["visual_subjects"]))
    foreground_hashes = []
    for subject in spec["visual_subjects"]:
        canvas = Canvas()
        draw_subject(canvas, {**spec, "secondary_subject": subject}, x=0, y=0, scale=1)
        foreground_hashes.append(hashlib.sha256("".join(canvas.parts).encode()).hexdigest())
    metadata["foreground_geometry_fingerprint"] = hashlib.sha256("|".join(sorted(foreground_hashes)).encode()).hexdigest()
    # The closed SVG grammar also permits a deliberately coarse visual screen.
    # This is not browser rasterization or proof of perceptual uniqueness.
    from art_similarity import RASTERIZER_VERSION, WIDTH, HEIGHT, rasterize, encode_signature
    try:
        pixels = rasterize(content)
    except ValueError as exc:
        return {**metadata, "status": "needs_review", "review_reasons": ["visual_similarity_unavailable"],
                "visual_similarity_detail": str(exc)}
    metadata.update(coarse_raster_version=RASTERIZER_VERSION, coarse_raster_size=[WIDTH, HEIGHT],
                    coarse_raster_signature=encode_signature(pixels),
                    coarse_raster_fingerprint=hashlib.sha256(pixels).hexdigest())
    asset_hash = hashlib.sha256(content).hexdigest()
    name = hashlib.sha256(identity.encode()).hexdigest()[:20] + "-" + asset_hash[:24] + ".svg"
    src = GENERATED_DIR + "/" + name
    target = (Path(root) / src).resolve()
    if not target.is_relative_to(Path(root).resolve() / "assets"):
        raise ValueError("Generated asset directory must remain inside local assets")
    if write_asset:
        write_if_changed(target, content)
    return {**metadata, "src": src, "asset_fingerprint": asset_hash, "format": "svg", "width": 1200, "height": 760}


def attach_art(records: list[dict], root: Path = ROOT, manifest: Path | None = None) -> list[dict]:
    """Decorate ONLY records that the caller has already admitted for publication.

    This is deliberately downstream from build_public's gates. It never promotes
    a record, changes reading depth, replaces visual evidence, or touches provenance.
    """
    overrides = load_overrides(Path(root), manifest)
    from art_similarity import compare, decode_signature, is_near_twin
    candidates = []
    for record in records:
        candidate = create_art(record, root, overrides, write_asset=False)
        prior = record.get("editorial_art") or {}
        # Retain an already accepted allocation only when it still describes
        # this exact candidate. Old v1 decorative differences grant no priority.
        retained = (prior.get("status") == "ready" and prior.get("src") == candidate.get("src")
                    and prior.get("input_fingerprint") == candidate.get("input_fingerprint")
                    and prior.get("asset_fingerprint") == candidate.get("asset_fingerprint")
                    and prior.get("renderer_version") == candidate.get("renderer_version"))
        candidates.append((not retained, canonical_identity(record), candidate, record))
    owners = {key: {} for key in ("semantic_signature", "foreground_signature", "foreground_geometry_fingerprint", "composition_fingerprint", "bytes")}
    reasons = {"semantic_signature": "duplicate_semantic_concept", "foreground_signature": "duplicate_foreground_subjects",
               "foreground_geometry_fingerprint": "duplicate_foreground_geometry",
               "composition_fingerprint": "duplicate_composition"}
    accepted_rasters = []
    for _, identity, candidate, record in sorted(candidates, key=lambda item: (item[0], item[1], item[2]["input_fingerprint"])):
        if candidate["status"] == "needs_review":
            record["editorial_art"] = candidate
            continue
        checks = [(key, candidate[key], reasons[key]) for key in reasons if candidate.get(key)]
        # These fingerprints come from validated file bytes, not names or an
        # editor-supplied checksum. Check thumbnails as well as full-size covers.
        checks += [("bytes", candidate[key], reason) for key, reason in
                   (("asset_fingerprint", "duplicate_asset_bytes"), ("thumbnail_fingerprint", "duplicate_thumbnail_bytes"))
                   if candidate.get(key)]
        collisions = [{"reason": reason, "identity": owners[key][signature]}
                      for key, signature, reason in checks
                      if signature in owners[key] and owners[key][signature] != identity]
        pixels = decode_signature(candidate["coarse_raster_signature"]) if candidate.get("coarse_raster_signature") else None
        if pixels is not None:
            for accepted_identity, accepted_pixels in accepted_rasters:
                if accepted_identity == identity:
                    continue
                metrics = compare(pixels, accepted_pixels)
                if is_near_twin(metrics):
                    collisions.append({"reason": "near_visual_twin", "identity": accepted_identity,
                                       "metrics": {key: round(value, 6) if isinstance(value, float) else value for key, value in metrics.items()}})
        if collisions:
            candidate["status"] = "needs_review"
            candidate["review_reasons"] = sorted({c["reason"] for c in collisions})
            candidate["review_collisions"] = collisions
            # A review state never contains a usable image URL, including a
            # thumbnail; consumers can show the article without fallback art.
            candidate.pop("src", None)
            candidate.pop("thumbnail_src", None)
        else:
            for key, signature, _ in checks:
                owners[key][signature] = identity
            if candidate["semantic_basis"] != "editor_selected":
                accepted_rasters.append((identity, pixels))
                # The candidate's path was already validated; redraw its exact
                # accepted scene without repeating the coarse raster analysis.
                write_if_changed(Path(root) / candidate["src"], render_svg(identity, public_inputs(record), candidate))
        record["editorial_art"] = candidate
    return records


def report(records: list[dict], root: Path) -> dict:
    from art_similarity import RASTERIZER_VERSION, WIDTH, HEIGHT, NEAR_TWIN_LIMITS
    items = [{"identity": canonical_identity(r), "title": r.get("title", ""), **r["editorial_art"]} for r in records]
    ready = [item for item in items if item.get("status") == "ready" and item.get("src")]
    pending = [item for item in items if item.get("status") == "needs_review"]
    def collisions(key):
        groups = {}
        for item in items:
            if item.get(key):
                groups.setdefault(item[key], set()).add(item["identity"])
        return {k: sorted(v) for k, v in sorted(groups.items()) if len(v) > 1}
    paths = {item["src"] for item in ready}
    return {"renderer_version": RENDERER_VERSION, "article_count": len(items),
            "ready_count": len(ready), "needs_review_count": len(pending),
            "review_reasons": dict(sorted(Counter(reason for item in pending for reason in item.get("review_reasons", [])).items())),
            "distinct_generated_compositions": len({item["composition_fingerprint"] for item in ready if item.get("composition_fingerprint")}),
            "composition_audit": "Dominant source-grounded noun pairs, semantic signatures, exact SVG geometry, and validated raster bytes; not a perceptual pixel-uniqueness guarantee",
            "coarse_visual_screen": {"version": RASTERIZER_VERSION, "size": [WIDTH, HEIGHT], "limits": NEAR_TWIN_LIMITS,
                                     "generated_candidate_count": sum(bool(item.get("coarse_raster_signature")) for item in items),
                                     "raster_overrides_screened": False,
                                     "scope": "Approximate generated SVG scene and foreground comparison; not browser pixels"},
            "near_visual_twin_candidates": [{"identity": item["identity"], "matches": [collision for collision in item.get("review_collisions", [])
                                             if collision["reason"] == "near_visual_twin"]}
                                            for item in pending if "near_visual_twin" in item.get("review_reasons", [])],
            "semantic_collision_groups": collisions("semantic_signature"),
            "foreground_collision_groups": collisions("foreground_signature"),
            "foreground_geometry_collision_groups": collisions("foreground_geometry_fingerprint"),
            "composition_collision_groups": collisions("composition_fingerprint"),
            "asset_collision_groups": collisions("asset_fingerprint"),
            "thumbnail_collision_groups": collisions("thumbnail_fingerprint"),
            "unique_asset_count": len(paths),
            "asset_bytes": sum((Path(root) / src).stat().st_size for src in paths),
            "motifs": dict(sorted(Counter(r["motif"] for r in items).items())),
            "semantic_bases": dict(sorted(Counter(r["semantic_basis"] for r in items).items())), "items": items}


def contact_sheet(records: list[dict], root: Path, target: Path):
    import os
    tiles = []
    for r in records:
        art = r["editorial_art"]
        if art.get("status") == "ready" and art.get("src"):
            src = os.path.relpath(root / art["src"], target.parent)
            visual = '<img loading="lazy" src="' + html.escape(src, quote=True) + '" alt="' + html.escape(art["alt"], quote=True) + '">'
        else:
            visual = '<p class="review">Artwork needs review: ' + html.escape(", ".join(art.get("review_reasons", []))) + '</p>'
        tiles.append('<figure>' + visual + '<figcaption><b>' + html.escape(r.get("title", "")) +
                     '</b><small>' + html.escape(art["motif"] + " · " + art["semantic_basis"]) + '</small></figcaption></figure>')
    content = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Editorial art contact sheet</title>'
               '<style>body{background:#eee9df;color:#171714;font:14px system-ui;margin:30px}'
               'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}'
               'figure{margin:0;background:#fff}img{display:block;width:100%}figcaption{padding:14px}'
               '.review{padding:24px;color:#655e52}small{display:block;color:#655e52;margin-top:8px}</style><h1>Editorial illustrations</h1>'
               '<p>Original source-theme metaphors, not source figures or study results.</p><main>' +
               ''.join(tiles) + '</main></html>\n')
    write_if_changed(target, content.encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--public-library", type=Path, help="Already-gated public projection; default data/public-library.json")
    parser.add_argument("--report", type=Path, help="Write a deterministic asset/concept manifest")
    parser.add_argument("--contact-sheet", type=Path, help="Write a local HTML review sheet")
    args = parser.parse_args()
    path = args.public_library or args.root / "data/public-library.json"
    if path.name != "public-library.json":
        parser.error("Use the already-gated public-library.json projection, not an acquisition index")
    records = json.loads(path.read_text())
    # Reuse the same gates without running acquisition, modifying source notes, or
    # inventing a separate eligibility policy for illustration generation.
    from build_public import readable
    from source_quality import screen
    from news_quality import substantive_article
    from original_readings import eligible
    records = [r for r in records if readable(r) and (screen(r)["decision"] == "include" if r.get("kind") == "scholarly"
               else eligible(r.get("original_reading"), r) or substantive_article(r))]
    attach_art(records, args.root)
    summary = report(records, args.root)
    if args.report:
        write_if_changed(args.report, (json.dumps(summary, indent=2, ensure_ascii=False) + "\n").encode())
    if args.contact_sheet:
        contact_sheet(records, args.root, args.contact_sheet)
    print(json.dumps({k: v for k, v in summary.items() if k != "items"}, sort_keys=True))


if __name__ == "__main__":
    main()

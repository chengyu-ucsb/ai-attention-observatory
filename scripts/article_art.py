"""Original, deterministic editorial illustrations for already-public readings.

Run ``python scripts/build_public.py`` for the full publication-gated loop, or
``python scripts/article_art.py --report /tmp/art.json --contact-sheet /tmp/art.html``
to regenerate the existing public projection and inspect its covers. No network,
API key, image service, source figures, timestamps, or third-party code is used.

The renderer chooses a concrete metaphor from public titles/digests, then composes
objects and relationships. A stable hash changes only small layout details; it
never chooses the subject or invents research findings. These are illustrations,
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
RENDERER_VERSION = "editorial-svg-1"
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
    "collaboration": (("collaborat", "co-intelligence", "co-creat", "shared control", "peer-likeness", "ai peer", "co-regulation"),
        "two different hands bringing interlocking pieces together above an open book", "negotiating a shared task between human and machine participants"),
    "interruptions": (("distract", "interrupt", "notification", "disruption", "smartphone", "multitask"),
        "a reading lamp and open book surrounded by incoming envelopes and a phone", "attention meeting competing digital invitations"),
    "switching": (("task switching", "switch readiness", "switching between", "switching in"),
        "a railway switch dividing into two tracks that end at different workbooks", "moving attention between competing tasks"),
    "autonomy": (("autonom", "agency", "agential", "intention", "blocking", "focus mode", "focus filter", "pause apps", "user-controlled"),
        "a hand adjusting a shutter between a phone and a quiet open book", "choosing what reaches one's attention"),
    "governance": (("governance", "consent", "consenting", "democracy", "surveillance", "policy", "integrity", "rules"),
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
    "art": (("art education", "creative agency", "innovation"), "a brush opening a paper aperture", "studio"),
    "sleep": (("insomnia", "sleep", "rest"), "a crescent moon behind a shuttered window", "night_window"),
    "games": (("game-based", "game based", "gaming"), "a controller and a loose puzzle piece", "digital_window"),
    "dashboard": (("dashboard", "explainable", "explainability"), "a viewing window and an adjustable lens", "digital_window"),
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
    "interview": (("accounts", "qualitative", "perspectives", "grounded theory", "interview"), "two facing speech cutouts above a notebook", "folded_paper"),
    "feedback": (("feedback", "prompting", "prompt strategy", "chat", "help-seeking"), "a paper loop returning to an open envelope", "folded_paper"),
    "offload": (("offload", "outsourc", "delegat", "substitution", "deskilling"), "a bundle of pages held by a small hook", "workbench"),
    "metacognition": (("metacognit", "self-regulat", "reflect", "monitoring"), "a pocket mirror beside an open page", "quiet_room"),
    "effort": (("cognitive load", "mental effort", "overload", "cognitive effort"), "a handle carrying a bundle of paper", "workbench"),
    "literacy": (("literacy", "familiarity", "knowledge", "understanding"), "an open field guide with a magnifying tab", "library"),
    "critical": (("critical thinking", "judgment", "judgement", "uncertain", "trust"), "a magnifier crossing an unmarked manuscript", "workbench"),
    "support": (("scaffold", "support", "capability", "engagement"), "a small trestle holding an unfinished plank", "workbench"),
    "inequality": (("unequal", "inequal", "equitable", "access"), "a doorway with two different-height steps", "threshold"),
    "practice": (("learning", "student", "education", "practice"), "an unfinished exercise book and a pencil", "classroom"),
}

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
    return [p for p in phrases if re.search(r"(?<!\w)" + re.escape(p), text)]


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
    if relation == "open" and any(word in text for word in ("between", "contrast", "disconnect", "or ", "different")):
        relation = "comparison"
    arrangement = {"shared": "shared_table", "question": "inspection", "protected": "threshold",
                   "rebuild": "separated_support", "comparison": "facing_panels", "open": "side_by_side"}[relation]
    title_label = f'For “{title}”, ' if title else "For this reading, "
    concept = title_label + objects + " evokes " + meaning + "."
    if basis == "topic_fallback":
        concept = "Topic-based illustration: " + title_label + objects + "; " + meaning + "."
    concept += " Paired with " + subject_object + ", the scene connects that metaphor to the article's " + subject.replace("_", " ") + " theme."
    signature = "|".join((family, subject, context, relation, setting))
    return {"motif": family, "semantic_basis": basis, "context": context, "relation": relation,
            "secondary_subject": subject, "secondary_basis": subject_basis, "secondary_cues": subject_cues,
            "setting": setting, "arrangement": arrangement, "semantic_signature": signature,
            "uniqueness": "source_theme_composition",
            "matched_cues": sorted(set(title_hits + digest_hits)), "concept": concept,
            "alt": "Editorial illustration of " + objects + ", paired with " + subject_object + ". Not a depiction of study results."}


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


def draw_subject(c: Canvas, spec: dict):
    subject = spec["secondary_subject"]
    # Each subject is a different large object assembly. Its relationship to the
    # main metaphor is a two-subject editorial composition, not an effect diagram.
    y = {"inspection": 300, "shared_table": 427, "threshold": 370,
         "separated_support": 281, "facing_panels": 377, "side_by_side": 354}[spec["arrangement"]]
    c.group(966, y, .77)
    if subject == "craft":
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
    elif subject in ("language", "interview"):
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
    seed = hashlib.sha256((identity + json.dumps(inputs, sort_keys=True, ensure_ascii=False)).encode()).digest()
    if not microvariation:
        seed = bytes(32)
    # Microvariation affects the cut-paper arrangement, never semantic selection.
    shift = (int.from_bytes(seed[:2], "big") / 65535 * 28 - 14)
    lean = (seed[2] / 255 * 5 - 2.5)
    c = Canvas()
    c.rect(0, 0, 1200, 760, PAPER)
    draw_setting(c, spec)
    # A second source subject changes both the silhouette and the spatial relation.
    # Nothing in this placement derives from the identity hash.
    layout = spec["arrangement"]
    transforms = {"side_by_side": (0, 74, .78), "inspection": (-22, 107, .81),
                  "shared_table": (8, 126, .78), "threshold": (-23, 100, .78),
                  "separated_support": (-10, 95, .8), "facing_panels": (-12, 107, .77)}
    tx, ty, zoom = transforms[layout]
    c.group(round(tx + shift / 3, 3), ty, zoom, round(lean / 2, 3))
    motif, context, relation = spec["motif"], spec["context"], spec["relation"]
    if motif == "offloading":
        book(c, 130, 447, 1.22, -4)
        screen(c, 785, 403, 1.25, 3)
        c.rect(541, 173, 29, 393)
        c.path("M433 567 H668 L633 594 H467 Z", INK)
        c.path("M427 181 H902 V207 H427 Z", INK)
        c.path("M554 200 L696 108 L844 181 M554 181 L696 108 L696 181", "none", INK, 8)
        c.line(759, 208, 759, 327, INK, 5)
        c.path("M759 326 V349 Q759 375 781 362", "none", INK, 7)
        page(c, 645, 318, .72, -12)
        page(c, 672, 310, .72, 7, RED)
        if relation == "question":
            lens(c, 340, 393, .43, -30)
        elif relation == "shared":
            hand(c, 888, 578, .65, 180, RED)
    elif motif == "reconstruction":
        c.path("M104 499 H446 V529 H104 Z M754 499 H1084 V529 H754 Z", INK)
        c.path("M152 526 V649 H205 V526 M1006 526 V649 H1059 V526", INK)
        c.path("M289 503 Q590 716 937 503", "none", INK, 11)
        c.path("M468 455 H722 V480 H468 Z", RED)
        hand(c, 593, 357, .94, 92)
        screen(c, 190, 380, .8, -7, closed=True)
        book(c, 794, 377, .71, 3)
        c.path("M497 504 L485 592 M692 502 L712 594", "none", RED, 6, stroke_dasharray="12 14")
    elif motif == "verification":
        page(c, 175, 315, 1.25, -13)
        page(c, 764, 227, 1.05, 12)
        page(c, 795, 462, .75, -9)
        c.path("M345 460 C480 459 478 303 728 314 M445 433 Q586 537 754 529", "none", INK, 9)
        lens(c, 584, 361, 1.3, -13)
        if context == "classroom":
            book(c, 298, 579, .62, 1)
        else:
            hand(c, 829, 588, .65, 185)
    elif motif == "reflection":
        c.path("M705 206 Q705 151 787 151 Q874 151 874 206 V509 H705 Z", INK)
        c.path("M724 217 Q724 176 787 176 Q854 176 854 217 V489 H724 Z", PAPER)
        c.path("M750 230 L823 195 M750 264 L839 217", "none", MUTED, 7)
        c.path("M728 510 L700 583 H890 L855 510", "none", INK, 9)
        book(c, 206, 443, 1.38, -7)
        page(c, 524, 281, .77, 21, RED)
        c.path("M410 283 C269 153 172 276 248 384", "none", INK, 8)
        c.path("M220 370 L251 391 L255 353", "none", INK, 8)
        if relation == "shared":
            c.circle(787, 351, 36, RED)
        else:
            c.path("M756 413 Q780 369 826 413 L826 445 H756 Z", RED)
    elif motif == "collaboration":
        book(c, 404, 480, 1.35, -3)
        hand(c, 313, 303, 1.12, -17)
        hand(c, 894, 330, 1.12, 164, RED)
        c.path("M462 259 H528 Q508 214 545 214 Q579 214 563 259 H614 V312 Q658 297 658 332 Q658 368 614 352 V404 H563 Q579 447 545 447 Q508 447 528 404 H462 Z", PAPER, INK, 6)
        c.path("M621 259 H759 V404 H621 V355 Q666 370 666 332 Q666 294 621 309 Z", RED, INK, 6)
        if context == "classroom":
            c.path("M286 492 L337 424 L350 436 L300 505 Z", INK)
    elif motif == "interruptions":
        book(c, 282, 479, 1.25, -4)
        c.path("M219 532 V361 L350 235", "none", INK, 13)
        c.path("M177 538 H272 L287 557 H162 Z", INK)
        c.path("M303 227 L351 180 L421 257 L351 302 Z", RED, INK, 5)
        c.path("M355 299 L406 467 L604 479 L418 260 Z", RED, fill_opacity="0.1")
        for i in range(3 + (context == "mobile")):
            envelope(c, 660 + i * 88, 190 + (i % 2) * 108, .77, -16 + i * 13)
        phone(c, 855, 411, 1.08, 13)
        c.path("M765 388 Q731 418 743 451 M790 397 Q770 418 778 437", "none", INK, 4)
    elif motif == "switching":
        c.path("M499 690 V518 Q502 395 302 309 M554 690 V520 Q554 419 331 271", "none", INK, 12)
        c.path("M514 526 Q692 439 871 296 M547 570 Q764 472 914 331", "none", INK, 12)
        for y in (583, 619, 655):
            c.line(480, y, 571, y, RED, 11)
        c.path("M552 502 L664 373", "none", RED, 15)
        c.circle(663, 372, 20, RED)
        book(c, 139, 216, .85, -10)
        screen(c, 818, 205, .86, 8)
    elif motif == "autonomy":
        phone(c, 151, 300, 1.6, -11)
        c.rect(489, 193, 191, 355, INK)
        c.rect(509, 214, 151, 311, PAPER)
        slats = 4 if relation == "protected" else 3
        for i in range(slats):
            c.path(f"M510 {224 + i * 78} L658 {245 + i * 78} V{276 + i * 78} L510 {255 + i * 78} Z", RED)
        hand(c, 443, 549, .84, -92)
        book(c, 752, 425, .99, 8)
        c.path("M309 361 Q390 346 458 375 M327 408 Q396 396 457 416", "none", INK, 4)
    elif motif == "governance":
        c.rect(674, 196, 28, 391)
        c.rect(991, 196, 28, 391)
        c.path("M706 218 L904 275 V551 L706 579 Z", PAPER, INK, 9)
        c.path("M745 269 V525 M790 283 V513 M835 294 V501", "none", RED, 8)
        c.circle(875, 408, 10, INK)
        c.circle(426, 315, 64, INK)
        c.circle(426, 315, 34, PAPER)
        c.path("M447 355 L552 460 L530 482 L510 462 L495 477 L477 459 L491 444 L421 375 Z", INK)
        hand(c, 321, 484, 1, -38, RED)
        page(c, 885, 496, .58, 17)
    elif motif == "language":
        c.path("M154 227 H481 V412 H297 L216 477 V412 H154 Z", PAPER, INK, 8)
        c.path("M707 266 H1032 V451 H972 V507 L893 451 H707 Z", INK)
        c.path("M361 345 L504 293 L690 378 L807 341 V427 L690 464 L504 379 L361 431 Z", RED, INK, 4)
        c.path("M504 293 V379 M690 378 V464", "none", PAPER, 4)
        book(c, 460, 523, .84, -2)
    elif motif == "writing":
        screen(c, 175, 266, 1.05, -8)
        c.path("M382 387 Q506 320 612 392 L708 502 Q551 449 442 538 Z", PAPER, INK, 5)
        book(c, 708, 470, 1, 7)
        c.group(668, 191, 1, 29)
        c.path("M0 0 H35 V268 L17 320 L0 268 Z", RED, INK, 5)
        c.path("M0 268 H35 L17 320 Z", PAPER, INK, 5)
        c.path("M17 320 L11 300 H24 Z", INK)
        c.end()
        if relation == "question":
            lens(c, 848, 347, .43, 19)
    elif motif == "creative":
        c.path("M370 215 H797 V560 H370 Z", INK)
        c.path("M393 238 H773 V536 H393 Z", PAPER)
        c.path("M474 421 Q485 276 581 316 Q659 252 688 391 Q633 491 474 421 Z", RED)
        c.path("M770 238 L905 167 V460 L770 536 Z", PAPER, INK, 6)
        c.path("M228 260 L258 255 L305 493 L278 497 Z", INK)
        c.path("M278 497 Q258 556 313 574 Q335 534 305 493 Z", RED)
        c.circle(879, 549, 27, "none", stroke=INK, stroke_width=9)
        c.circle(934, 561, 27, "none", stroke=INK, stroke_width=9)
        c.path("M893 529 L957 389 M921 538 L858 409", "none", INK, 10)
    elif motif == "music":
        c.path("M317 399 V312 Q317 167 491 167 Q660 167 660 312 V399", "none", INK, 32)
        c.rect(284, 325, 70, 141, RED, rx=28, stroke=INK, stroke_width=5)
        c.rect(624, 325, 70, 141, RED, rx=28, stroke=INK, stroke_width=5)
        c.path("M840 244 V367 Q840 413 877 413 Q914 413 914 367 V244 M877 415 V566", "none", INK, 13)
        book(c, 394, 482, 1.1, -7)
        c.path("M787 281 Q758 314 787 346 M968 281 Q997 314 968 346", "none", INK, 4)
    elif motif == "wellbeing":
        c.path("M337 298 Q337 269 369 269 H496 Q527 269 527 300 V454 H337 Z", INK)
        c.path("M314 450 H551 V480 H314 Z M342 480 L320 608 M523 480 L547 608", "none", INK, 14)
        c.path("M359 293 H503 V429 H359 Z", RED)
        plant(c, 771, 468, 1.33)
        phone(c, 610, 514, .8, 68)
        c.path("M167 571 Q205 532 269 572", "none", INK, 4)
        if context == "classroom":
            book(c, 148, 505, .49, -9)
    elif motif == "memory":
        c.path("M622 204 H929 V504 H622 Z", INK)
        c.path("M641 223 H909 V314 H641 Z M641 333 H909 V425 H641 Z", PAPER)
        c.rect(744, 258, 60, 15, RED)
        c.rect(744, 368, 60, 15, RED)
        c.path("M621 438 L540 564 H846 L929 438 Z", RED, INK, 6)
        c.path("M540 564 V608 H846 V564 Z", PAPER, INK, 6)
        page(c, 609, 367, .62, -18)
        page(c, 680, 374, .62, 9)
        book(c, 174, 438, 1.04, -6)
        if relation == "shared":
            hand(c, 369, 311, .71, 13)
    elif motif == "scaffolding":
        for x in (329, 719):
            c.line(x, 180, x, 617, INK, 12)
        for y in (219, 379, 539):
            c.line(296, y, 754, y, INK, 10)
        c.path("M329 219 L719 379 L329 539 M719 219 L329 379 L719 539", "none", INK, 4)
        for x, y, w in ((405, 548, 416), (505, 465, 316), (605, 382, 216)):
            c.rect(x, y, w, 63, PAPER, stroke=INK, stroke_width=5)
            c.rect(x, y, 17, 63, RED)
            c.line(x + 28, y + 48, x + w - 9, y + 48, MUTED, 3)
        book(c, 679, 269, .58, 1)
        hand(c, 929, 538, .7, 180, RED)
    elif motif == "inquiry":
        book(c, 244, 419, 1.88, -5)
        c.path("M335 506 L396 475 L461 509 L532 470 M587 480 L639 443 L703 466", "none", RED, 10)
        lens(c, 818, 285, 1.03, 10)
        c.path("M391 250 H436 Q422 220 450 220 Q478 220 465 250 H509 V292 Q544 278 544 305 Q544 334 509 320 V364 H391 Z", RED, INK, 5)
        if relation == "shared":
            hand(c, 159, 355, .66, -27)
    elif motif == "attention":
        c.circle(549, 292, 145, INK)
        c.circle(549, 292, 110, PAPER)
        for angle in (0, 60, 120, 180, 240, 300):
            c.group(549, 292, 1, angle)
            c.path("M-28 -105 L68 -83 L23 -25 L-18 -32 Z", RED)
            c.end()
        c.path("M496 370 L347 572 H817 L601 370 Z", RED, fill_opacity="0.1")
        book(c, 402, 496, 1.05, 4)
        c.path("M238 296 H312 M789 296 H882 M550 77 V115", "none", INK, 6)
    elif motif == "learning":
        book(c, 149, 433, 1.33, -7)
        for x, y, w in ((514, 533, 305), (594, 449, 225), (674, 365, 145)):
            c.rect(x, y, w, 70, PAPER, stroke=INK, stroke_width=6)
            c.rect(x, y, 16, 70, RED)
        c.path("M835 467 H1024 V588 H835 Z M888 467 V437 H972 V467", PAPER, INK, 7)
        c.path("M850 499 H1008 M926 488 V510", "none", RED, 8)
        if relation == "question":
            lens(c, 781, 262, .55, -16)
        else:
            page(c, 724, 204, .57, 11)
    else:
        book(c, 195, 427, 1.5, -4)
        page(c, 707, 263, 1.1, 15, RED)
        lens(c, 595, 288, .82, -33)
    # Semantic secondary object adds context and changes the silhouette.
    if context == "workplace" and motif not in ("writing", "offloading"):
        screen(c, 947, 545, .42, -3)
    elif context == "mobile" and motif not in ("interruptions", "autonomy", "wellbeing"):
        phone(c, 993, 494, .56, 11)
    elif context == "language" and motif not in ("language", "writing"):
        page(c, 1006, 491, .42, 13)
    c.end()
    draw_subject(c, spec)
    if spec["context"] == "classroom" and spec["setting"] != "classroom":
        # An exercise notebook makes the educational setting visible, including
        # when two pieces share a primary metaphor and secondary subject.
        book(c, 938, 603, .48, -3)
        c.path("M1091 580 L1101 585 L1067 648 L1055 657 L1056 643 Z", RED, INK, 2)
    # Very fine deterministic print marks make same-topic editions distinct without
    # claiming different concepts. No hidden title/metadata makes uniqueness pass.
    x = 78 + int.from_bytes(seed[3:5], "big") / 65535 * 22
    c.line(round(x, 3), 690, round(x + 38 + seed[5] / 8, 3), 690, RED, 7)
    body = "".join(c.parts)
    result = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 760" '
              'width="1200" height="760" role="img">' + body + '</svg>\n').encode()
    if len(result) > MAX_SVG_BYTES:
        raise ValueError("Editorial SVG exceeds its size budget")
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
        if src in seen_assets:
            raise ValueError("Different article overrides must not reuse the same cover")
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


def create_art(record: dict, root: Path = ROOT, overrides: dict | None = None) -> dict:
    identity, inputs = canonical_identity(record), public_inputs(record)
    spec = choose_concept(inputs)
    fingerprint = hashlib.sha256(json.dumps({"identity": identity, "inputs": inputs,
        "renderer_version": RENDERER_VERSION}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    metadata = {"kind": "editorial_illustration", "renderer_version": RENDERER_VERSION,
                "input_fingerprint": fingerprint, **spec,
                "provenance": "Original procedurally composed editorial SVG; not a source figure or empirical diagram."}
    if identity in (overrides or {}):
        override = overrides[identity]
        return {**metadata, **{k: override[k] for k in ("src", "alt", "concept", "provenance", "asset_fingerprint", "width", "height", "thumbnail_src", "thumbnail_fingerprint", "thumbnail_width", "thumbnail_height") if k in override},
                "renderer_version": "editorial-override-1", "semantic_basis": "editor_selected",
                "motif": "editor_selected", "format": Path(override["src"]).suffix.lstrip(".")}
    content = render_svg(identity, inputs, spec)
    metadata["composition_fingerprint"] = hashlib.sha256(render_svg(identity, inputs, spec, microvariation=False)).hexdigest()
    asset_hash = hashlib.sha256(content).hexdigest()
    name = hashlib.sha256(identity.encode()).hexdigest()[:20] + "-" + asset_hash[:24] + ".svg"
    src = GENERATED_DIR + "/" + name
    target = (Path(root) / src).resolve()
    if not target.is_relative_to(Path(root).resolve() / "assets"):
        raise ValueError("Generated asset directory must remain inside local assets")
    write_if_changed(target, content)
    return {**metadata, "src": src, "asset_fingerprint": asset_hash, "format": "svg", "width": 1200, "height": 760}


def attach_art(records: list[dict], root: Path = ROOT, manifest: Path | None = None) -> list[dict]:
    """Decorate ONLY records that the caller has already admitted for publication.

    This is deliberately downstream from build_public's gates. It never promotes
    a record, changes reading depth, replaces visual evidence, or touches provenance.
    """
    overrides = load_overrides(Path(root), manifest)
    for record in records:
        record["editorial_art"] = create_art(record, root, overrides)
    return records


def report(records: list[dict], root: Path) -> dict:
    items = [{"identity": canonical_identity(r), "title": r.get("title", ""), **r["editorial_art"]} for r in records]
    groups = {}
    for item in items:
        if item["semantic_basis"] != "editor_selected":
            groups.setdefault(item["composition_fingerprint"], []).append(item["identity"])
    return {"renderer_version": RENDERER_VERSION, "article_count": len(items),
            "distinct_generated_compositions": len(groups),
            "composition_audit": "SVG geometry compared with identity-based microvariation disabled",
            "semantic_collision_groups": {k: v for k, v in sorted(groups.items()) if len(v) > 1},
            "unique_asset_count": len({r["src"] for r in items}),
            "asset_bytes": sum((root / src).stat().st_size for src in {r["src"] for r in items}),
            "motifs": dict(sorted(Counter(r["motif"] for r in items).items())),
            "semantic_bases": dict(sorted(Counter(r["semantic_basis"] for r in items).items())), "items": items}


def contact_sheet(records: list[dict], root: Path, target: Path):
    import os
    tiles = []
    for r in records:
        art = r["editorial_art"]
        src = os.path.relpath(root / art["src"], target.parent)
        tiles.append('<figure><img loading="lazy" src="' + html.escape(src, quote=True) + '" alt="' +
                     html.escape(art["alt"], quote=True) + '"><figcaption><b>' + html.escape(r.get("title", "")) +
                     '</b><small>' + html.escape(art["motif"] + " · " + art["semantic_basis"]) + '</small></figcaption></figure>')
    content = ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Editorial art contact sheet</title>'
               '<style>body{background:#eee9df;color:#171714;font:14px system-ui;margin:30px}'
               'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}'
               'figure{margin:0;background:#fff}img{display:block;width:100%}figcaption{padding:14px}'
               'small{display:block;color:#655e52;margin-top:8px}</style><h1>Editorial illustrations</h1>'
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

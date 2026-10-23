"""Verify that an RSS/Atom description actually contains a synopsis.

Google News often provides the headline plus publisher name rather than an
article body. Its redirect URL is not a publisher article URL. Such records
are internal leads, not article-based public analysis.
"""
import re
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

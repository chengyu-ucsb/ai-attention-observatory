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

def substantive_article(record):
    # A separately verified companion is worth linking even when its only
    # stored text is a concise attributed publisher synopsis.
    if record.get("companion_to") and publisher_url(record.get("url")):
        return bool((record.get("reading") or {}).get("overview"))
    if record.get("content_access")=="editorially_read_source":
        return bool((record.get("editorial_notes") or {}).get("argument")) and publisher_url(record.get("url"))
    if record.get("deep_analysis",{}).get("source_depth")=="source_html":
        return publisher_url(record.get("url"))
    if record.get("source")=="Publisher RSS / Google News RSS":
        return publisher_url(record.get("url")) and useful_description(
            record.get("title"),(record.get("reading") or {}).get("overview") or record.get("preview"),record.get("venue"))
    return bool((record.get("editorial_notes") or {}).get("argument") or
                useful_description(record.get("title"),(record.get("reading") or {}).get("overview") or record.get("preview")))

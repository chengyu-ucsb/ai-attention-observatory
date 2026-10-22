"""Trace source relationships without counting a public explainer as new research.

Verified author explainers may point to an original scholarly publication. An
explicit link (or an editor-verified relationship) is required: shared keywords,
authors or argument similarity alone are NOT evidence of common origin.
"""
import copy
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
LINKS = ROOT / "data/source-lineage.json"


def canonical_url(url):
    try:
        parsed = urlsplit(str(url or "").strip())
        if parsed.scheme != "https" or not parsed.netloc:
            return ""
        return urlunsplit(("https", parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))
    except ValueError:
        return ""


def load(path=None):
    return json.loads(Path(path or LINKS).read_text(encoding="utf-8"))


def prepare(records, config=None):
    """Add verified missing primary publications; attach—not clone—commentary.

    The caller owns persistence. Repeated runs are idempotent, and a real
    harvested scholarly record is not overwritten by a manually supplied seed.
    """
    config = config if config is not None else load()
    urls_present = {canonical_url(x.get("url")) for x in records if canonical_url(x.get("url"))}
    related_dois = {str(x.get("primary_doi") or "").lower() for x in config.get("connections", [])
                    if canonical_url(x.get("commentary_url")) in urls_present}
    by_doi = {str(x.get("doi") or "").lower(): x
              for x in records if x.get("kind") == "scholarly" and x.get("doi")}
    for primary in config.get("primary_publications", []):
        doi = str(primary.get("doi") or "").lower()
        if doi not in related_dois and doi not in by_doi:
            continue
        if not doi.startswith("10.") or not primary.get("abstract_source") or not primary.get("url"):
            continue
        if doi not in by_doi:
            record = dict(copy.deepcopy(primary), doi=doi, kind="scholarly", curated=False,
                          evidence="Verified conceptual publication; source abstract/summary only",
                          preview=primary.get("abstract_text", "")[:420])
            records.append(record)
            by_doi[doi] = record
        else:
            found = by_doi[doi]
            # Explicit type/provenance can be retained on a record supplied
            # independently by bibliographic discovery.
            for key in ("research_type", "framework_notes"):
                if not found.get(key) and primary.get(key):
                    found[key] = copy.deepcopy(primary[key])
    by_url = {canonical_url(x.get("url")): x for x in records if canonical_url(x.get("url"))}
    for relation in config.get("connections", []):
        original = by_doi.get(str(relation.get("primary_doi") or "").lower())
        article = by_url.get(canonical_url(relation.get("commentary_url")))
        if not original or not article or article.get("kind") != "nonacademic":
            continue
        article["companion_to"] = original["doi"].lower()
        article["companion_relation"] = relation.get("relation", "Discussion of the original publication")
        article["companion_verified_via"] = relation.get("verified_via", "")
        article["format"] = article.get("format") or "Author commentary"
    return records


def primary_for(article, records):
    doi = (article.get("companion_to") or "").lower()
    return next((r for r in records if r.get("kind") == "scholarly"
                 and str(r.get("doi") or "").lower() == doi), None)

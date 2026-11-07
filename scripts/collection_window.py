"""Strict publication-day gates shared by every weekly collection stage.

An edition collected on any day of a UTC Monday–Sunday week covers the
previous completed Monday–Sunday week. Discovery/index/update timestamps
are never publication evidence. Partial dates are never padded.
"""
from __future__ import annotations

import datetime as dt
import re


def publication_date(value):
    """Return an exact UTC day, or None for missing/partial/invalid dates."""
    if isinstance(value, dt.datetime):
        return (value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None
                else value.astimezone(dt.timezone.utc)).date()
    if isinstance(value, dt.date):
        return value
    if not isinstance(value, str):
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return dt.date.fromisoformat(value)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[Zz]|[+-]\d{2}:\d{2})?", value):
            return publication_date(dt.datetime.fromisoformat(value.upper().replace("Z", "+00:00")))
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def previous_week(now=None):
    """Return inclusive date bounds for the previous completed UTC week."""
    today = publication_date(now if now is not None else dt.datetime.now(dt.timezone.utc))
    if today is None:
        raise ValueError("A complete ISO date or datetime is required")
    monday = today - dt.timedelta(days=today.weekday())
    return monday - dt.timedelta(days=7), monday - dt.timedelta(days=1)


def date_in_window(value, start, end):
    day, first, last = map(publication_date, (value, start, end))
    return day is not None and first is not None and last is not None and first <= day <= last


def window_metadata(now=None):
    start, end = previous_week(now)
    return {"from": start.isoformat(), "to": end.isoformat(), "timezone": "UTC",
            "basis": "original publication date", "inclusive": True,
            "scope": "original_publication_date_previous_completed_week"}


def weekly_eligible(record, start, end):
    """Nominations and first_seen dates cannot override the date gate."""
    provenance = record.get("publication_date_provenance") or {}
    if not isinstance(provenance,dict) or provenance.get("status") in {"unresolved","conflict","conflicting","unknown"}:return False
    day=publication_date(record.get("published"))
    evidence_day=publication_date(provenance.get("value") or provenance.get("date"))
    if day is None or evidence_day!=day:return False
    basis=provenance.get("basis")
    original_publisher=basis in {"publisher_rss_pubDate","publisher_atom_published","publisher_datePublished",
        "publisher_meta_published_time","editor_verified_original_publication_date"}
    registry=(provenance.get("status")=="day_known" and provenance.get("source")=="Crossref publisher metadata"
        and provenance.get("field") in {"published-online","published-print","published","issued"})
    arxiv=(provenance.get("status")=="day_known" and basis=="arxiv_first_submitted" and provenance.get("field")=="published")
    if not (original_publisher or registry or arxiv):return False
    if record.get("kind") not in {"scholarly","nonacademic"}:return False
    from urllib.parse import urlsplit
    try:
        if urlsplit(record.get("url") or "").hostname=="news.google.com":return False
    except ValueError:return False
    if (record.get('original_reading') is not None or (record.get('reading') or {}).get('original_summary')
            or record.get('original_summary') or record.get('original_reading_sha256')):
        from original_readings import weekly_source_eligible
        if not weekly_source_eligible(record):return False
    return (date_in_window(day,start,end) and not record.get("historical_backfill")
            and not str(record.get("discovery_scope", "")).startswith("historical:"))


def crossref_publication(work):
    """Choose the earliest precise publication event, retaining registry evidence.

    Crossref's created/deposited/indexed dates describe registry activity, not
    publication. Online-first publication beats a later print/issue date. An
    imprecise online/print event that could predate the chosen day makes the
    original day unresolved; it is not silently replaced with a print date.
    """
    evidence, exact, uncertain_events = [], [], []
    for field in ("published-online", "published-print", "published", "issued"):
        raw=work.get(field)
        if raw is None:continue
        outer=raw.get("date-parts") if isinstance(raw,dict) else None
        if not isinstance(outer,list) or not outer or not isinstance(outer[0],list) or not outer[0]:
            evidence.append({"field":field,"precision":"unresolved"})
            uncertain_events.append(dt.date.min)
            continue
        parts=outer[0]
        item = {"field": field, "date_parts": parts}
        day = None
        if len(parts) == 3 and all(type(p) is int for p in parts):
            try:
                day = dt.date(*parts)
            except ValueError:
                pass
        item["precision"] = "day" if day else "unresolved"
        evidence.append(item)
        if day:
            exact.append((day, field))
        else:
            # This bound is only an uncertainty check, never a saved date.
            try:
                lower = dt.date(parts[0], parts[1] if len(parts) > 1 else 1, 1)
            except (ValueError, TypeError, IndexError):
                lower = dt.date.min
            uncertain_events.append(lower)
    provenance = {"source": "Crossref publisher metadata", "evidence": evidence,
                  "policy": "earliest precise publication event; no registry timestamp fallback"}
    if not exact:
        return "", dict(provenance, status="unresolved")
    day, field = min(exact, key=lambda pair: pair[0])
    if any(lower < day for lower in uncertain_events):
        return "", dict(provenance, status="unresolved", reason="Earlier publication event has no exact day")
    return day.isoformat(), dict(provenance, status="day_known", field=field, value=day.isoformat())

def reconcile_publication_evidence(previous, incoming):
 """Combine repeated provider evidence without promoting a later event."""
 if previous is None:return incoming
 if previous[1].get("requires_explicit_date_resolution"):return previous
 if incoming[1].get("requires_explicit_date_resolution"):return incoming
 # Missing original-day evidence is not repaired by selecting a convenient
 # later response. Temporary provider failures alone do not erase good data.
 if not incoming[0]:return previous if incoming[1].get("verification_error") else incoming
 if not previous[0]:return incoming if previous[1].get("verification_error") else previous
 return previous if previous[0]<=incoming[0] else incoming


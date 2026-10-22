"""Recover lawfully reusable Zenodo publication PDFs by their exact Zenodo DOI.

Zenodo records are public and individually license-checked. The file endpoint
is constructed from the record ID and a verified PDF entry; arbitrary record
links and redirects to unapproved hosts are never followed. Downloaded bytes
remain in memory, and automatic article sections need independent review.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from enrich_pdf_fulltext import clean, extract_pdf

ZENODO_DOI = re.compile(r"^10\.5281/zenodo\.(\d+)$", re.I)
MAX_PDF = 18_000_000
USER_AGENT = "AI-Attention-Observatory/4.4 (academic research; fangcu@ucmail.uc.edu)"
PERMISSIVE = {"cc-by", "cc-by-sa", "cc0"}
EXCLUDED_FILES = re.compile(r"suppl|appendix|supporting|slides|poster|presentation", re.I)


def license_name(value):
    text = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    text = re.sub(r"^https?://(?:www\.)?creativecommons\.org/licenses/", "", text)
    text = text.rstrip("/")
    if any(x in text for x in ("-nc", "-nd", "noncommercial", "noderivatives")):
        return ""
    if re.fullmatch(r"(?:cc-)?by(?:[-/]\d(?:\.\d)?)?", text):
        return "cc-by"
    if re.fullmatch(r"(?:cc-)?by-sa(?:[-/]\d(?:\.\d)?)?", text):
        return "cc-by-sa"
    if re.fullmatch(r"cc0(?:[-/]\d(?:\.\d)?)?|public-domain", text):
        return "cc0"
    return ""


def record_license(work):
    meta = work.get("metadata") or {}
    choices = meta.get("rights") or []
    if not isinstance(choices, list):
        choices = []
    if not choices:
        choices = [meta.get("license")]
    for item in choices:
        value = item.get("id") if isinstance(item, dict) else item
        permitted = license_name(value)
        if permitted:
            # Mixed or conflicting rights cannot authorize the article PDF.
            if len(choices) != 1:
                return ""
            return permitted
    return ""


def verified_record(work, doi):
    identifiers = [
        work.get("doi"),
        (work.get("metadata") or {}).get("doi"),
        ((work.get("pids") or {}).get("doi") or {}).get("identifier"),
    ]
    if not any(str(x or "").strip().lower() == doi.lower() for x in identifiers):
        return False
    meta = work.get("metadata") or {}
    access = work.get("access") or {}
    if meta.get("access_right") not in (None, "open"):
        return False
    if access.get("files") not in (None, "public"):
        return False
    if work.get("is_published") is False:
        return False
    return True


def pdf_keys(work):
    files = work.get("files") or []
    if isinstance(files, dict):
        if files.get("enabled") is False:
            return []
        entries = files.get("entries") or {}
        files = list(entries.values()) if isinstance(entries, dict) else []
    if not isinstance(files, list):
        return []
    found = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        size = entry.get("size")
        if not key.lower().endswith(".pdf") or EXCLUDED_FILES.search(key):
            continue
        if len(key) > 250 or not key or "/" in key or "\\" in key:
            continue
        if size is not None and (not isinstance(size, int) or size > MAX_PDF or size < 200):
            continue
        found.append(key)
    return found[:2]


class ZenodoRedirectGuard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).hostname != "zenodo.org" or not newurl.startswith("https://"):
            raise ValueError("Zenodo download redirected outside official host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request_bytes(url, limit):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "zenodo.org" or parsed.port not in (None, 443) or parsed.username:
        raise ValueError("Unapproved Zenodo request URL")
    opener = urllib.request.build_opener(ZenodoRedirectGuard())
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,application/pdf"})
    with opener.open(req, timeout=25) as response:
        if urllib.parse.urlsplit(response.geturl()).hostname != "zenodo.org":
            raise ValueError("Unapproved final Zenodo URL")
        length = response.headers.get("Content-Length")
        if length and int(length) > limit:
            raise ValueError("Oversize Zenodo response")
        content = response.read(limit + 1)
        if len(content) > limit:
            raise ValueError("Oversize Zenodo response")
        return content


def metadata(record_id):
    raw = request_bytes(f"https://zenodo.org/api/records/{record_id}", 2_000_000)
    work = json.loads(raw)
    if not isinstance(work, dict):
        raise ValueError("Zenodo response was not a record")
    return work


def download_pdf(record_id, file_key):
    # Ignore URLs embedded in the response: only the exact published record
    # and named PDF file on Zenodo's official file API may be requested.
    name = urllib.parse.quote(file_key, safe="")
    raw = request_bytes(f"https://zenodo.org/api/records/{record_id}/files/{name}/content", MAX_PDF)
    if not raw.startswith(b"%PDF"):
        raise ValueError("Zenodo file was not a PDF")
    return raw


def eligible(row, today):
    if row.get("kind") != "scholarly" or row.get("analysis"):
        return False
    if not ZENODO_DOI.fullmatch(str(row.get("doi") or "").strip()):
        return False
    old = row.get("zenodo_recovery") or {}
    if old.get("version") != 1:
        return True
    try:
        return dt.date.fromisoformat(old.get("next_at", "")) <= today
    except (ValueError, TypeError):
        return True


def checkpoint(row, status, today):
    interval = 365 if status == "full_text_recovered" else 3 if status in ("temporary_error", "rate_limited") else 30
    old = row.setdefault("zenodo_recovery", {})
    old.update(version=1, status=status, last_at=today.isoformat(),
               next_at=(today + dt.timedelta(days=interval)).isoformat(),
               attempts=old.get("attempts", 0) + 1)


def recover_due(records, today=None):
    today = today or dt.date.today()
    limit = max(1, min(int(os.getenv("ZENODO_OA_BATCH", "8")), 20))
    candidates = [x for x in records if eligible(x, today)]
    candidates.sort(key=lambda x: (int((x.get("zenodo_recovery") or {}).get("attempts", 0)),
                                   x.get("published") or ""))
    stats = {"attempted": 0, "recovered": 0, "license_unverified": 0,
             "no_pdf": 0, "record_unavailable": 0, "pdf_unreadable": 0,
             "temporary_error": 0, "rate_limited": 0}
    for row in candidates[:limit]:
        match = ZENODO_DOI.fullmatch(row["doi"].strip())
        record_id = match.group(1)
        status = "record_unavailable"
        stats["attempted"] += 1
        try:
            work = metadata(record_id)
            if not verified_record(work, row["doi"]):
                status = "record_unavailable"
            else:
                license_id = record_license(work)
                if not license_id:
                    status = "license_unverified"
                else:
                    keys = pdf_keys(work)
                    status = "no_pdf" if not keys else "pdf_unreadable"
                    for key in keys:
                        try:
                            sections = extract_pdf(download_pdf(record_id, key))
                        except (ValueError, urllib.error.URLError, TimeoutError, urllib.error.HTTPError):
                            continue
                        if not (sections.get("results") or sections.get("discussion")):
                            continue
                        landing = f"https://zenodo.org/records/{record_id}"
                        row["analysis"] = {
                            "provenance": "Zenodo exact-DOI licensed publication PDF; pypdf automatic extraction",
                            "license": license_id,
                            "license_url": landing,
                            "fulltext_url": landing,
                            "methods": sections.get("methods", ""),
                            "results": sections.get("results", ""),
                            "discussion": sections.get("discussion", ""),
                            "limitations": sections.get("limitations", ""),
                            "figures": [],
                            "key_idea": clean(sections.get("results") or sections.get("discussion"))[:280],
                            "extraction_date": today.isoformat(),
                            "extraction_version": 1,
                            "sections_available": list(sections),
                            "pdf_text_extraction": "pypdf; automatic section boundaries; verify original"
                        }
                        status = "full_text_recovered"
                        break
        except urllib.error.HTTPError as exc:
            status = "rate_limited" if exc.code == 429 else "record_unavailable" if exc.code in (403, 404) else "temporary_error"
        except (urllib.error.URLError, TimeoutError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            status = "temporary_error"
        checkpoint(row, status, today)
        stats["recovered" if status == "full_text_recovered" else status] += 1
        if status == "rate_limited":
            break
    return stats

"""Bounded publisher metadata verification, without saving article text.

This is independent of discovery and full-text acquisition. Only original
publication fields and explicit article genres can strengthen feed metadata.
Conflicting dates remain unresolved until explicit editorial adjudication.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import time
import tempfile
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit
from urllib.request import Request, build_opener
from urllib.robotparser import RobotFileParser

from collection_window import date_in_window, previous_week, publication_date, weekly_eligible, window_metadata
import full_document_access as access

MAX_HTML_BYTES = 2_000_000
VERSION = 1
UNRESOLVED = {"unresolved", "conflict", "conflicting", "unknown"}
ORIGINAL_BASES = {"publisher_rss_pubDate", "publisher_atom_published", "publisher_datePublished",
                  "publisher_meta_published_time", "editor_verified_original_publication_date"}
DATE_META = {"article:published_time", "datepublished", "citation_publication_date",
             "dc.date.issued", "dcterms.issued", "parsely-pub-date"}
TITLE_META = {"og:title", "twitter:title", "citation_title"}
TYPE_META = {"article:section", "article:type", "parsely-section"}
GENRES = {
    "opinion": "opinion", "commentary": "opinion", "editorial": "opinion", "perspective": "opinion",
    "analysis": "analysis", "explainer": "analysis", "policy analysis": "policy",
    "policy brief": "policy", "policy": "policy", "news": "journalism", "reporting": "journalism",
    "investigation": "journalism", "investigative reporting": "journalism",
}
SCHEMA_GENRES = {"OpinionNewsArticle": "opinion", "AnalysisNewsArticle": "analysis",
                 "ReportageNewsArticle": "journalism", "NewsArticle": "journalism"}
ARTICLE_TYPES = {"Article", "BlogPosting", "Report", "ScholarlyArticle", *SCHEMA_GENRES}
TRACKING = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "ref_src", "ref_url"}


def stamp(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def normal(value):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", str(value)).casefold()))


def identity_url(value):
    """Keep meaningful query identity in memory; never save query strings."""
    try:
        p = urlsplit(value)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
            return ""
        params = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                  if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
        return p.hostname.lower() + p.path.rstrip("/") + ("?" + urlencode(sorted(params)) if params else "")
    except (ValueError, TypeError):
        return ""


def day(value):
    # Do not accept dateModified, partial dates, epochs, or free-text guesses.
    exact = publication_date(value)
    if exact:
        return exact.isoformat()
    return ""


def strings(value):
    return [x for x in (value if isinstance(value, list) else [value]) if isinstance(x, str)]


def schema_types(node):
    return {value.rsplit("/", 1)[-1].rsplit("#", 1)[-1] for value in strings(node.get("@type"))}


def nodes(value, depth=0):
    """Bound recursive traversal; JSON-LD recommendations are not page evidence."""
    if depth > 12:
        raise ValueError("metadata_structure_limit")
    if isinstance(value, dict):
        yield value
        for key in ("@graph", "mainEntity"):
            yield from nodes(value.get(key), depth + 1)
    elif isinstance(value, list):
        if len(value) > 100:
            raise ValueError("metadata_structure_limit")
        for child in value:
            yield from nodes(child, depth + 1)


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = []
        self.canonicals = []
        self.titles = []
        self.jsonld = []
        self.capture = None
        self.buffer = []
        self.buffer_size = 0

    def handle_starttag(self, tag, attrs):
        attrs = {k.lower(): v or "" for k, v in attrs}
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
            if key in DATE_META | TITLE_META | TYPE_META | {"og:url", "isaccessibleforfree"}:
                self.meta.append((key, attrs.get("content", "")[:2000]))
        if tag == "link" and "canonical" in attrs.get("rel", "").lower().split():
            self.canonicals.append(attrs.get("href", "")[:2000])
        if tag in ("title", "h1") or (tag == "script" and attrs.get("type", "").lower() == "application/ld+json"):
            self.capture = tag
            self.buffer = []
            self.buffer_size = 0

    def handle_data(self, data):
        if self.capture and self.buffer_size < 300_000:
            self.buffer.append(data[:300_000 - self.buffer_size])
            self.buffer_size += len(data)

    def handle_endtag(self, tag):
        if self.capture != tag:
            return
        content = "".join(self.buffer)
        if tag == "script":
            try:
                self.jsonld.extend(nodes(json.loads(content)))
            except (ValueError, RecursionError):
                pass
        else:
            self.titles.append((tag, content[:1000]))
        self.capture = None
        self.buffer = []


def parse_metadata(page, url):
    """Pure HTML parser. Return metadata only, never body text or script source."""
    if isinstance(page, bytes):
        page = page.decode("utf-8", "replace")
    if not isinstance(page, str) or len(page.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("document_too_large")
    if access.BLOCKED.search(page[:18000]):
        raise ValueError("access_challenge_not_article")
    parsed = MetadataParser()
    parsed.feed(page)
    articles = []
    for node in parsed.jsonld:
        types = schema_types(node)
        if not types & ARTICLE_TYPES:
            continue
        urls = strings(node.get("url"))
        entity = node.get("mainEntityOfPage")
        if isinstance(entity, dict):
            urls += strings(entity.get("@id") or entity.get("url"))
        else:
            urls += strings(entity)
        # @id often names a fragment of this page, but may be an unrelated ID.
        urls += strings(node.get("@id"))
        articles.append({"titles": strings(node.get("headline")) or strings(node.get("name")),
                         "urls": [urljoin(url, value) for value in urls],
                         "date_present": "datePublished" in node,
                         "dates": strings(node.get("datePublished")),
                         "sections": strings(node.get("articleSection")) + strings(node.get("genre")),
                         "types": sorted(types), "restricted": node.get("isAccessibleForFree") in (False, "false")})
    return {"titles": parsed.titles + [(k, v) for k, v in parsed.meta if k in TITLE_META],
            "urls": [urljoin(url, x) for x in parsed.canonicals] +
                    [urljoin(url, v) for k, v in parsed.meta if k == "og:url"],
            "dates": [(k, v) for k, v in parsed.meta if k in DATE_META],
            "sections": [(k, v) for k, v in parsed.meta if k in TYPE_META],
            "articles": articles,
            "restricted": any(k == "isaccessibleforfree" and v.lower() == "false" for k, v in parsed.meta)}


def title_matches(expected, candidate, venue="", field=""):
    key, found = normal(expected), normal(candidate)
    if len(key) < 12:
        return False
    if key == found:
        return True
    return bool(field == "title" and venue and found in {key + " " + normal(venue), normal(venue) + " " + key})


def evidence_item(field, value, basis, url):
    # Values are normalized dates or a bounded explicit genre, never raw text.
    return {"field": field, "date": day(value), "basis": basis,
            "source_url": access.diagnostic_url(url), "precision": "day" if day(value) else "unresolved"}


def prior_evidence(record):
    provenance = record.get("publication_date_provenance") or {}
    result = []
    # Preserve established evidence order on repeat checks. Reordering identical
    # evidence would also change the article-screen receipt's record hash.
    for row in (provenance.get("evidence") or []) + [provenance]:
        if not isinstance(row, dict):
            continue
        value = row.get("value") or row.get("date")
        if row.get("basis") in ORIGINAL_BASES and day(value):
            result.append(evidence_item(str(row.get("field") or row["basis"]), value, row["basis"], row.get("source_url", "")))
    return result


def unique(rows):
    return list({json.dumps(row, sort_keys=True): row for row in rows}.values())


def verify_record(record, page, *, url=None, checked_at=None):
    """Pure verification returning a copied record, preserving article readings.

    A no-date page does not invalidate a trusted feed date. Explicitly partial
    or conflicting original-date fields do: there is then contrary evidence.
    Old conflicts are never auto-cleared, even by a later matching page.
    """
    output = deepcopy(record)
    url = url or record.get("url", "")
    now = stamp(checked_at).isoformat()
    report = {"version": VERSION, "checked_at": now, "source_url": access.diagnostic_url(url),
              "status": "unresolved", "identity": "unverified", "date_status": "unresolved",
              "source_type_status": "unresolved", "source_text_saved": False}
    output["editorial_metadata"] = report
    if record.get("kind") != "nonacademic":
        report["status"] = "not_nonacademic"
        return output
    expected_url = record.get("url", "")
    if not identity_url(expected_url) or not identity_url(url) or urlsplit(url).hostname != urlsplit(expected_url).hostname:
        report["status"] = "publisher_host_mismatch"
        return output
    if identity_url(expected_url) != identity_url(url):
        report["status"] = "canonical_identity_mismatch"
        return output
    metadata = parse_metadata(page, url)
    identity = identity_url(url)
    if any(identity_url(value) != identity for value in metadata["urls"]):
        report["status"] = "canonical_identity_mismatch"
        return output
    title, venue = record.get("title", ""), record.get("venue", "")
    page_match = any(title_matches(title, value, venue, field) for field, value in metadata["titles"])
    strong = [(field, value) for field, value in metadata["titles"] if field in {"og:title", "citation_title"}]
    if strong and not all(title_matches(title, value, venue, field) for field, value in strong):
        report["status"] = "title_identity_mismatch"
        return output
    selected = []
    for article in metadata["articles"]:
        if article["urls"] and any(identity_url(value) != identity for value in article["urls"]):
            continue
        if any(title_matches(title, value) for value in article["titles"]) or (not article["titles"] and article["urls"] and page_match):
            selected.append(article)
    if not page_match and not selected:
        report["status"] = "title_identity_unverified"
        return output
    report["identity"] = "verified"
    if metadata["restricted"] or any(article["restricted"] for article in selected):
        report["status"] = "publisher_access_restricted"
        return output
    dates = [evidence_item(field, value, "publisher_meta_published_time", url) for field, value in metadata["dates"]]
    genres = [(field, value) for field, value in metadata["sections"]]
    for article in selected:
        if article["date_present"]:
            dates.extend(evidence_item("datePublished", value, "publisher_datePublished", url) for value in article["dates"] or [None])
        genres.extend(("articleSection_or_genre", value) for value in article["sections"])
        types = set(article["types"])
        # Specific genre supersedes generic NewsArticle, not other explicit labels.
        genres.extend(("@type", value) for value in types & SCHEMA_GENRES.keys() if value != "NewsArticle")
        if "NewsArticle" in types and not any(value.casefold().strip() in GENRES for _, value in genres) and not types & (SCHEMA_GENRES.keys() - {"NewsArticle"}):
            genres.append(("@type", "NewsArticle"))
    provenance = record.get("publication_date_provenance") or {}
    all_dates = unique(prior_evidence(record) + dates)
    values = {row["date"] for row in all_dates if row["date"]}
    stored = day(record.get("published"))
    conflicting = len(values) > 1 or (stored and dates and any(row["date"] and row["date"] != stored for row in dates))
    existing_conflict = provenance.get("status") in UNRESOLVED and (
        "conflict" in provenance.get("reason", "") or provenance.get("requires_explicit_date_resolution") or len(values) > 1)
    uncertain = any(row["precision"] != "day" for row in dates)
    if conflicting or existing_conflict or uncertain:
        reason = "conflicting_original_publication_dates" if conflicting or existing_conflict else "imprecise_publisher_original_date"
        output["publication_date_provenance"] = {"status": "unresolved", "reason": reason,
            "requires_explicit_date_resolution": True, "stored_publication_date": record.get("published", ""),
            "evidence": all_dates, "checked_at": now}
        report["date_status"] = "conflict" if conflicting or existing_conflict else "unresolved"
    elif dates and values:
        selected_date = next(row for row in dates if row["date"])
        output["published"] = selected_date["date"]
        output["publication_date_provenance"] = {"status": "day_known", "basis": selected_date["basis"],
            "field": selected_date["field"], "value": selected_date["date"], "date": selected_date["date"],
            "timezone": "UTC", "source_url": access.diagnostic_url(url), "evidence": all_dates,
            "independently_verified": True, "checked_at": now}
        # Keep the timestamp of unchanged date evidence stable. The per-run
        # editorial_metadata report above still records this verification time.
        # Rewriting only checked_at would invalidate source-bound reading receipts
        # despite no change in identity, original date, or supporting evidence.
        candidate = output["publication_date_provenance"]
        if (provenance.get("checked_at")
                and {k: v for k, v in provenance.items() if k != "checked_at"}
                == {k: v for k, v in candidate.items() if k != "checked_at"}):
            candidate["checked_at"] = provenance["checked_at"]
        report["date_status"] = "verified"
    elif provenance.get("basis") in ORIGINAL_BASES and provenance.get("status") not in UNRESOLVED and day(provenance.get("value") or provenance.get("date")) == stored:
        report["date_status"] = "publisher_feed_only" if provenance["basis"] in {"publisher_rss_pubDate", "publisher_atom_published"} else "previously_verified"
    kinds = set()
    genre_evidence = []
    for field, value in genres:
        kind = SCHEMA_GENRES.get(value) if field == "@type" else GENRES.get(value.casefold().strip())
        if kind:
            kinds.add(kind)
            genre_evidence.append({"field": field, "label": value[:80], "source_type": kind})
    if record.get("source_type_basis") in {"publisher_item_category", "publisher_structured_metadata"} and record.get("source_type"):
        if kinds and record["source_type"] not in kinds:
            kinds.add(record["source_type"])
    previous_type = record.get("editorial_metadata") or {}
    if previous_type.get("source_type_status") == "conflict":
        kinds.update(item.get("source_type") for item in previous_type.get("source_type_evidence", [])
                     if item.get("source_type") in {"journalism", "opinion", "policy", "analysis"})
        genre_evidence = previous_type.get("source_type_evidence", []) + genre_evidence
    if len(kinds) == 1:
        output["source_type"] = next(iter(kinds))
        output["source_type_basis"] = "publisher_structured_metadata"
        report["source_type_status"] = "verified"
    elif len(kinds) > 1:
        report["source_type_status"] = "conflict"
    if genre_evidence:
        report["source_type_evidence"] = unique(genre_evidence)
    report["status"] = "verified" if report["date_status"] == "verified" else "date_conflict" if report["date_status"] == "conflict" else "metadata_incomplete"
    return output


class BudgetExceeded(ValueError):
    pass


class Budget:
    def __init__(self, max_requests, deadline_seconds, clock=time.monotonic):
        self.max_requests = max(0, max_requests)
        self.clock = clock
        self.deadline = clock() + max(0, deadline_seconds)
        self.requests = 0

    def take(self):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise BudgetExceeded("deadline")
        if self.requests >= self.max_requests:
            raise BudgetExceeded("request_budget")
        self.requests += 1
        return min(22, remaining)


class MetadataFetcher:
    """Anonymous, exact-host HTTPS requests, including robots and redirects.

    Budget counts each network request (redirects included). No locator search,
    alternate route, saved login, API key, or article-body persistence exists.
    """
    def __init__(self, budget):
        self.budget = budget
        self.hosts = set(access.ARTICLE_HOSTS)  # disables legacy suffix allowance
        self.robots = {}

    def request(self, url, limit):
        if not access.safe_url(url, self.hosts) or not access.anonymous_source_url(url):
            raise ValueError("unapproved_or_credentialed_source_url")
        budget, hosts, robots = self.budget, self.hosts, self.robots

        class Guard(access.Guard):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                if not access.anonymous_source_url(newurl):
                    raise ValueError("credentialed_source_url_disallowed")
                result = super().redirect_request(req, fp, code, msg, headers, newurl)
                target = urlsplit(newurl)
                policy = robots.get(target.scheme + "://" + target.netloc)
                if policy is not None and policy is not True and not policy.can_fetch(access.AGENT, newurl):
                    raise ValueError("robots_disallow")
                req.timeout = budget.take()
                return result

        request = Request(url, headers={"User-Agent": access.AGENT, "Accept": "text/html,application/xhtml+xml,text/plain"})
        with build_opener(Guard(hosts)).open(request, timeout=budget.take()) as response:
            if response.headers.get("Content-Length", "").isdigit() and int(response.headers["Content-Length"]) > limit:
                raise ValueError("document_too_large")
            chunks, total = [], 0
            while total <= limit:
                if budget.clock() >= budget.deadline:
                    raise BudgetExceeded("deadline")
                # read1 performs at most one buffered/raw read. Recheck the
                # deadline between reads, even on a slow streaming response.
                remaining = budget.deadline - budget.clock()
                socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                if socket is not None:
                    socket.settimeout(max(.001, min(22, remaining)))
                reader = getattr(response, "read1", response.read)
                chunk = reader(min(65536, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            if total > limit:
                raise ValueError("document_too_large")
            return b"".join(chunks), response.geturl(), response.headers.get("Content-Type", "")

    def __call__(self, url):
        if not access.safe_url(url, self.hosts) or not access.anonymous_source_url(url):
            raise ValueError("unapproved_or_credentialed_source_url")
        p = urlsplit(url)
        origin = p.scheme + "://" + p.netloc
        if origin not in self.robots:
            try:
                body, _, _ = self.request(origin + "/robots.txt", 500_000)
                parser = RobotFileParser()
                parser.parse(body.decode("utf-8", "replace").splitlines())
                self.robots[origin] = parser
            except HTTPError as exc:
                if exc.code == 404:
                    self.robots[origin] = True
                else:
                    raise
        robots = self.robots[origin]
        if robots is not True and not robots.can_fetch(access.AGENT, url):
            raise ValueError("robots_disallow")
        body, final, content_type = self.request(url, MAX_HTML_BYTES)
        if not any(kind in content_type.lower() for kind in ("text/html", "application/xhtml+xml")):
            raise ValueError("not_html")
        return body, final


def fingerprint(record):
    provenance = record.get("publication_date_provenance") or {}
    identity = {"version": VERSION, "title": record.get("title"), "url": record.get("url"),
                "published": record.get("published"), "basis": provenance.get("basis"),
                "status": provenance.get("status"), "source_type": record.get("source_type"),
                "source_type_basis": record.get("source_type_basis"),
                # State is saved before the library. Include the saved result so
                # an interrupted library write cannot look already complete.
                "metadata_result": {key: (record.get("editorial_metadata") or {}).get(key)
                    for key in ("version", "checked_at", "status", "identity", "date_status", "source_type_status")}}
    return sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def record_key(record):
    return sha256(identity_url(record.get("url", "")).encode()).hexdigest()


def failure(exc, now):
    """Sanitized diagnostics only: exception bodies may contain article text."""
    if isinstance(exc, HTTPError):
        code = exc.code
        result = {"status": "http_" + str(code), "retryable": code in {408, 425, 429} or 500 <= code < 600}
        if result["retryable"]:
            value = (exc.headers or {}).get("Retry-After", "")
            seconds = 3600
            if str(value).isdigit():
                seconds = int(value)
            elif value:
                try:
                    seconds = int((stamp(parsedate_to_datetime(value)) - now).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    pass
            maximum = int((datetime.max.replace(tzinfo=timezone.utc) - now).total_seconds())
            if seconds > maximum:
                result.update(retryable=False, blocked=True)
            else:
                result["retry_after_seconds"] = max(1, seconds)
        return result
    allowed = {"document_too_large", "access_challenge_not_article", "publisher_access_restricted",
               "unapproved_or_credentialed_source_url", "credentialed_source_url_disallowed", "unapproved_redirect",
               "cross_host_redirect_requires_review", "robots_disallow", "not_html"}
    result = {"status": str(exc) if isinstance(exc, ValueError) and str(exc) in allowed else type(exc).__name__ if type(exc).__name__ in {"TimeoutError", "URLError", "ConnectionError", "OSError"} else "unknown_failure",
              "retryable": isinstance(exc, (TimeoutError, URLError, ConnectionError))}
    if result["retryable"]:
        result["retry_after_seconds"] = 3600
    return result


def validate_state(state):
    """Fail closed on corrupt structural/backoff state, rather than retrying it."""
    if state is None:
        return
    if not isinstance(state, dict) or state.get("schema_version", VERSION) != VERSION:
        raise ValueError("invalid_metadata_state_schema")
    for collection in ("records", "host_backoff"):
        rows = state.get(collection, {})
        if not isinstance(rows, dict) or any(not isinstance(row, dict) for row in rows.values()):
            raise ValueError("invalid_metadata_state_records")
        for row in rows.values():
            for field in ("blocked", "complete"):
                if field in row and type(row[field]) is not bool:
                    raise ValueError("invalid_metadata_state_boolean")
            if "attempts" in row and (type(row["attempts"]) is not int or row["attempts"] < 0):
                raise ValueError("invalid_metadata_state_attempts")
            for field in ("until", "next_retry_at", "last_attempt_at", "checked_at"):
                if field not in row:
                    continue
                try:
                    if not isinstance(row[field], str) or not row[field]:
                        raise ValueError("invalid timestamp")
                    stamp(row[field])
                except (TypeError, ValueError, OverflowError, AttributeError) as exc:
                    raise ValueError("invalid_metadata_state_timestamp") from exc


def clean_state(state):
    """Use only this module's closed schema, never relay arbitrary saved fields."""
    validate_state(state)
    source = state if isinstance(state, dict) else {}
    result = {"schema_version": VERSION, "records": {}, "host_backoff": {}}
    statuses = {"verified", "date_conflict", "metadata_incomplete", "not_nonacademic",
                "publisher_host_mismatch", "canonical_identity_mismatch", "title_identity_mismatch",
                "title_identity_unverified", "publisher_access_restricted", "document_too_large",
                "access_challenge_not_article", "unapproved_or_credentialed_source_url",
                "credentialed_source_url_disallowed", "unapproved_redirect",
                "cross_host_redirect_requires_review", "robots_disallow", "not_html",
                "ValueError", "TimeoutError", "URLError", "ConnectionError", "OSError"}
    def safe_status(value):
        return value if isinstance(value, str) and (value in statuses or re.fullmatch(r"http_[1-5][0-9]{2}", value)) else "unknown_failure"
    def safe_time(value):
        try:
            return stamp(value).isoformat() if value else ""
        except (TypeError, ValueError, OverflowError, AttributeError):
            return ""
    for key, row in (source.get("records") or {}).items():
        if not re.fullmatch(r"[0-9a-f]{64}", str(key)) or not isinstance(row, dict):
            continue
        item = {"source_url": access.diagnostic_url(row.get("source_url", "")),
                "status": safe_status(row.get("status")), "complete": row.get("complete") is True,
                "attempts": row.get("attempts", 0) if type(row.get("attempts", 0)) is int else 0,
                "source_text_saved": False}
        for field in ("last_attempt_at", "next_retry_at"):
            if value := safe_time(row.get(field)):
                item[field] = value
        if re.fullmatch(r"[0-9a-f]{64}", str(row.get("fingerprint", ""))):
            item["fingerprint"] = row["fingerprint"]
        for field in ("date_status", "source_type_status"):
            if isinstance(row.get(field), str) and row[field] in {"verified", "unresolved", "conflict", "publisher_feed_only", "previously_verified"}:
                item[field] = row[field]
        result["records"][key] = item
    for host, row in (source.get("host_backoff") or {}).items():
        if not re.fullmatch(r"[a-z0-9.-]{1,253}", str(host)) or not isinstance(row, dict):
            continue
        item = {"reason": safe_status(row.get("reason"))}
        if row.get("blocked") is True:
            item["blocked"] = True
        for field in ("until", "checked_at"):
            if value := safe_time(row.get(field)):
                item[field] = value
        result["host_backoff"][host] = item
    return result


def process(records, state=None, *, now=None, max_records=24, max_requests=60,
            deadline_seconds=90, fetcher=None, clock=time.monotonic):
    """Return (copied records, durable attempts/backoff, current-window report).

    Only previous-week or undated nonacademic records are attempted; historical
    attempts stay in state but never count as current-week successes. A custom
    fixture fetcher(url) -> (html, final_url) uses one budget unit per invocation.
    Production fetches count robots, page and redirect requests separately.
    """
    now = stamp(now)
    start, end = previous_week(now)
    output = deepcopy(records)
    state = clean_state(state)
    budget = Budget(max_requests, deadline_seconds, clock)
    actual_fetcher = fetcher or MetadataFetcher(budget)
    counters = Counter()
    attempted, stop = 0, "completed"
    candidates = []
    for index, row in enumerate(output):
        if row.get("kind") != "nonacademic":
            continue
        if row.get("historical_backfill") or str(row.get("discovery_scope", "")).startswith("historical:"):
            counters["historical_backfill"] += 1
            continue
        published = day(row.get("published"))
        if published and not date_in_window(published, start, end):
            counters["outside_previous_week"] += 1
            continue
        candidates.append(index)
    # Least recently attempted first: failed first rows cannot starve later rows.
    candidates.sort(key=lambda index: state["records"].get(record_key(output[index]), {}).get("last_attempt_at", ""))
    for index in candidates:
        row = output[index]
        key = record_key(row)
        old = state["records"].get(key, {})
        try:
            host = urlsplit(row.get("url", "")).hostname or ""
        except (TypeError, ValueError):
            host = ""
        backoff = state["host_backoff"].get(host, {})
        if backoff.get("blocked") or (backoff.get("until") and stamp(backoff["until"]) > now):
            counters["host_paused"] += 1
            continue
        unchanged = old.get("fingerprint") == fingerprint(row)
        if old.get("complete") and unchanged:
            counters["already_checked"] += 1
            continue
        if old.get("next_retry_at") and stamp(old["next_retry_at"]) > now:
            counters["backoff"] += 1
            continue
        if attempted >= max_records:
            stop = "record_budget"
            break
        if clock() >= budget.deadline:
            stop = "deadline"
            break
        if budget.requests >= budget.max_requests:
            stop = "request_budget"
            break
        attempt = {"source_url": access.diagnostic_url(row.get("url", "")), "attempts": old.get("attempts", 0) + 1,
                   "last_attempt_at": now.isoformat(), "complete": True, "source_text_saved": False}
        try:
            if fetcher:
                budget.take()
            page, final_url = actual_fetcher(row.get("url", ""))
            updated = verify_record(row, page, url=final_url, checked_at=now)
            output[index] = updated
            attempt.update(status=updated["editorial_metadata"]["status"],
                           date_status=updated["editorial_metadata"]["date_status"],
                           source_type_status=updated["editorial_metadata"]["source_type_status"])
        except BudgetExceeded as exc:
            stop = str(exc)
            # An incomplete budget attempt is resumable, not a permanent failure.
            counters["budget_deferred"] += 1
            break
        except Exception as exc:
            info = failure(exc, now)
            attempt.update(status=info["status"], complete=not info["retryable"])
            if info["retryable"]:
                until = (now + timedelta(seconds=info["retry_after_seconds"])).isoformat()
                attempt["next_retry_at"] = until
                state["host_backoff"][host] = {"until": until, "reason": info["status"]}
            elif info.get("blocked") or info["status"] in {"http_401", "http_403", "access_challenge_not_article"}:
                state["host_backoff"][host] = {"blocked": True, "reason": info["status"], "checked_at": now.isoformat()}
        attempt["fingerprint"] = fingerprint(output[index])
        state["records"][key] = attempt
        counters[attempt["status"]] += 1
        attempted += 1
    current = [row for row in output if row.get("kind") == "nonacademic" and weekly_eligible(row, start, end)]
    report = {"schema_version": VERSION, "checked_at": now.isoformat(), "publication_window": window_metadata(now),
              "selected_records": len(candidates), "attempted_records": attempted, "requests": budget.requests,
              "stop_reason": stop, "outcomes": dict(counters), "weekly_eligible_records": len(current),
              "verified_original_dates": sum((row.get("editorial_metadata") or {}).get("date_status") == "verified" for row in current),
              "verified_source_types": sum((row.get("editorial_metadata") or {}).get("source_type_status") == "verified" for row in current),
              "source_text_saved": False, "model_used": False}
    return output, state, report


ROOT = Path(__file__).resolve().parents[1]


def atomic_json(path, payload):
    """Replace one validated UTF-8 JSON file atomically on its own filesystem."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".editorial-metadata-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_json(path):
    def invalid_constant(_):
        raise ValueError("nonfinite_json_value")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid_constant)


def run_files(library_path, state_path, status_path, *, now=None, max_records=24,
              max_requests=60, deadline_seconds=90):
    """Load and commit one bounded batch; no discovery and no missing-state prompt."""
    paths = [Path(path) for path in (library_path, state_path, status_path)]
    if len({path.resolve() for path in paths}) != 3:
        raise ValueError("metadata_output_paths_must_be_distinct")
    library_path, state_path, status_path = paths
    library = load_json(library_path)
    if not isinstance(library, list) or any(not isinstance(row, dict) for row in library):
        raise ValueError("library_must_be_record_list")
    # Refuse malformed files before network work or any replacement. A missing
    # state file starts fresh; a corrupt one must never silently lose access stops.
    state = clean_state(load_json(state_path)) if state_path.exists() else clean_state(None)
    updated, state, report = process(library, state, now=now, max_records=max_records,
                                     max_requests=max_requests, deadline_seconds=deadline_seconds)
    state = clean_state(state)
    # Serialize all outputs first, so a non-JSON result cannot partially commit.
    payloads = [json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                for value in (state, updated, report)]
    # Each file is atomic, not the three-file batch. A saved state fingerprint
    # includes the result metadata, so a failed library save is detected on resume.
    for path, payload in zip((state_path, library_path, status_path), payloads):
        atomic_json(path, payload)
    return report


def nonnegative_int(value):
    try:
        result = int(value)
        if result < 0:
            raise ValueError
        return result
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from None


def nonnegative_seconds(value):
    try:
        result = float(value)
        if not math.isfinite(result) or result < 0:
            raise ValueError
        return result
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("must be finite nonnegative seconds") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify bounded publisher original-date and source-type metadata.")
    parser.add_argument("--library", type=Path, default=ROOT / "data/library.json")
    parser.add_argument("--state", type=Path, default=ROOT / "data/editorial-metadata-state.json")
    parser.add_argument("--status", type=Path, default=ROOT / "data/editorial-metadata-status.json")
    parser.add_argument("--max-records", type=nonnegative_int, default=24)
    parser.add_argument("--max-requests", type=nonnegative_int, default=60)
    parser.add_argument("--time-budget", type=nonnegative_seconds, default=90)
    args = parser.parse_args(argv)
    try:
        report = run_files(args.library, args.state, args.status, max_records=args.max_records,
                           max_requests=args.max_requests, deadline_seconds=args.time_budget)
    except (ValueError, TypeError, OSError) as exc:
        # Exception details can contain source content. Emit the error class,
        # never a source page, query string, or malformed file contents.
        print(json.dumps({"status": "metadata_batch_failed", "error_type": type(exc).__name__,
                          "source_text_saved": False}))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

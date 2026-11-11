"""Closed, recursive schema for repository-public academic checkpoints.

Reject unsupported data without echoing its contents. Validation is not a
signature: digests bind query/row identities and detect accidental corruption,
while the repository remains the trusted source of saved metadata.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re

from collection_window import crossref_publication, publication_date
from abstract_metadata import COMPLETENESS, MAX_ABSTRACT_CHARS, openalex_abstract

SCHEMA = 1
SAFE_PARAMS = {"search", "filter", "query.bibliographic", "query.title", "query.container-title", "sort", "order"}
PROVIDERS = {"Crossref", "OpenAlex", "arXiv"}
PUBLICATION_FIELDS = {"published-online", "published-print", "published", "issued"}
PROVIDER_FIELDS = {"blocked", "last_http_status", "reason", "next_retry_at", "consecutive_failures", "last_request_at"}
QUERY_REQUIRED = {"provider", "params", "page_size", "cursor", "seen_cursors", "rows", "pages", "records_seen", "provider_total", "status", "started_at"}
QUERY_FIELDS = QUERY_REQUIRED | {"reason", "observed_at", "attempts", "last_attempt_at"}
PROVENANCE_FIELDS = {"source", "evidence", "policy", "status", "field", "value", "reason",
                     "openalex_publication_date", "crossref_publication_date", "requires_explicit_date_resolution",
                     "basis", "requested_id", "source_url", "version_url", "raw", "source_id", "verification_error"}
MAX_DATE_RETRIES = 5000
DATE_RETRY_FIELDS = {"provider", "attempts", "last_attempt_at", "next_retry_at", "outcome"}
HASH = re.compile(r"[0-9a-f]{64}")
DOI = re.compile(r"(?:https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/\S+", re.I)


def invalid():
    raise ValueError("Invalid academic discovery checkpoint or metadata; preserve the checkpoint for inspection")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def obj(value, allowed=None, required=()):
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value): invalid()
    if allowed is not None and set(value) - set(allowed): invalid()
    if set(required) - set(value): invalid()


def text(value, *, nullable=False, maximum=4096, empty=True):
    if value is None and nullable: return
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value): invalid()


def integer(value, *, nullable=False, minimum=0):
    if value is None and nullable: return
    if type(value) is not int or value < minimum: invalid()


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0: invalid()


def boolean(value):
    if type(value) is not bool: invalid()


def day(value, *, empty=False):
    if empty and value == "": return
    text(value, maximum=10, empty=False)
    try:
        if dt.date.fromisoformat(value).isoformat() != value: invalid()
    except (ValueError, TypeError): invalid()


def sequence(value, *, maximum=None):
    if not isinstance(value, (list, tuple)) or (maximum is not None and len(value) > maximum): invalid()


def strings(value, *, maximum=None, length=4096):
    sequence(value, maximum=maximum)
    for item in value: text(item, maximum=length)


def params(value, *, allow_auth=False):
    obj(value, SAFE_PARAMS | ({"api_key", "mailto"} if allow_auth else set()))
    for item in value.values(): text(item, maximum=16384)


def fingerprint(provider, search_params, page_size, *, allow_auth=False):
    text(provider)
    if provider not in {"Crossref", "OpenAlex"}: invalid()
    params(search_params, allow_auth=allow_auth)
    integer(page_size, minimum=1)
    if page_size > (100 if provider == "OpenAlex" else 1000): invalid()
    return digest({"provider": provider, "params": {k: v for k, v in search_params.items() if k in SAFE_PARAMS},
                   "page_size": page_size, "version": SCHEMA})


def date_parts(value):
    sequence(value, maximum=8)
    for parts in value:
        sequence(parts, maximum=8)
        for part in parts:
            # Invalid calendar values remain available as uncertainty evidence.
            if type(part) is not int: invalid()


def publication_event(value):
    if value is None: return
    obj(value, {"date-parts"})
    if "date-parts" in value: date_parts(value["date-parts"])


def project_publication_event(value):
    """Keep date components, never arbitrary nested provider body/URL fields."""
    if value is None: return None
    if not isinstance(value, dict): return {}
    if "date-parts" not in value: return {}
    selected = {"date-parts": value["date-parts"]}
    publication_event(selected)
    return selected


def validate_row(provider, row):
    obj(row)
    if "abstract_completeness" in row:
        text(row["abstract_completeness"])
        if row["abstract_completeness"] not in COMPLETENESS: invalid()
    if provider == "Crossref":
        obj(row, {"DOI", "type", "title", "container-title", "abstract", "abstract_completeness", "author"} | PUBLICATION_FIELDS)
        for name in ("DOI", "type"): 
            if name in row: text(row[name], nullable=True, maximum=2048)
        if row.get("DOI") and not DOI.fullmatch(row["DOI"]): invalid()
        for name in ("title", "container-title"):
            if name not in row or row[name] is None: continue
            if isinstance(row[name], str): text(row[name], maximum=4096)
            else: strings(row[name], maximum=32)
        if "abstract" in row: text(row["abstract"], maximum=MAX_ABSTRACT_CHARS)
        if "author" in row:
            sequence(row["author"], maximum=8)
            for author in row["author"]:
                obj(author, {"given", "family"})
                for name in author.values(): text(name, nullable=True, maximum=1024)
        for name in PUBLICATION_FIELDS & row.keys(): publication_event(row[name])
    elif provider == "OpenAlex":
        obj(row, {"id", "doi", "title", "publication_date", "is_retracted", "primary_location", "authorships", "abstract_inverted_index", "abstract_completeness"})
        for name in ("id", "doi", "title", "publication_date"):
            if name in row: text(row[name], nullable=True, maximum=4096)
        if row.get("doi") and not DOI.fullmatch(row["doi"]): invalid()
        if "is_retracted" in row and row["is_retracted"] is not None: boolean(row["is_retracted"])
        if "primary_location" in row:
            location = row["primary_location"]
            obj(location, {"source"}, {"source"})
            obj(location["source"], {"display_name"}, {"display_name"})
            text(location["source"]["display_name"], nullable=True)
        if "authorships" in row:
            sequence(row["authorships"], maximum=8)
            for authorship in row["authorships"]:
                obj(authorship, {"author"}, {"author"})
                obj(authorship["author"], {"display_name"}, {"display_name"})
                text(authorship["author"]["display_name"], nullable=True, maximum=1024)
        if "abstract_inverted_index" in row:
            inverted = row["abstract_inverted_index"]
            obj(inverted)
            modern = "abstract_completeness" in row
            limit = MAX_ABSTRACT_CHARS if modern else 801
            count = 0
            for word, positions in inverted.items():
                text(word, maximum=MAX_ABSTRACT_CHARS if modern else 4096)
                sequence(positions, maximum=limit)
                count += len(positions)
                for position in positions: integer(position)
            if count > limit: invalid()
            ordered = sorted((p, word) for word, positions in inverted.items() for p in positions)
            if modern:
                if sum(len(word) + 1 for _, word in ordered) > MAX_ABSTRACT_CHARS + 1: invalid()
                if inverted and openalex_abstract(inverted)["abstract_completeness"] != "provider_text_preserved": invalid()
            # Legacy rows retain their exact validation contract and digest.
            elif sum(len(word) + 1 for _, word in ordered[:-1]) >= 801: invalid()
    else: invalid()
    if "abstract_completeness" in row:
        value = row.get("abstract" if provider == "Crossref" else "abstract_inverted_index")
        status = row["abstract_completeness"]
        if status in {"provider_text_preserved", "truncated"} and not value: invalid()
        if status in {"unavailable", "invalid_provider_index"} and value: invalid()


def provenance(value):
    obj(value, PROVENANCE_FIELDS, {"source", "status"})
    text(value["source"]); text(value["status"])
    if value["source"] not in {"Crossref publisher metadata", "Official arXiv Atom metadata"}: invalid()
    if value["status"] not in {"day_known", "unresolved", "conflict"}: invalid()
    common = {"source", "status", "field", "value", "reason", "verification_error"}
    allowed = common | ({"evidence", "policy", "openalex_publication_date", "crossref_publication_date", "requires_explicit_date_resolution"}
                        if value["source"] == "Crossref publisher metadata" else
                        {"basis", "requested_id", "source_url", "version_url", "raw", "source_id"})
    if set(value) - allowed or value.get("verification_error"): invalid()
    for name in PROVENANCE_FIELDS - {"evidence", "verification_error", "requires_explicit_date_resolution"}:
        if name in value: text(value[name], maximum=4096)
    for name in ("verification_error", "requires_explicit_date_resolution"):
        if name in value: boolean(value[name])
    if "field" in value and value["field"] not in PUBLICATION_FIELDS: invalid()
    if "basis" in value and value["basis"] != "arxiv_first_submitted": invalid()
    for name in ("value", "openalex_publication_date", "crossref_publication_date"):
        if name in value: day(value[name], empty=True)
    if "evidence" in value:
        sequence(value["evidence"], maximum=4)
        for evidence in value["evidence"]:
            obj(evidence, {"field", "precision", "date_parts"}, {"field", "precision"})
            text(evidence["field"]); text(evidence["precision"])
            if evidence["field"] not in PUBLICATION_FIELDS or evidence["precision"] not in {"day", "unresolved"}: invalid()
            if "date_parts" in evidence: date_parts([evidence["date_parts"]])


def date_evidence(values, *, arxiv=False, candidates=()):
    obj(values)
    for identity, pair in values.items():
        text(identity, maximum=8192, empty=False)
        if not arxiv and not DOI.fullmatch(identity): invalid()
        sequence(pair, maximum=2)
        if len(pair) != 2: invalid()
        day(pair[0], empty=True)
        proof = pair[1]
        provenance(proof)
        if pair[0] and (proof["status"] != "day_known" or proof.get("value") != pair[0]): invalid()
        if not pair[0] and proof["status"] == "day_known": invalid()
        if proof["source"] == "Crossref publisher metadata":
            if arxiv: invalid()
            if not {"policy", "evidence"} <= proof.keys(): invalid()
            events = {}
            for event in proof["evidence"]:
                if event["field"] in events: invalid()
                events[event["field"]] = {"date-parts": [event["date_parts"]]} if "date_parts" in event else {}
            selected, expected = crossref_publication(events)
            if proof["policy"] != expected["policy"] or proof["evidence"] != expected["evidence"]: invalid()
            if proof["status"] == "conflict":
                if not selected or not proof.get("requires_explicit_date_resolution"): invalid()
                if proof.get("crossref_publication_date") != selected or not proof.get("openalex_publication_date") or proof["openalex_publication_date"] >= selected: invalid()
                if proof.get("value") != selected or proof.get("field") != expected.get("field"): invalid()
            elif pair[0] != selected or proof["status"] != expected["status"] or proof.get("field") != expected.get("field"):
                invalid()
        else:
            if arxiv:
                match = re.fullmatch(r"(\d{4}\.\d{4,5}):(.+)", identity, re.S)
                if not match: invalid()
                identifier, title = match.groups()
                expected_doi = "10.48550/arxiv." + identifier
                if not any(re.sub(r"v\d+$", "", re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(row.get("doi") or "").lower())) == expected_doi and row.get("title") == title for row in candidates): invalid()
                if not pair[0]: invalid()
            else:
                match = re.fullmatch(r"10\.48550/arxiv\.(\d{4}\.\d{4,5})(?:v\d+)?", identity, re.I)
                if not match: invalid()
                identifier = match[1]
            versioned = identifier + "v1"
            if proof.get("basis") != "arxiv_first_submitted" or proof.get("field") != "published" or proof.get("requested_id") != versioned: invalid()
            if proof.get("source_url") != "https://export.arxiv.org/api/query?id_list=" + versioned or proof.get("version_url") != "https://arxiv.org/abs/" + versioned: invalid()
            if pair[0]:
                raw_day = publication_date(proof.get("raw"))
                if raw_day is None or raw_day.isoformat() != pair[0] or proof.get("source_id") not in {"https://arxiv.org/abs/" + versioned, "http://arxiv.org/abs/" + versioned}: invalid()


def validate_state(data):
    obj(data, {"schema_version", "providers", "windows", "date_retries", "date_retry_cursors"}, {"schema_version", "providers", "windows"})
    cursors = data.get("date_retry_cursors", {})
    obj(cursors, {"Crossref", "arXiv"})
    for cursor in cursors.values():
        text(cursor, maximum=64, empty=False)
        if not HASH.fullmatch(cursor): invalid()
    retries = data.get("date_retries", {})
    obj(retries)
    if len(retries) > MAX_DATE_RETRIES: invalid()
    for identity, retry in retries.items():
        if not HASH.fullmatch(identity): invalid()
        obj(retry, DATE_RETRY_FIELDS, DATE_RETRY_FIELDS)
        text(retry["provider"])
        if retry["provider"] not in {"Crossref", "arXiv"}: invalid()
        integer(retry["attempts"], minimum=1)
        if retry["attempts"] > 32: invalid()
        number(retry["last_attempt_at"]); number(retry["next_retry_at"])
        delay = min(7 * 86400, 3600 * 2 ** min(retry["attempts"] - 1, 8))
        if retry["next_retry_at"] != retry["last_attempt_at"] + delay: invalid()
        text(retry["outcome"])
        if retry["outcome"] not in {"unavailable", "unresolved"}: invalid()
    if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA: invalid()
    obj(data["providers"], PROVIDERS)
    for provider in data["providers"].values():
        obj(provider, PROVIDER_FIELDS)
        for name in ("next_retry_at", "last_request_at"):
            if name in provider: number(provider[name])
        if "consecutive_failures" in provider: integer(provider["consecutive_failures"])
        if "blocked" in provider: boolean(provider["blocked"])
        if "last_http_status" in provider:
            integer(provider["last_http_status"], nullable=True, minimum=100)
            if provider["last_http_status"] is not None and provider["last_http_status"] > 599: invalid()
        if provider.get("blocked") and provider.get("last_http_status") not in {401, 403}: invalid()
        if "reason" in provider: text(provider["reason"], maximum=240)
    obj(data["windows"])
    for window_id, window in data["windows"].items():
        obj(window, {"mode", "window", "queries", "plans", "date_evidence", "arxiv_date_evidence"}, {"mode", "window", "queries", "plans", "date_evidence"})
        text(window["mode"])
        if window["mode"] not in {"weekly", "backfill", "preparation", "closeout", "closeout_late_index"}: invalid()
        bounds = window["window"]
        obj(bounds, {"from", "to"}, {"from", "to"})
        if bounds != {"from": "unspecified", "to": "unspecified"}:
            day(bounds["from"]); day(bounds["to"])
            if bounds["from"] > bounds["to"]: invalid()
        if window_id != f"{window['mode']}:{bounds['from']}:{bounds['to']}": invalid()
        obj(window["plans"], {"general", "journals"})
        for plan in window["plans"].values():
            obj(plan, {"active", "superseded", "drift_detected"}, {"active"})
            for name in ("active", "superseded"):
                if name not in plan: continue
                strings(plan[name], length=64)
                if any(not HASH.fullmatch(item) for item in plan[name]) or len(set(plan[name])) != len(plan[name]): invalid()
            if "drift_detected" in plan: boolean(plan["drift_detected"])
        obj(window["queries"])
        for query_id, query in window["queries"].items():
            obj(query, QUERY_FIELDS, QUERY_REQUIRED)
            if query_id != fingerprint(query["provider"], query["params"], query["page_size"]): invalid()
            text(query["cursor"], maximum=65536, empty=False)
            strings(query["seen_cursors"], length=65536)
            if len(set(query["seen_cursors"])) != len(query["seen_cursors"]): invalid()
            integer(query["pages"]); integer(query["records_seen"])
            integer(query["provider_total"], nullable=True)
            number(query["started_at"])
            if "observed_at" in query: number(query["observed_at"])
            if "last_attempt_at" in query: number(query["last_attempt_at"])
            if "attempts" in query: integer(query["attempts"])
            text(query["status"])
            if query["status"] not in {"pending", "complete", "truncated", "error"}: invalid()
            if query["status"] == "complete" and query["pages"] == 0: invalid()
            if "reason" in query: text(query["reason"], maximum=240)
            obj(query["rows"])
            for row_id, row in query["rows"].items():
                validate_row(query["provider"], row)
                if row_id != digest(row): invalid()
            if query["records_seen"] < len(query["rows"]): invalid()
        date_evidence(window["date_evidence"])
        if "arxiv_date_evidence" in window:
            candidates = [row for query in window["queries"].values() if query["provider"] == "OpenAlex" for row in query["rows"].values()]
            date_evidence(window["arxiv_date_evidence"], arxiv=True, candidates=candidates)


def strict_json_loads(value):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: invalid()
            result[key] = value
        return result
    return json.loads(value, object_pairs_hook=pairs, parse_constant=lambda _: invalid())

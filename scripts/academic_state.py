"""Durable, bounded academic metadata searches. No credentials or full text saved.

Checkpoints commit a validated page and its successor cursor together. Replays
return all retained metadata for the *same* query and publication window so a
crash before library publication cannot lose already-fetched pages. Callers must
still apply the original-publication-date and article-quality gates.

Provider contracts checked 2026-11-07:
https://community.crossref.org/t/changes-to-cursors-filtering-and-sorting-in-the-rest-api/16246
https://help.openalex.org/api/paging/
Crossref's August 2026 cursors persist and change per page. Both indexes are
mutable: cached-page replay prevents local loss, not remote indexing changes.
"""
from __future__ import annotations

import copy
import datetime as dt
from email.utils import parsedate_to_datetime
import json
import math
import os
from pathlib import Path
import tempfile
import time
import urllib.error
from urllib.parse import urlencode


from academic_state_schema import (SCHEMA, SAFE_PARAMS, PROVIDERS, digest, fingerprint,
                                   validate_state, validate_row, project_publication_event, strict_json_loads)
RETRYABLE = {429, 500, 502, 503, 504}



def retry_after(value, now):
    """Parse delta seconds or an HTTP-date; never shorten a server cooldown."""
    if value is None:
        return None
    try:
        seconds = float(str(value).strip())
        return max(0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        try:
            stamp = parsedate_to_datetime(str(value))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=dt.timezone.utc)
            return max(0, stamp.timestamp() - now)
        except (ValueError, TypeError, OverflowError):
            return None


class ProviderDeferred(RuntimeError):
    def __init__(self, provider, reason, *, code=None, retry_at=None, blocked=False):
        super().__init__(reason)
        self.provider, self.code, self.retry_at, self.blocked = provider, code, retry_at, blocked


class DiscoveryState:
    """One active collection window, with prior windows retained but never replayed.

    Use one writer (workflow concurrency) per state file. Invalid checkpoints
    fail closed instead of silently losing progress or dropping cooldowns.
    """
    def __init__(self, path=None, *, mode="weekly", window=None, now=None, sleep=None,
                 max_inline_wait=0, max_attempts=3, backoff_base=5, resume_only=False, minimum_interval=0.25):
        self.path = Path(path) if path else None
        self.now, self.sleep = now or time.time, sleep or time.sleep
        self.max_inline_wait = max(0, max_inline_wait)
        self.max_attempts, self.backoff_base = max(1, max_attempts), max(1, backoff_base)
        self.minimum_interval = max(0, minimum_interval)
        self.requests = {}
        self.resume_only = resume_only
        self.data = {"schema_version": SCHEMA, "providers": {}, "windows": {}}
        if self.path and self.path.exists():
            self.data = strict_json_loads(self.path.read_text())
            validate_state(self.data)
        self.window = dict(window or {"from": "unspecified", "to": "unspecified"})
        self.window_id = f"{mode}:{self.window['from']}:{self.window['to']}"
        self.had_window = self.window_id in self.data["windows"]
        self.current = self.data["windows"].setdefault(self.window_id, {
            "mode": mode, "window": self.window, "queries": {}, "plans": {}, "date_evidence": {}})
        self.validate_window(mode, window)
        validate_state(self.data)

    def validate_window(self, mode, window):
        if window is not None and (self.current["mode"] != mode or self.current["window"] != dict(window)):
            raise ValueError("Discovery checkpoint belongs to a different publication window")

    def save(self):
        validate_state(self.data)
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w") as stream:
                json.dump(self.data, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def query_id(self, provider, params, page_size):
        # Runtime authentication may be sent to the provider but is never saved.
        return fingerprint(provider, params, page_size, allow_auth=True)

    def register_plan(self, group, queries):
        active = sorted(set(self.query_id(provider, params, size) for provider, params, size in queries))
        prior = self.current["plans"].get(group, {}).get("active", [])
        if self.resume_only:
            if active != prior:
                self.current["plans"].setdefault(group, {"active": prior})["drift_detected"] = True
                self.save()
            return
        removed = sorted(set(prior) - set(active))
        self.current["plans"][group] = {"active": active, "superseded": sorted(set(removed) | set(self.current["plans"].get(group, {}).get("superseded", [])))}
        self.save()

    def summary(self):
        validate_state(self.data)
        active = {q for group in self.current["plans"].values() for q in group["active"]}
        if not self.current["plans"]:
            active = set(self.current["queries"])
        complete = sum(self.current["queries"].get(q, {}).get("status") == "complete" for q in active)
        stale = []
        for name, value in self.data["windows"].items():
            if name == self.window_id:
                continue
            ids = {q for group in value.get("plans", {}).values() for q in group["active"]} or set(value["queries"])
            pending = sum(value["queries"].get(q, {}).get("status") != "complete" for q in ids)
            if pending:
                stale.append({"window_id": name, "window": value["window"], "pending_queries": pending,
                              "action": "retained for explicit historical recovery; excluded from current week"})
        return {"window_id": self.window_id, "active_queries": len(active), "completed_queries": complete,
                "pending_queries": len(active) - complete,
                "status": "complete_for_configured_queries" if complete == len(active) else "partial",
                "stale_windows": stale,
                "query_plan_drift": any(p.get("drift_detected") for p in self.current["plans"].values()),
                "superseded_queries": sum(len(set(p.get("superseded", [])) - active) for p in self.current["plans"].values()),
                "provider_state": copy.deepcopy(self.data["providers"])}

    def fetch(self, provider, url, request):
        """Bound retries by elapsed wait budget, while persisting longer cooldowns."""
        validate_state(self.data)
        if provider not in PROVIDERS:raise ValueError("Unsupported academic provider")
        spent = 0
        p = self.data["providers"].setdefault(provider, {})
        for attempt in range(self.max_attempts):
            if p.get("blocked"):
                raise ProviderDeferred(provider, "Provider access blocked; manual access review required", code=p.get("last_http_status"), blocked=True)
            delay = max(0, p.get("next_retry_at", 0) - self.now())
            if delay:
                if spent + delay > self.max_inline_wait:
                    raise ProviderDeferred(provider, "Provider cooldown active", code=p.get("last_http_status"), retry_at=p["next_retry_at"])
                self.sleep(delay)
                spent += delay
                if self.now() < p["next_retry_at"]:
                    raise ProviderDeferred(provider, "Provider cooldown active", code=p.get("last_http_status"), retry_at=p["next_retry_at"])
            pacing = max(0, p.get("last_request_at", 0) + self.minimum_interval - self.now())
            if pacing:
                self.sleep(pacing)
            p["last_request_at"] = self.now()
            self.requests[provider] = self.requests.get(provider, 0) + 1
            try:
                result = request(url)
            except Exception as exc:
                code = getattr(exc, "code", None)
                if code in (401, 403):
                    p.update(blocked=True, last_http_status=code, reason="HTTP access denied; no automatic retry or alternate route")
                    self.save()
                    raise
                transient = code in RETRYABLE or isinstance(exc, (TimeoutError, ConnectionError, urllib.error.URLError)) and code is None
                if not transient:
                    raise
                failures = p.get("consecutive_failures", 0) + 1
                headers = getattr(exc, "headers", None)
                retry = retry_after(headers.get("Retry-After") if headers else None, self.now())
                delay = max(retry or 0, min(3600, self.backoff_base * 2 ** min(failures - 1, 10)))
                p.update(consecutive_failures=failures, last_http_status=code, next_retry_at=self.now() + delay,
                         reason="HTTP " + str(code) if code else type(exc).__name__)
                self.save()
                if attempt + 1 == self.max_attempts or spent + delay > self.max_inline_wait:
                    raise
            else:
                p.update(consecutive_failures=0, next_retry_at=0)
                p.pop("last_http_status", None)
                p.pop("reason", None)
                self.save()
                return result
        raise AssertionError("Unreachable retry state")


def _identity(provider, work):
    raw = (work.get("DOI") if provider == "Crossref" else work.get("doi")) or work.get("id")
    return str(raw).lower().removeprefix("https://doi.org/") if raw else digest(work)


def _project(provider, work):
    """Retain only metadata consumed by the collector, not entire API payloads."""
    if provider == "Crossref":
        fields = {"DOI", "type", "title", "container-title", "published-online", "published-print", "published", "issued"}
        out = {k: v for k, v in work.items() if k in fields}
        for field in ("published-online", "published-print", "published", "issued"):
            if field in out:out[field]=project_publication_event(out[field])
        if work.get("abstract"):
            if not isinstance(work["abstract"],str):raise ValueError("Malformed Crossref abstract")
            out["abstract"] = work["abstract"][:6000]
        if work.get("author"):
            if not isinstance(work["author"], list) or any(not isinstance(a, dict) for a in work["author"]):
                raise ValueError("Malformed Crossref authors")
            out["author"] = [{k: a[k] for k in ("given", "family") if k in a} for a in work["author"][:8]]
        validate_row(provider,out)
        return out
    fields = {"id", "doi", "title", "publication_date", "is_retracted"}
    out = {k: v for k, v in work.items() if k in fields}
    if work.get("title") is not None and not isinstance(work["title"], str):
        raise ValueError("Malformed OpenAlex title")
    location = work.get("primary_location") or {}
    if not isinstance(location, dict) or not isinstance(location.get("source") or {}, dict):
        raise ValueError("Malformed OpenAlex publication source")
    out["primary_location"] = {"source": {"display_name": (location.get("source") or {}).get("display_name")}}
    authors = work.get("authorships") or []
    if not isinstance(authors, list) or any(not isinstance(a, dict) or not isinstance(a.get("author") or {}, dict) for a in authors):
        raise ValueError("Malformed OpenAlex authors")
    out["authorships"] = [{"author": {"display_name": (a.get("author") or {}).get("display_name", "")}} for a in authors[:8]]
    inverted = work.get("abstract_inverted_index")
    if inverted:
        if not isinstance(inverted, dict) or any(not isinstance(word, str) or not isinstance(positions, list) or any(type(p) is not int or p < 0 for p in positions) for word, positions in inverted.items()):
            raise ValueError("Malformed OpenAlex abstract index")
        # update.abstract reads its first 800 characters. Preserve complete
        # words spanning that prefix, keeping exactly the same input meaning.
        retained, length = {}, 0
        for position, word in sorted((p, word) for word, positions in inverted.items() for p in positions):
            retained.setdefault(word, []).append(position)
            length += len(word) + 1
            if length >= 801:
                break
        out["abstract_inverted_index"] = retained
    validate_row(provider,out)
    return out


def cursor_search(request, provider, params, *, state=None, max_pages=5, page_size=100):
    """Return replayed + newly fetched records; the cap applies to this invocation.

    Provider variants of the same DOI are retained for conservative date
    reconciliation, but identical records/pages are never appended twice.
    """
    if provider not in {"Crossref", "OpenAlex"}:
        raise ValueError("Unsupported academic provider")
    ceiling = 100 if provider == "OpenAlex" else 1000
    if not 1 <= page_size <= ceiling:
        raise ValueError(f"{provider} page_size must be between 1 and {ceiling}")
    state = state or DiscoveryState()
    validate_state(state.data)
    query_id = state.query_id(provider, params, page_size)
    if state.resume_only and query_id not in {q for p in state.current["plans"].values() for q in p["active"]}:
        return [], {"provider": provider, "query_id": query_id, "query": params.get("search") or params.get("query.bibliographic") or params.get("query.title", ""),
                    "filter": params.get("filter", ""), "status": "deferred", "truncated": True,
                    "reason": "Query is not in the saved plan; initial discovery run required", "requests_this_run": 0,
                    "pages_this_run": 0, "window_id": state.window_id}, []
    q = state.current["queries"].setdefault(query_id, {
        "provider": provider, "params": {k: v for k, v in params.items() if k in SAFE_PARAMS},
        "page_size": page_size, "cursor": "*", "seen_cursors": [], "rows": {}, "pages": 0,
        "records_seen": 0, "provider_total": None, "status": "pending", "started_at": state.now()})
    errors, run_pages = [], 0
    before_requests = state.requests.get(provider, 0)
    cached_pages = q["pages"]
    try:
        while q["status"] != "complete" and run_pages < max_pages:
            cursor = q["cursor"]
            url = ("https://api.crossref.org/works?" + urlencode(dict(params, rows=page_size, cursor=cursor))
                   if provider == "Crossref" else "https://api.openalex.org/works?" + urlencode(dict(params, per_page=page_size, cursor=cursor)))
            result = state.fetch(provider, url, request)
            message = result.get("message") if provider == "Crossref" else result
            if not isinstance(message, dict):
                raise ValueError("Malformed provider search response")
            works = message.get("items" if provider == "Crossref" else "results")
            meta = message if provider == "Crossref" else message.get("meta") or {}
            if not isinstance(works, list) or any(not isinstance(w, dict) for w in works) or not isinstance(meta, dict):
                raise ValueError("Malformed provider search page")
            total = meta.get("total-results" if provider == "Crossref" else "count")
            if total is not None and (type(total) is not int or total < 0):
                raise ValueError("Invalid provider result count")
            if total == 0 and works:
                raise ValueError("Nonempty page contradicts zero provider total")
            total = max(total, q["provider_total"]) if total is not None and q["provider_total"] is not None else total if total is not None else q["provider_total"]
            next_cursor = meta.get("next-cursor" if provider == "Crossref" else "next_cursor")
            if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor):
                raise ValueError("Invalid provider successor cursor")
            # Commit page + cursor only after the entire response is validated.
            rows = dict(q["rows"])
            for work in works:
                projected = _project(provider, work)
                rows[digest(projected)] = projected
            unique = len({_identity(provider, w) for w in rows.values()})
            q.update(rows=rows, pages=q["pages"] + 1, records_seen=q["records_seen"] + len(works),
                     provider_total=total, status="truncated", reason="page budget reached", observed_at=state.now())
            run_pages += 1
            # A reported total is a consistency check, never an excuse to count
            # duplicate rows as independent papers. Unknown-total short pages
            # are terminal only when there is no advertised successor.
            if (total is not None and unique >= total and (bool(works) or total == 0)) or (total is None and (not works or len(works) < page_size and not next_cursor)):
                q.update(status="complete", reason="Provider query exhausted")
            elif not works:
                q.update(reason="empty page before reported total", status="truncated")
            elif not next_cursor or next_cursor == "*":
                q.update(reason="provider did not supply a new cursor", status="truncated")
            elif next_cursor == cursor or next_cursor in q["seen_cursors"]:
                q.update(reason="cursor did not advance to new records", status="truncated")
            else:
                q["seen_cursors"] = list(dict.fromkeys(q["seen_cursors"] + [cursor]))
                q["cursor"] = next_cursor
            state.save()
            if q["status"] == "complete" or q["reason"] != "page budget reached":
                break
    except Exception as exc:
        # I/O checkpoint failures must stop the run: reporting success here
        # would permit library publication without a durable replay checkpoint.
        if isinstance(exc, OSError) and not isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError)):
            raise
        reason = "HTTP " + str(exc.code) if getattr(exc, "code", None) else str(exc) if isinstance(exc, ProviderDeferred) else type(exc).__name__
        q.update(status="error", reason=reason)
        state.save()
        errors.append(provider + " search unavailable: " + reason)
    if max_pages < 1 and q["status"] != "complete":
        q.update(status="truncated", reason="page budget is zero")
        state.save()
    p = state.data["providers"].get(provider, {})
    audit = {"provider": provider, "query_id": query_id, "query": params.get("search") or params.get("query.bibliographic") or params.get("query.title", ""),
             "filter": params.get("filter", ""), "pages": q["pages"], "pages_this_run": run_pages,
             "cached_pages": cached_pages, "requests_this_run": state.requests.get(provider, 0) - before_requests,
             "records_seen": q["records_seen"], "records_unique": len({_identity(provider, w) for w in q["rows"].values()}),
             "provider_total": q["provider_total"], "max_pages": max_pages, "page_size": page_size,
             "status": q["status"], "truncated": q["status"] != "complete", "reason": q.get("reason", ""),
             "completion_scope": "configured provider query and original publication window only",
             "query_status": "complete_for_configured_query" if q["status"] == "complete" else "partial",
             "index_note": "Provider indexes can change during traversal; this is not a frozen snapshot or exhaustive literature coverage",
             "observed_at": q.get("observed_at"),
             "window_id": state.window_id, "resumable": q["status"] != "complete"}
    if p.get("blocked") or p.get("next_retry_at", 0) > state.now():
        audit["provider_paused"] = True
        audit["retry_at"] = p.get("next_retry_at")
        audit["access_blocked"] = bool(p.get("blocked"))
        if p.get("last_http_status") == 429:
            audit["quota_exhausted"] = True
    return copy.deepcopy(list(q["rows"].values())), audit, errors

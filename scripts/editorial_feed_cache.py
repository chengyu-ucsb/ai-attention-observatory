"""Preserve rolling-feed metadata before it disappears, without article retrieval.

Captured titles, URLs, exact publisher dates and genre tags are a staging index.
Only the next week's strict publication-window collector can promote candidates.
No descriptions, article bodies, PDFs or summaries are persisted here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
import email.utils

from collection_window import date_in_window, publication_date, previous_week, window_metadata

ROOT = Path(__file__).resolve().parents[1]
VERSION = 1
SCREENING_VERSION = 1
RETENTION_DAYS = 28
MAX_ITEMS = 10000
MAX_CHECKS = 160
STATES = {"ok", "partial", "rate_limited", "unavailable", "blocked", "deferred_budget"}


def utc(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def fingerprint(feed):
    fields = {name: feed.get(name) for name in ("id", "url", "name", "article_hosts", "source_type")}
    return sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def empty_state():
    return {"schema_version": VERSION, "screening_version": SCREENING_VERSION, "sources": {}}


def validate_state(state, feeds):
    """Fail closed on unknown fields and non-publisher URLs before reuse."""
    import discover_editorial as ed
    if (type(state) is not dict or set(state) != {"schema_version", "screening_version", "sources"}
            or state["schema_version"] != VERSION or state["screening_version"] != SCREENING_VERSION
            or type(state["sources"]) is not dict):
        raise ValueError("invalid_editorial_feed_cache")
    configured = {feed["id"]: feed for feed in feeds}
    source_fields = {"fingerprint", "status", "attempts", "last_attempt_at", "last_success_at",
                     "next_retry_at", "continuation_url", "checks", "items", "http_status", "retry_after"}
    item_fields = {"title", "url", "date", "date_raw", "date_basis", "authors", "categories",
                   "first_observed_at", "last_observed_at", "topical", "screening_version", "conflicting_dates"}
    for source_id, source in state["sources"].items():
        if type(source_id) is not str or not 1 <= len(source_id) <= 200:
            raise ValueError("invalid_editorial_feed_source")
        feed = configured.get(source_id)
        if type(source) is not dict or set(source) - source_fields or not {"fingerprint", "status", "checks", "items"} <= set(source):
            raise ValueError("invalid_editorial_feed_source")
        if (type(source["fingerprint"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", source["fingerprint"])
                or type(source.get("attempts", 0)) is not int or source.get("attempts", 0) < 0):
            raise ValueError("invalid_editorial_feed_source")
        applicable = feed is not None and source["fingerprint"] == fingerprint(feed)
        # Stale configurations are never served, but they still must pass the
        # complete closed metadata schema before any save or artifact validation.
        if (type(source["status"]) is not str or source["status"] not in STATES or type(source["items"]) is not list
                or len(source["items"]) > MAX_ITEMS or type(source["checks"]) is not list
                or len(source["checks"]) > MAX_CHECKS):
            raise ValueError("invalid_editorial_feed_source")
        if (type(source.get("retry_after", "")) is not str or len(source.get("retry_after", "")) > 100
                or type(source.get("http_status", 200)) is not int or not 100 <= source.get("http_status", 200) <= 599):
            raise ValueError("invalid_editorial_feed_source")
        for key in ("last_attempt_at", "last_success_at", "next_retry_at"):
            if source.get(key) is not None and (type(source[key]) is not str or utc(source[key]).isoformat() != source[key]):
                raise ValueError("invalid_editorial_feed_timestamp")
        continuation = source.get("continuation_url", "")
        if type(continuation) is not str or len(continuation) > 8192:
            raise ValueError("invalid_editorial_feed_continuation")
        if continuation:
            a = urlsplit(continuation)
            if (a.scheme != "https" or not a.hostname or a.username or a.password or a.port not in (None, 443)
                    or ed.credentialed_url(continuation)
                    or (applicable and a.hostname != urlsplit(feed["url"]).hostname)):
                raise ValueError("invalid_editorial_feed_continuation")
        for check in source["checks"]:
            if (type(check) is not dict or set(check) != {"at", "status", "oldest", "newest", "pages"}
                    or type(check["status"]) is not str or check["status"] not in STATES or type(check["pages"]) is not int
                    or not 0 <= check["pages"] <= 100 or type(check["at"]) is not str or utc(check["at"]).isoformat() != check["at"]):
                raise ValueError("invalid_editorial_feed_check")
            if any(type(check[x]) is not str or (check[x] and publication_date(check[x]) is None) for x in ("oldest", "newest")):
                raise ValueError("invalid_editorial_feed_check")
        for item in source["items"]:
            if type(item) is not dict or set(item) != item_fields:
                raise ValueError("invalid_editorial_feed_item")
            locator = item["url"]
            if type(locator) is not str or len(locator) > 8192:
                raise ValueError("invalid_editorial_feed_item")
            parsed = urlsplit(locator)
            safe_locator = (parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
                            and not parsed.password and parsed.port in (None, 443) and not ed.credentialed_url(locator))
            if (not safe_locator or (applicable and not ed.allowed_article(locator, feed))
                    or type(item["title"]) is not str or len(item["title"]) > 1000
                    or item["topical"] is not True or item["screening_version"] != SCREENING_VERSION
                    or type(item["date_basis"]) is not str or item["date_basis"] not in {"publisher_rss_pubDate", "publisher_atom_published"}
                    or type(item["date_raw"]) is not str or len(item["date_raw"]) > 100
                    or type(item["date"]) is not str or ed.normalize_date(item["date_raw"]) != item["date"]
                    or publication_date(item["date"]) is None):
                raise ValueError("invalid_editorial_feed_item")
            conflict = item["conflicting_dates"]
            if (type(conflict) is not list or len(conflict) not in (0, 2)
                    or any(type(day) is not str or publication_date(day) is None or publication_date(day).isoformat() != day for day in conflict)
                    or (conflict and conflict[0] >= conflict[1])):
                raise ValueError("invalid_editorial_feed_conflict")
            for key in ("first_observed_at", "last_observed_at"):
                if type(item[key]) is not str or utc(item[key]).isoformat() != item[key]:
                    raise ValueError("invalid_editorial_feed_timestamp")
            for key in ("authors", "categories"):
                if type(item[key]) is not list or len(item[key]) > 50 or any(type(x) is not str or len(x) > 300 for x in item[key]):
                    raise ValueError("invalid_editorial_feed_item")
    return state


def load_cache(path, feeds):
    path = Path(path)
    return validate_state(json.loads(path.read_text()), feeds) if path.exists() else empty_state()


def retry_time(error, now, attempt):
    """Respect Retry-After in seconds or HTTP-date; never retry before it."""
    minimum = min(86400, 900 * (2 ** min(attempt - 1, 7)))
    result = now + timedelta(seconds=minimum)
    value = error.headers.get("Retry-After", "") if isinstance(error, HTTPError) and error.headers else ""
    if value:
        try:
            seconds = int(value)
            result = max(result, now + timedelta(seconds=max(0, seconds)))
        except OverflowError:
            # An unrepresentably long delta means effectively no automatic retry,
            # not permission to shorten the server's requested cooldown.
            result = datetime.max.replace(tzinfo=timezone.utc)
        except ValueError:
            try:
                result = max(result, utc(email.utils.parsedate_to_datetime(value)))
            except (ValueError, TypeError, OverflowError):
                pass
    return result.isoformat(), value[:100]


def capture(state=None, *, feeds=None, now=None, fetcher=None, max_requests=24,
            deadline_seconds=240, monotonic=time.monotonic, checkpoint=None):
    import discover_editorial as ed
    feeds = ed.FEEDS if feeds is None else feeds
    fetcher = ed.get_xml if fetcher is None else fetcher
    now = utc(now)
    state = deepcopy(validate_state(state or empty_state(), feeds))
    state["sources"] = {key: value for key, value in state["sources"].items() if key in {f["id"] for f in feeds}}
    cutoff = now.date() - timedelta(days=RETENTION_DAYS)
    deadline = monotonic() + max(1, deadline_seconds)
    requests = 0
    outcomes = []
    known_urls = {ed.url_key(row["url"]) for feed in feeds
                  if state["sources"].get(feed["id"], {}).get("fingerprint") == fingerprint(feed)
                  for row in state["sources"][feed["id"]].get("items", [])
                  if utc(row["last_observed_at"]).date() >= cutoff}
    # Hold valid date metadata transiently, including entries whose current
    # preview is off-topic. A later feed/page can establish the same URL as
    # topical; reconcile all earlier contrary evidence before checkpointing it.
    observed = {}
    host_pauses = {}
    for feed in feeds:
        source = state["sources"].get(feed["id"], {})
        host = urlsplit(feed["url"]).hostname.removeprefix("www.")
        if source.get("fingerprint") == fingerprint(feed):
            if source.get("status") == "blocked":
                host_pauses[host] = None
            elif source.get("next_retry_at") and utc(source["next_retry_at"]) > now:
                if host not in host_pauses or host_pauses[host] is not None:
                    host_pauses[host] = max(host_pauses.get(host) or now, utc(source["next_retry_at"]))
    feeds = sorted(feeds, key=lambda feed: state["sources"].get(feed["id"], {}).get("last_attempt_at", ""))
    for feed in feeds:
        ident = fingerprint(feed)
        source = state["sources"].get(feed["id"], {})
        if source.get("fingerprint") != ident:
            source = {"fingerprint": ident, "status": "ok", "checks": [], "items": []}
        source["items"] = [x for x in source["items"] if utc(x["last_observed_at"]).date() >= cutoff]
        source["checks"] = [x for x in source["checks"] if utc(x["at"]).date() >= cutoff][-MAX_CHECKS:]
        state["sources"][feed["id"]] = source
        host = urlsplit(feed["url"]).hostname.removeprefix("www.")
        if host in host_pauses:
            outcomes.append({"source_id": feed["id"], "status": "deferred_provider_pause", "next_retry_at":
                             host_pauses[host].isoformat() if host_pauses[host] else None})
            continue
        if requests >= max_requests or monotonic() >= deadline:
            outcomes.append({"source_id": feed["id"], "status": "deferred_budget"})
            continue
        rows = {(ed.url_key(x["url"]), x["date"]): x for x in source["items"]}
        observed[feed["id"]] = rows
        # Revalidate the live advertised chain before reaching a saved cursor.
        # Jumping from the root directly to the old cursor can lose entries
        # shifted onto intermediate pages in a mutable rolling feed.
        resume = source.get("continuation_url", "")
        current, pages, dates, seen_pages = feed["url"], 0, [], set()
        source.update(last_attempt_at=now.isoformat(), status="ok", next_retry_at=None)
        while current:
            if requests >= max_requests or monotonic() >= deadline or pages >= ed.MAX_FEED_PAGES:
                source.update(status="partial", continuation_url=current)
                break
            if current in seen_pages:
                source.update(status="partial", continuation_url="")
                break
            seen_pages.add(current)
            requests += 1
            try:
                root = fetcher(current)
                items = ed.parse_feed(root)
                pages += 1
                for item in items:
                    if item.get("date"):
                        dates.append(item["date"])
                    day = publication_date(item.get("date"))
                    if not day or not ed.allowed_article(item.get("url", ""), feed):
                        continue
                    key = (ed.url_key(item["url"]), item["date"])
                    row = {k: item.get(k, "") for k in ("title", "url", "date", "date_raw", "date_basis")}
                    row["title"] = row["title"][:1000]
                    row["url"] = ed.diagnostic_locator(row["url"])
                    for key_name in ("authors", "categories"):
                        row[key_name] = [str(x)[:300] for x in item.get(key_name, [])][:50]
                    row.update(first_observed_at=rows.get(key, {}).get("first_observed_at", now.isoformat()),
                               last_observed_at=now.isoformat(), topical=True, screening_version=SCREENING_VERSION,
                               conflicting_dates=rows.get(key, {}).get("conflicting_dates", []))
                    rows[key] = row
                    if ed.eligible(item):
                        known_urls.add(ed.url_key(row["url"]))
                advertised = ed.next_page(root, current)
                current = advertised
                source.update(last_success_at=now.isoformat(), attempts=0, continuation_url=current)
            except Exception as error:
                attempt = source.get("attempts", 0) + 1
                source["attempts"] = attempt
                source["continuation_url"] = current
                if isinstance(error, HTTPError) and error.code in (401, 403):
                    source.update(status="blocked", http_status=error.code, next_retry_at=None, continuation_url="")
                    host_pauses[host] = None
                else:
                    delay, header = retry_time(error, now, attempt)
                    source.update(status="rate_limited" if isinstance(error, HTTPError) and error.code == 429 else "unavailable",
                                  next_retry_at=delay, retry_after=header)
                    if isinstance(error, HTTPError):
                        source["http_status"] = error.code
                    host_pauses[host] = utc(delay)
                break
        if resume and resume not in seen_pages and source["status"] == "ok":
            # The previously unfinished chain disappeared or changed. Do not
            # upgrade that history gap to a completeness claim.
            source["status"] = "partial"
        # Keep a compact conflict marker on every overlapping row before any
        # capacity trimming. A cap must not turn known contradictory dates into
        # an apparently verified single date, including on another feed or run.
        dates_by_url = {}
        all_rows = [row for src in state["sources"].values() for row in src["items"]]
        all_rows += [row for pending in observed.values() for row in pending.values()]
        for row in all_rows:
            evidence = dates_by_url.setdefault(ed.url_key(row["url"]), set())
            evidence.update([row["date"], *row["conflicting_dates"]])
        for row in all_rows:
            evidence = sorted(dates_by_url[ed.url_key(row["url"])])
            row["conflicting_dates"] = [evidence[0], evidence[-1]] if len(evidence) > 1 else []
        for observed_id, pending in observed.items():
            relevant = {key: row for key, row in pending.items() if key[0] in known_urls}
            prior = state["sources"][observed_id]
            if len(relevant) > MAX_ITEMS:
                # Exceeding the retention bound is explicitly partial coverage.
                prior["status"] = "partial"
                relevant = dict(sorted(relevant.items(), key=lambda kv: kv[1]["first_observed_at"])[:MAX_ITEMS])
            prior["items"] = list(relevant.values())
        check = {"at": now.isoformat(), "status": source["status"], "oldest": min(dates) if dates else "",
                 "newest": max(dates) if dates else "", "pages": pages}
        source["checks"] = (source["checks"] + [check])[-MAX_CHECKS:]
        outcomes.append({"source_id": feed["id"], "status": source["status"], "pages": pages,
                         "retained_candidates": len(source["items"]), "next_retry_at": source.get("next_retry_at")})
        validate_state(state, feeds)
        if checkpoint:
            checkpoint(state)
    for outcome in outcomes:
        if "retained_candidates" in outcome:
            outcome["retained_candidates"] = len(state["sources"][outcome["source_id"]]["items"])
    return state, {"checked_at": now.isoformat(), "requests": requests, "sources": outcomes,
        "scope": "Rolling publisher-feed metadata only. No current-week articles retrieved or published; coverage is not exhaustive."}


def candidate_items(state, feeds, *, now=None):
    """Serve only exact previous-week dates from unchanged source configurations."""
    import discover_editorial as ed
    validate_state(state, feeds)
    start, end = previous_week(now)
    output = {}
    # A canonical article can occur in multiple feeds with contradictory dates.
    # Select relevant identities globally before including all their evidence.
    relevant_urls = {ed.url_key(row["url"]) for feed in feeds
                     if state["sources"].get(feed["id"], {}).get("fingerprint") == fingerprint(feed)
                     for row in state["sources"][feed["id"]].get("items", [])
                     if date_in_window(row["date"], start, end)}
    for feed in feeds:
        source = state["sources"].get(feed["id"], {})
        if source.get("fingerprint") != fingerprint(feed):
            continue
        selected = []
        # Outside-week dates are conflict evidence only, never weekly admission.
        for row in source.get("items", []):
            if ed.url_key(row["url"]) not in relevant_urls:
                continue
            selected.append({k: deepcopy(row[k]) for k in ("title", "url", "date", "date_raw", "date_basis", "authors", "categories")})
            selected[-1].update(description="", _snapshot_screening_version=SCREENING_VERSION,
                                _snapshot_observed_at=row["first_observed_at"],
                                _snapshot_conflicting_dates=deepcopy(row["conflicting_dates"]))
        output[feed["id"]] = selected
    return output


def coverage_report(state, feeds, *, now=None):
    validate_state(state, feeds)
    start, end = previous_week(now)
    beginning = utc(start.isoformat())
    closing = utc((end + timedelta(days=1)).isoformat())
    report = {}
    for feed in feeds:
        source = state["sources"].get(feed["id"], {})
        if source.get("fingerprint") != fingerprint(feed):
            source = {}
        checks = [utc(x["at"]) for x in source.get("checks", [])
                  if x["status"] in ("ok", "partial") and x["pages"] > 0
                  and beginning <= utc(x["at"]) < closing]
        points = sorted(set([beginning, closing] + checks))
        report[feed["id"]] = {"snapshots_during_publication_week": len(checks),
            "largest_unobserved_interval_hours": round(max((b-a).total_seconds()/3600 for a,b in zip(points, points[1:])), 2),
            "coverage_claim": "Observed feed snapshots only; publication completeness is not verified."}
    return report


def save_cache(path, state, feeds):
    validate_state(state, feeds)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def main():
    import discover_editorial as ed
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=ROOT / "data/editorial-feed-cache.json")
    parser.add_argument("--max-requests", type=int, default=24)
    parser.add_argument("--time-budget", type=int, default=240)
    args = parser.parse_args()
    state = load_cache(args.state, ed.FEEDS)
    state, report = capture(state, max_requests=max(0, min(args.max_requests, 72)),
                            deadline_seconds=max(1, min(args.time_budget, 600)),
                            checkpoint=lambda value: save_cache(args.state, value, ed.FEEDS))
    save_cache(args.state, state, ed.FEEDS)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

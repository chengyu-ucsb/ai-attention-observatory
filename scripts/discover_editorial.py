"""Discover prior-week journalism, opinion, policy and analysis from free feeds.

Publisher-declared original publication dates determine admission, never modified,
indexed or first-seen dates. Google News is a separate, unverified lead queue.
Only metadata and short publisher previews persist; discovery is not full text.
"""
from collections import Counter
import datetime
import argparse
import email.utils
import html
import json
import pathlib
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

from collection_window import previous_week, date_in_window, weekly_eligible, window_metadata
from search_plan import discovery_window
from news_quality import useful_description, publisher_url
from editorial_corrections import apply as apply_editorial_corrections
from editorial_source_reviews import apply as apply_source_reviews

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIR = ROOT / "data"
TODAY = datetime.datetime.now(datetime.timezone.utc).date()
ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"
MAX_FEED_BYTES = 3_000_000
MAX_FEED_PAGES = 6
AGENT = "AIAttentionObservatory/8.0 (+https://github.com/chengyu-ucsb/ai-attention-observatory)"
FEEDS = json.loads((DIR / "editorial-sources.json").read_text())["sources"]
GOOGLE_SEARCHES = [
    ('"AI" ("attention" OR "distraction" OR "focus")', "AI & cognition"),
    ('"ChatGPT" ("thinking" OR "cognitive" OR "memory")', "AI & cognition"),
    ('"AI" ("digital wellbeing" OR "attention management")', "Interventions"),
    ('"AI" "learning" "critical thinking"', "AI & cognition"),
    ('"notification batching" OR "interruption recovery"', "Interventions"),
    ('"AI" "productivity" "focus"', "Interventions"),
    ('"cognitive offloading" "generative AI"', "AI & cognition"),
    ('"attention economy" "AI" ("design" OR "policy")', "Technology & society"),
]
PUBLISHERS = {
    "The Conversation", "The Verge", "Ars Technica", "WIRED", "MIT Technology Review",
    "Tech Policy Press", "The Atlantic", "The Guardian", "BBC", "The New York Times",
    "Financial Times", "The Economist", "Harvard Business Review", "IEEE Spectrum",
    "Nielsen Norman Group", "NPR", "Vox", "Rest of World", "EdSurge", "Inside Higher Ed",
    "404 Media", "The Markup", "TechCrunch", "Poynter", "New Scientist", "Nature",
    "Scientific American", "Fast Company", "Nieman Lab", "AI Now Institute", "Brookings",
    "Electronic Frontier Foundation",
}
AI = re.compile(r"\b(?:ai|genai|chatgpt|copilot|generative|artificial intelligence|language models?|llms?|claude|algorithmic)\b", re.I)
FOCUS = re.compile(r"\b(?:attention|focus|distraction|cognitive|offloading|thinking|mental effort|memory|learning|interruption|notifications?|task.switching|mindful|productivity|deep work|wellbeing|well-being|autonomy)\b", re.I)
NOISE = re.compile(r"stock (?:price|market)|share price|market cap|latest earnings|price target|football|crypto investment|gambling|celebrity|smartphone deal|focus on privacy|focuses on privacy|paying attention to (?:the|a|creative)|(?:ai|artificial intelligence).*museum|museum.*(?:ai|artificial intelligence)", re.I)
SENSITIVE_QUERY_KEYS = {"api_key", "apikey", "key", "access_token", "refresh_token", "id_token", "token", "auth", "authorization", "client_secret", "password", "passwd", "pwd", "session", "sessionid", "session_id", "sid", "secret", "signature", "sig"}
TRACKING = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "ref_src", "ref_url"}
FORMATS = {"journalism": "Technology journalism", "opinion": "Opinion & analysis",
           "policy": "Policy & analysis", "analysis": "Expert analysis"}


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def credentialed_url(value):
    try:
        parts = urllib.parse.urlsplit(value)
        return bool(parts.username or parts.password or any(
            key.casefold() in SENSITIVE_QUERY_KEYS
            for key, _ in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)))
    except (ValueError, TypeError):
        return True


def diagnostic_locator(value):
    """Keep ordinary article IDs, never userinfo, credential queries or fragments."""
    try:
        parts = urllib.parse.urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return ""
        query = urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                                       if k.casefold() not in SENSITIVE_QUERY_KEYS])
        return urllib.parse.urlunsplit((parts.scheme, parts.hostname, parts.path, query, ""))
    except (ValueError, TypeError):
        return ""


def url_key(value):
    """Remove known tracking only; article IDs in query strings are identity."""
    try:
        parts = urllib.parse.urlsplit(value)
        host = (parts.hostname or "").lower().removeprefix("www.")
        params = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                  if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
        query = urllib.parse.urlencode(sorted(params))
        return host + parts.path.rstrip("/") + ("?" + query if query else "")
    except ValueError:
        return value


def title_key(title, publisher, published):
    # Do not collapse similar titles, truncated prefixes, or different publishers.
    words = " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", title).casefold()))
    return (publisher.casefold(), published, words)


def normalize_date(value):
    """Normalize an actual publication field to a UTC date, never infer a day."""
    if not value:
        return ""
    value = str(value).strip()
    try:
        stamp = email.utils.parsedate_to_datetime(value)
    except (ValueError, TypeError, OverflowError):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                return datetime.date.fromisoformat(value).isoformat()
            except ValueError:
                return ""
        if not re.match(r"^\d{4}-\d{2}-\d{2}T", value):
            return ""
        try:
            stamp = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if stamp.tzinfo:
        stamp = stamp.astimezone(datetime.timezone.utc)
    return stamp.date().isoformat()


class FeedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, host):
        self.host = host.lower().removeprefix("www.")

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urllib.parse.urlsplit(newurl)
        if (parts.scheme != "https" or parts.username or parts.password
                or parts.port not in (None, 443)
                or (parts.hostname or "").lower().removeprefix("www.") != self.host):
            raise ValueError("feed_redirect_requires_review")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def get_xml(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("unsafe_feed_url")
    request = urllib.request.Request(url, headers={"User-Agent": AGENT,
        "Accept": "application/atom+xml,application/rss+xml,application/xml,text/xml"})
    with urllib.request.build_opener(FeedRedirects(parts.hostname)).open(request, timeout=22) as response:
        blob = response.read(MAX_FEED_BYTES + 1)
    if len(blob) > MAX_FEED_BYTES:
        raise ValueError("feed_size_limit_exceeded")
    root = ET.fromstring(blob)
    if root.tag not in (ATOM + "feed", "rss", "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"):
        raise ValueError("not_an_rss_or_atom_feed")
    return root


def atom_text(element, local):
    child = element.find(ATOM + local)
    return "".join(child.itertext()) if child is not None else ""


def parse_feed(root):
    output = []
    if root.tag == ATOM + "feed":
        for item in root.findall(ATOM + "entry"):
            links = item.findall(ATOM + "link")
            url = next((a.get("href") for a in links if a.get("rel", "alternate") == "alternate"), "")
            original = atom_text(item, "published")
            output.append({"title": clean(atom_text(item, "title")), "url": url,
                "description": clean(atom_text(item, "summary") or atom_text(item, "content")),
                "date": normalize_date(original), "date_raw": original,
                "date_basis": "publisher_atom_published" if original else "missing_original_publication_date",
                "updated": normalize_date(atom_text(item, "updated")),
                "authors": [clean(atom_text(a, "name")) for a in item.findall(ATOM + "author") if atom_text(a, "name")],
                "categories": [a.get("term", "") for a in item.findall(ATOM + "category")]})
    else:
        # RSS 2 and namespaced RSS 1. Never substitute channel lastBuildDate or dc:date.
        nodes = root.findall(".//item") + root.findall(".//{http://purl.org/rss/1.0/}item")
        for item in nodes:
            namespace = "{http://purl.org/rss/1.0/}" if item.tag.startswith("{") else ""
            source = item.find("source")
            original = item.findtext("pubDate") or ""
            output.append({"title": clean(item.findtext(namespace + "title")),
                "url": clean(item.findtext(namespace + "link")),
                "description": clean(item.findtext(namespace + "description")),
                "date": normalize_date(original), "date_raw": original,
                "date_basis": "publisher_rss_pubDate" if original else "missing_original_publication_date",
                "authors": [clean(a.text) for a in item.findall(DC + "creator") if a.text],
                "source": clean(source.text) if source is not None else "",
                "categories": [clean(a.text) for a in item.findall("category") if a.text]})
    return output


def next_page(root, current_url):
    container = root.find("channel") if root.tag == "rss" else root
    if container is None:
        return ""
    for link in container.findall(ATOM + "link"):
        if link.get("rel") != "next":
            continue
        target = urllib.parse.urljoin(current_url, link.get("href", ""))
        parts, old = urllib.parse.urlsplit(target), urllib.parse.urlsplit(current_url)
        if (parts.scheme != "https" or parts.hostname != old.hostname or parts.username
                or parts.password or parts.port not in (None, 443) or credentialed_url(target)):
            raise ValueError("feed_pagination_requires_review")
        return target
    return ""


def source_type(item, feed):
    tags = {str(x).strip().casefold() for x in item.get("categories", [])}
    for kind, values in (("opinion", {"opinion", "perspective", "commentary", "editorial"}),
                         ("analysis", {"analysis", "explainer"}),
                         ("policy", {"policy", "policy analysis", "policy brief"}),
                         ("journalism", {"news", "reporting", "investigation"})):
        if tags & values:
            return kind, "publisher_item_category"
    return feed.get("source_type", "analysis"), "provisional_feed_default"


def label(title, desc, category):
    # A design topic does not turn a reported article into product documentation.
    return "Opinion & analysis" if "commentary" in category.casefold() else category


def classify(title, desc):
    value = (title + " " + desc).lower()
    if re.search(r"\b(?:focus|notification|self.regulation|digital wellbeing|attention support|intervention|design)\b", value):
        return "Interventions"
    if re.search(r"distraction|fragmentation|interruption|task.switching", value):
        return "Fragmentation"
    if re.search(r"attention economy|ethics|agency|platform|policy", value):
        return "Technology & society"
    return "AI & cognition"


def eligible(item):
    """Topical screening only; exact publication-window admission is separate."""
    title, description = item["title"], item["description"]
    if len(title) < 16 or NOISE.search(title) or NOISE.search(description[:260]):
        return False
    if re.search(r"focus on (?:privacy|market|revenue|policy|security|investment)|paying attention to", title + " " + description[:100], re.I):
        return False
    body = title + " " + description
    # Technical model learning and ordinary rhetoric ("I think", regulatory
    # "agency", deployment "workflow") are not evidence of human cognition.
    human_body = re.sub(r"\b(?:machine|deep|reinforcement|representation|transfer) learning\b", "", body, flags=re.I)
    return bool((AI.search(body) and FOCUS.search(human_body)) or
                (re.search(r"attention|focus|digital wellbeing|notification|cognitive offload", title, re.I) and FOCUS.search(human_body)))


def allowed_article(url, feed):
    if not publisher_url(url) or credentialed_url(url):
        return False
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    return (not parts.username and not parts.password and parts.port in (None, 443)
            and any(host == domain or host.endswith("." + domain) for domain in feed["article_hosts"]))


def to_record(item, publisher, format_label, *, feed=None, today=None):
    today = today or TODAY
    title, desc = item["title"], item["description"]
    overview = ""
    if useful_description(title, desc, publisher) and publisher_url(item["url"]):
        overview = desc[:320].rsplit(" ", 1)[0] + "…" if len(desc) > 320 else desc
    kind, basis = source_type(item, feed or {"source_type": "analysis"})
    return {
        "title": title, "authors": item.get("authors", []), "published": item["date"], "venue": publisher,
        "doi": "", "url": item["url"], "preview": overview or "Source listed; editorial text not yet available.",
        "kind": "nonacademic", "lane": classify(title, desc), "relation": "Nonacademic reporting / commentary",
        "evidence": "Publisher feed metadata (not independently reviewed)",
        "source": "Publisher RSS / Google News RSS", "format": format_label,
        "source_type": kind, "source_type_basis": basis,
        "publication_date_provenance": {"basis": item.get("date_basis", "unspecified"),
            "raw": item.get("date_raw", ""), "date": item["date"], "timezone": "UTC",
            "source_url": (feed or {}).get("url", ""), "independently_verified": False},
        "discovery_provenance": {"method": "publisher_feed", "feed_id": (feed or {}).get("id", ""),
            "feed_url": (feed or {}).get("url", ""), "checked_at": today.isoformat(),
            **({"metadata_snapshot_observed_at": item["_snapshot_observed_at"]} if item.get("_snapshot_observed_at") else {})},
        "curated": False, "first_seen": today.isoformat(),
        "reading": {"level": "source_preview" if overview else "citation_only",
            "provenance": publisher + " RSS/Atom description", "overview": overview,
            "methods": "", "findings": "", "limitations": "",
            "notice": "Publisher-supplied discovery preview, not a full-article review or independent assessment."},
        "content_access": "feed_description" if overview else "headline_only", "source_checked": today.isoformat(),
    }


def quarantine_item(item, feed, reason):
    return {"title": item["title"], "url": diagnostic_locator(item["url"]), "publisher": feed["name"],
            "feed_id": feed["id"], "reported_date": item.get("date", ""),
            "reported_date_basis": item.get("date_basis", ""), "status": reason,
            "eligible_for_weekly": False}


def collect(existing, *, now=None, feeds=None, searches=None, fetcher=get_xml, sleep=time.sleep, cached_items=None, cache_coverage=None, live=True, mode="weekly", publication_window=None):
    today = now or TODAY
    if isinstance(today, datetime.datetime):
        today = today.astimezone(datetime.timezone.utc).date() if today.tzinfo else today.date()
    start, end = discovery_window(today, mode, publication_window)
    feeds = FEEDS if feeds is None else feeds
    searches = GOOGLE_SEARCHES if searches is None else searches
    seen = {url_key(x["url"]) for x in existing if x.get("url")}
    titles = {title_key(x.get("title", ""), x.get("venue", ""), x.get("published", "")) for x in existing}
    added, quarantine, reports, verified_existing = [], [], [], []
    date_conflicts = {}
    existing_by_url = {url_key(row["url"]): row for row in existing if row.get("url")}
    observed_by_url = {}
    paused_hosts = {}
    cached_items = cached_items or {}
    cache_coverage = cache_coverage or {}
    for feed in feeds:
        report = {"source_id": feed["id"], "name": feed["name"], "feed_url": feed["url"],
                  "status": "ok", "pages": 0, "returned": 0, "accepted": 0, "warnings": []}
        rejected, dates, visited = Counter(), [], set()
        host = urllib.parse.urlsplit(feed["url"]).hostname
        cached = list(cached_items.get(feed["id"], []))
        cache_pending = bool(cached)
        report["cached_candidates"] = sum(date_in_window(x.get("date"), start, end) for x in cached)
        report["cached_evidence_rows"] = len(cached)
        report["snapshot_coverage"] = cache_coverage.get(feed["id"], {})
        current = feed["url"] if live else ""
        if not live:
            report.update(status="partial")
            report["warnings"].append("live_feed_not_requested_cached_recovery_only")
        if host in paused_hosts:
            report.update(status="deferred", reason=paused_hosts[host])
            current = ""
        try:
            while current or cache_pending:
                from_cache = cache_pending
                if from_cache:
                    items = cached
                    cache_pending = False
                else:
                    if current in visited:
                        report["warnings"].append("pagination_loop")
                        break
                    if report["pages"] >= MAX_FEED_PAGES:
                        report["warnings"].append("pagination_page_limit_reached")
                        break
                    visited.add(current)
                    root = fetcher(current)
                    items = parse_feed(root)
                    report["pages"] += 1
                    report["returned"] += len(items)
                    dates.extend(x["date"] for x in items if x["date"])
                for item in items:
                    topical = eligible(item) or (from_cache and item.get("_snapshot_screening_version") == 1)
                    key = url_key(item["url"])
                    if not topical and key not in existing_by_url and key not in observed_by_url:
                        rejected["not_topical"] += 1
                        continue
                    if not item["date"]:
                        rejected["original_publication_date_missing"] += 1
                        quarantine.append(quarantine_item(item, feed, "original_publication_date_missing"))
                        continue
                    if not allowed_article(item["url"], feed):
                        rejected["publisher_url_unverified"] += 1
                        quarantine.append(quarantine_item(item, feed, "publisher_url_unverified"))
                        continue
                    key = url_key(item["url"])
                    old = existing_by_url.get(key) or observed_by_url.get(key)
                    fresh = to_record(item, feed["name"], "", feed=feed, today=today)
                    observed_by_url.setdefault(key, fresh)
                    # A publisher correction outside this week's bounds still
                    # invalidates an old in-window date. Preserve both accounts.
                    cached_conflict = item.get("_snapshot_conflicting_dates") if from_cache else []
                    if (old and old.get("published") and old["published"] != item["date"]) or cached_conflict:
                        rejected["conflicting_original_publication_dates"] += 1
                        quarantine.append(quarantine_item(item, feed, "conflicting_original_publication_dates"))
                        fresh = to_record(item, feed["name"], "", feed=feed, today=today)
                        prior = old or fresh
                        conflict = date_conflicts.setdefault(key, {"url": prior["url"],
                            "stored_publication_date": prior["published"], "conflicting_evidence": [prior.get("publication_date_provenance", {"date":prior["published"]})]})
                        conflict["conflicting_evidence"].append(fresh["publication_date_provenance"])
                        if cached_conflict:
                            conflict["conflicting_evidence"].append({"basis": "publisher_feed_cache_conflict",
                                "status": "unresolved", "observed_original_dates": list(cached_conflict)})
                        if key not in seen and key not in existing_by_url and date_in_window(item["date"],start,end):
                            kind,_=source_type(item,feed)
                            added.append(to_record(item,feed["name"],FORMATS[kind],feed=feed,today=today))
                            seen.add(key)
                        continue
                    if not topical:
                        rejected["not_topical"] += 1
                        continue
                    if not date_in_window(item["date"], start, end):
                        rejected["outside_previous_week"] += 1
                        continue
                    name = title_key(item["title"], feed["name"], item["date"])
                    if key in seen or name in titles:
                        if old and old.get("published") == item["date"]:
                            fresh = to_record(item, feed["name"], "", feed=feed, today=today)
                            verified_existing.append({"url": old["url"], "published": item["date"],
                                "publication_date_provenance": fresh["publication_date_provenance"],
                                "discovery_provenance": fresh["discovery_provenance"]})
                        rejected["duplicate"] += 1
                        continue
                    seen.add(key)
                    titles.add(name)
                    kind, _ = source_type(item, feed)
                    added.append(to_record(item, feed["name"], FORMATS[kind], feed=feed, today=today))
                    report["accepted"] += 1
                if not from_cache:
                    current = next_page(root, current)
                    if current:
                        sleep(.25)
        except Exception as error:
            report["status"] = "failed" if not report["pages"] else "partial"
            report["error_type"] = type(error).__name__
            report["error"] = "HTTP " + str(error.code) if isinstance(error, urllib.error.HTTPError) else str(error)[:140]
            if isinstance(error, urllib.error.HTTPError) and error.code in (401, 403, 429):
                paused_hosts[host] = "provider_http_" + str(error.code)
                report["retry_after"] = (error.headers.get("Retry-After", "") if error.headers else "")
        report["rejected"] = dict(rejected)
        report["oldest_original_date"] = min(dates) if dates else ""
        report["newest_original_date"] = max(dates) if dates else ""
        if not dates:
            report["warnings"].append("no_original_publication_dates_returned")
        else:
            if min(dates) > start.isoformat():
                report["warnings"].append("rolling_feed_does_not_reach_window_start")
            if max(dates) < start.isoformat():
                report["warnings"].append("newest_feed_entry_predates_publication_window")
        if report["warnings"] and report["status"] == "ok":
            report["status"] = "partial"
        reports.append(report)
        sleep(.25)
    # Aggregator timestamps are not proof of original publication. Keep bounded-
    # date search leads separate until a canonical publisher and date are verified.
    for index, (query, lane) in enumerate(searches if live else []):
        exact = f"{query} after:{(start - datetime.timedelta(days=1)).isoformat()} before:{(end + datetime.timedelta(days=1)).isoformat()}"
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": exact, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        report = {"source_id": f"google-news-{index + 1}", "name": "Google News RSS", "status": "leads_only",
                  "query": exact, "returned": 0, "accepted": 0, "warnings": ["original_publisher_and_publication_date_unverified"]}
        if "news.google.com" in paused_hosts:
            report.update(status="deferred", reason=paused_hosts["news.google.com"])
            reports.append(report)
            continue
        try:
            items = parse_feed(fetcher(url))
            report["returned"] = len(items)
            for item in items:
                publisher = item.get("source", "")
                if publisher not in PUBLISHERS or not eligible(item):
                    continue
                if item["date"] and not date_in_window(item["date"], start, end):
                    continue
                item["date_basis"] = "aggregator_pubDate_not_verified_original"
                quarantine.append(quarantine_item(item, {"name": publisher, "id": report["source_id"]},
                                                   "canonical_publisher_and_original_date_required"))
        except Exception as error:
            report.update(status="failed", error_type=type(error).__name__)
            if isinstance(error, urllib.error.HTTPError):
                report["http_status"] = error.code
                report["retry_after"] = (error.headers.get("Retry-After", "") if error.headers else "")
            # One failed supplemental provider must not generate repeated requests
            # into a rate limit, access refusal or outage during the same run.
            paused_hosts["news.google.com"] = "supplemental_provider_unavailable"
        reports.append(report)
        sleep(.25)
    quarantine = list({(x["url"], x["status"]): x for x in quarantine}.values())
    status = {"schema_version": 1, "checked_on": today.isoformat(),
        "publication_window": window_metadata(today) if mode == "weekly" else {
            "from": start.isoformat(), "to": end.isoformat(), "timezone": "UTC", "scope": mode},
        "date_policy": "Publisher original publication field only; never modified, indexed, Google News or first-seen dates.",
        "scope": "Configured feeds and explicit search queries, not exhaustive coverage of online publishing.",
        "status": "partial" if any(x["status"] in ("failed", "partial", "deferred") for x in reports) else "completed_configured_sources",
        "accepted": len(added), "quarantined": len(quarantine),
        "source_type_counts": dict(Counter(x["source_type"] for x in added)),
        "full_articles_retrieved": 0, "verified_existing_records": verified_existing,
        "conflicting_existing_records": list(date_conflicts.values()), "sources": reports}
    added=apply_discovery_evidence(added,status)
    status["accepted"]=sum(weekly_eligible(row,start,end) for row in added)
    status["source_type_counts"]=dict(Counter(row["source_type"] for row in added if weekly_eligible(row,start,end)))
    status["conflicting_new_records"]=sum(url_key(row["url"]) in date_conflicts for row in added)
    return added, status, quarantine


def apply_discovery_evidence(data, status):
    """Update date evidence without replacing articles or clearing conflicts."""
    verified = {url_key(row["url"]): row for row in status.get("verified_existing_records", [])}
    conflicts = {url_key(row["url"]): row for row in status.get("conflicting_existing_records", [])}
    unresolved = {"unresolved", "conflict", "conflicting", "unknown"}
    for row in data:
        key = url_key(row.get("url", ""))
        prior = row.get("publication_date_provenance") or {}
        conflict = conflicts.get(key)
        if conflict:
            evidence = list(prior.get("evidence") or []) if prior.get("status") in unresolved else []
            if not evidence:
                evidence.append(dict(prior, date=row.get("published", "")))
            evidence.extend(conflict["conflicting_evidence"])
            evidence = list({json.dumps(x, sort_keys=True): x for x in evidence}.values())
            row["publication_date_provenance"] = {
                "status": "unresolved", "reason": "conflicting_original_publication_dates",
                "stored_publication_date": row.get("published", ""), "evidence": evidence}
            continue
        match = verified.get(key)
        if (match and match["published"] == row.get("published")
                and prior.get("status") not in unresolved):
            incoming = match["publication_date_provenance"]
            # Rediscovery must not downgrade a checked publisher date to the
            # same RSS observation already included in its evidence. Otherwise
            # the next publisher check reconstructs the identical evidence with
            # a fresh timestamp and invalidates an unchanged article receipt.
            # Compare the verifier's exact normalized evidence, not date alone:
            # a new feed source or basis must still change the bound context.
            from editorial_metadata import prior_evidence
            observation = prior_evidence({"publication_date_provenance": incoming})
            known_observation = (
                prior.get("status") == "day_known"
                and prior.get("independently_verified") is True
                and (prior.get("value") or prior.get("date")) == row["published"]
                and incoming.get("basis") in {"publisher_rss_pubDate", "publisher_atom_published"}
                and len(observation) == 1
                and observation[0] in (prior.get("evidence") or [])
            )
            if not known_observation:
                row["publication_date_provenance"] = incoming
            row["discovery_provenance"] = match["discovery_provenance"]
    return data


def run(*, cached_only=False):
    path = DIR / "library.json"
    data = apply_source_reviews(apply_editorial_corrections(json.loads(path.read_text())))
    from editorial_feed_cache import load_cache, candidate_items, coverage_report
    cache = load_cache(DIR / "editorial-feed-cache.json", FEEDS)
    added, status, quarantine = collect(data, cached_items=candidate_items(cache, FEEDS, now=TODAY),
                                         cache_coverage=coverage_report(cache, FEEDS, now=TODAY), live=not cached_only)
    # Historical and curated records remain in the archive; never relabel them as new.
    data.extend(added)
    apply_discovery_evidence(data, status)
    data = apply_source_reviews(apply_editorial_corrections(data))
    data.sort(key=lambda row: (row.get("published") or "", row.get("first_seen") or ""), reverse=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    (DIR / "editorial-discovery-status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    (DIR / "editorial-discovery-quarantine.json").write_text(json.dumps({"publication_window": status["publication_window"], "items": quarantine}, ensure_ascii=False, indent=2) + "\n")
    week_path = DIR / "weekly.json"
    week = json.loads(week_path.read_text())
    start, end = previous_week(TODAY)
    week["items"] = [row for row in data if weekly_eligible(row, start, end)]
    week["run"].update(total=len(data), nonacademic_added=len(added),
        nonacademic_total=sum(x.get("kind") == "nonacademic" for x in data))
    week["run"]["new"] = week["run"].get("new", 0) + len(added)
    week["run"].setdefault("stats", {})["editorial_feeds"] = status
    week_path.write_text(json.dumps(week, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached-only", action="store_true", help="Use staged previous-week metadata without repeating live feed/search requests")
    args = parser.parse_args()
    run(cached_only=args.cached_only)

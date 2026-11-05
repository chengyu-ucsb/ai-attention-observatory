"""Find OpenAIRE locations for an exact DOI without fetching source documents.

The caller supplies a bounded JSON getter, which also owns HTTP errors and
rate-limit handling. OpenAIRE's result PID is checked before inspecting its
locations; DOIs and URLs inside citations or other relations are never used.
Location metadata does not establish document access or redistribution rights.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ENDPOINT = "https://api.openaire.eu/search/publications"
DOI = re.compile(r"10\.\d{4,9}/[^\s<>?#\\]+", re.I)
SENSITIVE_QUERY = re.compile(
    r"token|secret|password|authorization|credential|signature|"
    r"api[-_]?key|access[-_]?key|^auth$|^sig$|^policy$|^expires$|^x-amz-|^x-goog-",
    re.I,
)
VERSIONS = {"submittedversion", "acceptedversion", "publishedversion"}


def _items(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("$"), str):
        return value["$"]
    return ""


def _doi(value):
    if not isinstance(value, str):
        return ""
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I).lower()
    if len(value) > 500 or not DOI.fullmatch(value):
        return ""
    # Encoded controls and URL delimiters must not become another identifier.
    if re.search(r"%(?:0[0-9a-f]|1[0-9a-f]|7f|3f|23|5c)", value, re.I):
        return ""
    return value


def _pids(node):
    """Only this publication's declared DOI PIDs, never nested references."""
    return {
        normalized
        for pid in _items(node.get("pid"))
        if isinstance(pid, dict) and str(pid.get("@classid", "")).lower() == "doi"
        if (normalized := _doi(_text(pid)))
    }


def _source_url(value):
    value = _text(value).strip()
    if not value or len(value) > 2000 or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return ""
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if (parts.scheme != "https" or parts.username or parts.password
                or parts.port not in (None, 443) or not host):
            return ""
        # Source documents must have public DNS hostnames. The caller still
        # applies its stricter approved-host and redirect checks before a GET.
        try:
            ipaddress.ip_address(host)
            return ""
        except ValueError:
            pass
        labels = host.split(".")
        if (len(labels) < 2 or not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", labels[-1])
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", x)
                       or len(x) > 63 for x in labels)
                or host.endswith((".localhost", ".local", ".internal", ".invalid", ".test"))):
            return ""
        if any(SENSITIVE_QUERY.search(key) for key, _ in parse_qsl(parts.query)):
            return ""
        if host in ("doi.org", "dx.doi.org") and not _doi(parts.path.lstrip("/")):
            return ""
        return urlunsplit(("https", host, parts.path, parts.query, ""))
    except (TypeError, ValueError):
        return ""


def _license(node):
    for item in _items(node.get("license")):
        value = _text(item).strip()
        if value and len(value) <= 300:
            return value
    # Some repository deposits encode their license as the accessright URI.
    for access in _items(node.get("accessright")):
        if isinstance(access, dict):
            value = access.get("@classid", "")
            if isinstance(value, str) and value.startswith("https://creativecommons.org/"):
                return value
    return None


def _version(node):
    for item in _items(node.get("version")):
        value = _text(item).strip()
        if value.lower() in VERSIONS:
            return value
    return "unspecified"


def _locations(node, identifier, depth=0):
    if not isinstance(node, dict) or depth > 5:
        return
    declared = _pids(node)
    if declared and identifier not in declared:
        return
    # These keys are the actual location fields in the public OpenAIRE API.
    for key in ("fulltext", "url"):
        for value in _items(node.get(key)):
            yield value, node
    for resource in _items(node.get("webresource")):
        if isinstance(resource, dict):
            for value in _items(resource.get("url")):
                yield value, node
    for instance in _items(node.get("instance")):
        yield from _locations(instance, identifier, depth + 1)
    children = node.get("children")
    if isinstance(children, dict):
        for key in ("result", "instance"):
            for child in _items(children.get(key)):
                yield from _locations(child, identifier, depth + 1)


def openaire_candidates(identifier, get):
    """Return all safe, deduplicated locations of exactly matching publications.

    ``get(url)`` returns parsed JSON and should enforce response-size, timeout,
    and host limits. HTTP failures propagate so the acquisition caller can log
    them and move to another provider. No email, API key, or source GET is used.
    """
    identifier = _doi(identifier)
    if not identifier:
        raise ValueError("invalid_doi")
    data = get(ENDPOINT + "?" + urlencode({"doi": identifier, "format": "json"}))
    response = data.get("response", {}) if isinstance(data, dict) else {}
    results = response.get("results", {}) if isinstance(response, dict) else {}
    wrappers = results.get("result") if isinstance(results, dict) else None
    candidates = {}
    for wrapper in _items(wrappers):
        if not isinstance(wrapper, dict):
            continue
        metadata = wrapper.get("metadata", {})
        entity = metadata.get("oaf:entity", {}) if isinstance(metadata, dict) else {}
        publications = entity.get("oaf:result") if isinstance(entity, dict) else None
        for publication in _items(publications):
            if not isinstance(publication, dict) or identifier not in _pids(publication):
                continue
            for raw, owner in _locations(publication, identifier):
                url = _source_url(raw)
                if not url:
                    continue
                # A DOI resolver pointing at another publication is not a copy.
                parts = urlsplit(url)
                if (parts.hostname in ("doi.org", "dx.doi.org")
                        and _doi(parts.path.lstrip("/")) != identifier):
                    continue
                option = {
                    "url": url, "provider": "OpenAIRE", "doi": identifier,
                    "version": _version(owner), "license": _license(owner),
                    "redistribution_granted": False,
                }
                if url not in candidates:
                    candidates[url] = option
                else:
                    prior = candidates[url]
                    if not prior["license"]:
                        prior["license"] = option["license"]
                    if prior["version"] == "unspecified":
                        prior["version"] = option["version"]
    return list(candidates.values())

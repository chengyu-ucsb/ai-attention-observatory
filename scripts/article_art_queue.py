"""Private, durable allocation and bounded-retry state for public article art.

Only build_public's already-admitted records reach this boundary. The queue never
loads source records or grants publication eligibility. It stores canonical IDs,
art fingerprints and candidate-review metadata, not source text or copied prose.

The state is a snapshot of candidates assessed for the current inputs, not a
build counter. Unchanged exhausted inputs can reuse their results; changing any
public candidate pool or collection membership allows reconsideration. Accepted
allocations are always checked by the renderer, including their actual assets.

Scheduled data-producing workflows commit this file with data/. A publish-only
build writes it locally but needs a separate workflow artifact/commit to retain
that run's changes. It must not be copied into the public _site payload.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

import article_art as art

STATE_VERSION = 1
STATE_FILENAME = "article-art-state.json"
HASH = re.compile(r"[a-f0-9]{64}")
TOKEN = re.compile(r"[a-z][a-z0-9_.-]{0,79}")
PATH = re.compile(r"assets/(?:article-art|editorial-covers)/[a-z0-9-]+\.(?:svg|png|webp|jpg)")
STATUSES = {"ready", "needs_review"}
RETRY_STATUSES = {"accepted", "exhausted", "insufficient_context", "editorial_review", "validation_failed"}
FINGERPRINTS = {
    "input_fingerprint", "candidate_fingerprint", "candidate_pool_fingerprint",
    "asset_fingerprint", "thumbnail_fingerprint", "composition_fingerprint",
    "foreground_geometry_fingerprint", "coarse_raster_fingerprint",
}
METRICS = {"full_mean_difference", "foreground_mean_difference", "foreground_iou", "foreground_pixels"}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _identity(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 4096:
        return False
    try:
        if value.startswith("doi:"):
            return len(value) > 4 and art.canonical_identity({"doi": value}) == value
        if value.startswith("url:"):
            return art.canonical_identity({"url": value[4:]}) == value
        return value.startswith("title:") and HASH.fullmatch(value[6:]) is not None
    except (ValueError, TypeError):
        return False


def _reasons(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, str) and TOKEN.fullmatch(item)})


def _collisions(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict) or not _identity(item.get("identity")):
            continue
        reason = item.get("reason")
        if not isinstance(reason, str) or not TOKEN.fullmatch(reason):
            continue
        clean = {"identity": item["identity"], "reason": reason}
        metrics = item.get("metrics")
        if isinstance(metrics, dict):
            clean["metrics"] = {key: number for key, number in metrics.items()
                                if key in METRICS and type(number) in (int, float)
                                and math.isfinite(number) and number >= 0}
        result.append(clean)
    return result


def safe_metadata(value: object) -> dict:
    """Explicit allowlist: even stale state/projections cannot cache source prose."""
    if not isinstance(value, dict) or not isinstance(value.get("status"), str) or value["status"] not in STATUSES:
        return {}
    clean = {"status": value["status"]}
    for key in FINGERPRINTS:
        token = value.get(key)
        if isinstance(token, str) and HASH.fullmatch(token):
            clean[key] = token
    for key in ("renderer_version", "coarse_raster_version", "candidate_policy_version"):
        token = value.get(key)
        if isinstance(token, str) and TOKEN.fullmatch(token):
            clean[key] = token
    for key in ("candidate_index", "candidate_count", "attempt_count"):
        number = value.get(key)
        if type(number) is int and 0 <= number <= art.MAX_ART_CANDIDATES:
            clean[key] = number
    if isinstance(value.get("retry_status"), str) and value["retry_status"] in RETRY_STATUSES:
        clean["retry_status"] = value["retry_status"]
    if "review_reasons" in value:
        clean["review_reasons"] = _reasons(value["review_reasons"])
    if "review_collisions" in value:
        clean["review_collisions"] = _collisions(value["review_collisions"])
    # Geometry signatures are derived artwork bytes, never source text. They
    # allow held results to retain the same non-prose diagnostic fields.
    signature = value.get("coarse_raster_signature")
    if (isinstance(signature, str) and len(signature) <= 32768
            and re.fullmatch(r"rgb1:[A-Za-z0-9+/=]+", signature)):
        clean["coarse_raster_signature"] = signature
    size = value.get("coarse_raster_size")
    if isinstance(size, list) and len(size) == 2 and all(type(n) is int and 1 <= n <= 512 for n in size):
        clean["coarse_raster_size"] = size[:]
    foreground = value.get("foreground_signature")
    if isinstance(foreground, str) and re.fullmatch(r"[a-z][a-z0-9_]*\|[a-z][a-z0-9_]*", foreground):
        clean["foreground_signature"] = foreground
    if isinstance(value.get("format"), str) and value["format"] in {"svg", "png", "webp", "jpg"}:
        clean["format"] = value["format"]
    for key in ("width", "height", "thumbnail_width", "thumbnail_height"):
        number = value.get(key)
        if type(number) is int and 1 <= number <= 10000:
            clean[key] = number
    if value["status"] == "ready":
        for key in ("src", "thumbnail_src"):
            path = value.get(key)
            if isinstance(path, str) and PATH.fullmatch(path):
                clean[key] = path
    attempts = value.get("retry_attempts")
    if isinstance(attempts, list):
        clean["retry_attempts"] = []
        for attempt in attempts[:art.MAX_ART_CANDIDATES]:
            if not isinstance(attempt, dict):
                continue
            # An attempt is itself a small status/fingerprint/reasons record.
            entry = safe_metadata({key: attempt[key] for key in
                ("status", "candidate_index", "candidate_fingerprint", "review_reasons", "review_collisions")
                if key in attempt})
            if entry:
                clean["retry_attempts"].append(entry)
    return clean


def _complete(value: dict) -> bool:
    """A cache must describe one real, bounded assessment, not invented progress."""
    required = {"status", "renderer_version", "input_fingerprint", "candidate_index", "candidate_count",
                "candidate_fingerprint", "candidate_pool_fingerprint", "retry_status", "attempt_count", "retry_attempts"}
    if not required.issubset(value):
        return False
    count, attempts = value["candidate_count"], value["retry_attempts"]
    if not 1 <= count <= art.MAX_ART_CANDIDATES or not 0 <= value["candidate_index"] < count:
        return False
    if not 1 <= value["attempt_count"] == len(attempts) <= count:
        return False
    indices = [attempt.get("candidate_index") for attempt in attempts]
    if any(type(index) is not int or not 0 <= index < count for index in indices) or len(indices) != len(set(indices)):
        return False
    if any(not {"candidate_fingerprint", "review_reasons"}.issubset(item) for item in attempts):
        return False
    for key in ("candidate_index", "candidate_fingerprint", "status", "review_reasons", "review_collisions"):
        if value.get(key) != attempts[-1].get(key):
            return False
    if any(item["status"] != "needs_review" or not item["review_reasons"] for item in attempts[:-1]):
        return False
    if value["status"] == "ready":
        return (value["retry_status"] == "accepted" and not value.get("review_reasons")
                and not value.get("review_collisions") and bool(value.get("src") and value.get("asset_fingerprint")))
    if value["retry_status"] == "accepted" or not value.get("review_reasons"):
        return False
    if value["retry_status"] == "exhausted":
        return len(attempts) == count and set(indices) == set(range(count))
    if value["retry_status"] in {"insufficient_context", "editorial_review"}:
        return count == 1
    return value["retry_status"] == "validation_failed"


def load_state(path: Path) -> dict:
    """Discard unsupported/corrupt state safely, then rebuild from current inputs."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, UnicodeError):
        print("Article art state is unreadable; rebuilding allocations from current public inputs.", file=sys.stderr)
        return {}
    if (not isinstance(payload, dict) or type(payload.get("version")) is not int
            or payload["version"] != STATE_VERSION or not isinstance(payload.get("articles"), dict)):
        print("Article art state has an unsupported schema; rebuilding current allocations.", file=sys.stderr)
        return {}
    entries = {}
    for identity, value in payload["articles"].items():
        clean = safe_metadata(value)
        if _identity(identity) and _complete(clean):
            entries[identity] = clean
    return {"articles": entries, "corpus_fingerprint": payload.get("corpus_fingerprint")}


def _seed_previous_public(path: Path | None, admitted: set[str]) -> dict:
    if path is None:
        return {}
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeError):
        return {}
    if not isinstance(previous, list):
        return {}
    result = {}
    for record in previous:
        if not isinstance(record, dict):
            continue
        try:
            identity = art.canonical_identity(record)
        except (ValueError, TypeError):
            continue
        metadata = safe_metadata(record.get("editorial_art"))
        if identity in admitted and metadata.get("status") == "ready":
            result[identity] = metadata
    return result


def write_state(path: Path, payload: dict) -> bool:
    """Replace atomically; unchanged results preserve bytes and modification time."""
    content = (json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    try:
        if path.read_bytes() == content:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def attach_persistent_art(records: list[dict], root: Path = art.ROOT, manifest: Path | None = None, *,
                          state_path: Path | None = None, previous_public: Path | None = None) -> list[dict]:
    """Hydrate safe allocation hints, decorate admitted records, and save a snapshot.

    State never supplies records: removed or newly quarantined IDs are pruned.
    Input/policy/override/collection changes unlock another bounded assessment,
    while identical exhausted pools are not represented as fresh attempts.
    """
    root = Path(root)
    state_path = Path(state_path) if state_path is not None else root / "data" / STATE_FILENAME
    overrides = art.load_overrides(root, manifest)
    pools = {art.canonical_identity(record): art.candidate_pool_fingerprint(record, overrides) for record in records}
    if len(pools) != len(records):
        raise ValueError("Article art allocation requires unique canonical public identities")
    corpus = digest({"state_version": STATE_VERSION, "candidate_pools": pools})
    state = load_state(state_path)
    prior = state.get("articles", {})
    reuse_exhausted = state.get("corpus_fingerprint") == corpus and set(prior) == set(pools)
    seeds = _seed_previous_public(previous_public, set(pools))
    for record in records:
        identity = art.canonical_identity(record)
        # Only the state or previous public projection is an allocation hint.
        # Source-index editorial_art fields must not bypass this boundary.
        record.pop("editorial_art", None)
        value = prior.get(identity) or seeds.get(identity)
        if value:
            record["editorial_art"] = value
    art.attach_art(records, root, manifest, reuse_exhausted=reuse_exhausted)
    entries = {art.canonical_identity(record): safe_metadata(record["editorial_art"]) for record in records}
    summary = dict(sorted(Counter(value.get("retry_status", "unknown") for value in entries.values()).items()))
    write_state(state_path, {"version": STATE_VERSION, "corpus_fingerprint": corpus,
                            "retry_status_counts": summary, "articles": entries})
    return records

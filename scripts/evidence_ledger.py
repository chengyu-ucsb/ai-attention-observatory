"""Private, resumable evidence checkpoints. No retrieval or publication entry point.

The caller explicitly selects a private directory OUTSIDE every checkout and
supplies the exact ephemeral source and chunk plan again on resume. A policy
fingerprint must cover model/weights, prompts, inference settings and validators.
Changing any of these requires separate work, never blending prior acceptance.

Only ``run_chunk`` creates accepted checkpoints: it calls the unchanged
``comprehensive_readings.read_chunk`` gate, then rechecks deterministic and
privacy constraints. Its model argument is not promoted or selected here.
Accepted original paraphrases are saved; quotes, source prose, bytes, raw model
responses, URLs and exception messages are not. Provenance identifiers, source
locators and versions are hashed; recover their readable values from the caller's
private source catalog. Locations and controlled section roles remain readable.

The checksum detects accidental corruption, NOT malicious same-user rewriting or
rollback. Private ownership/permissions and the caller's policy fingerprint are
part of the trust boundary. POSIX advisory locking protects cooperating writers.
The files are private, not encrypted. Filesystem durability depends on fsync.

Cross-section examination/resolution are explicit caller attestations, not a
semantic detector or independent review. There is no publication-ready state.
An interrupted or rejected chunk remains unresolved; this API never retries it.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
from urllib.parse import urlsplit
from uuid import uuid4

import comprehensive_readings as reading

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1
MAX_FILE_BYTES = 16_000_000
HASH = re.compile(r"[0-9a-f]{64}")
SECTIONS = frozenset(("unknown", "abstract", "introduction", "background", "methods",
    "results", "discussion", "limitations", "conclusion", "references", "appendix"))
PROVIDERS = frozenset(("unspecified", "publisher", "repository", "zotero", "indexed",
    "europe_pmc", "openalex", "arxiv", "user_supplied"))
LICENSES = frozenset(("unknown", "restricted", "cc-by", "cc-by-sa", "cc-by-nc",
    "cc-by-nc-nd", "cc-by-nd", "cc0", "public-domain"))
LOCATION = re.compile(r"(?:page|paragraph|unit):[1-9][0-9]*|(?:indexed_section|section):"
                      r"(?:abstract|introduction|background|methods|results|discussion|limitations|"
                      r"conclusion|references|appendix)(?::[1-9][0-9]*)?")
OBLIGATION_KINDS = frozenset(("later_limitation", "contradiction", "scope_qualification"))
RESOLUTIONS = frozenset(("qualified_in_private_review", "no_claim_change_after_review"))
FAILURES = frozenset(("reader_failed", "invalid_checked_claims", "privacy_check_failed",
    "claim_not_object", "unsupported_claim_field", "claim_length_invalid", "claim_anchor_invalid",
    "claim_anchor_absent", "ambiguous_claim_anchor", "unsupported_numeric_claim", "copied_source_passage",
    "verifier_schema_invalid", "verifier_indices_invalid", "claim_verification_failed",
    "verifier_output_truncated", "verifier_output_incomplete", "unknown_source_span",
    "invalid_claim_list", "unexplained_empty_segment", "model_schema_invalid", "model_json_invalid",
    "model_output_truncated", "model_output_incomplete", "deferred_document_time_budget",
    "deferred_model_context_budget", "unverified_model_chat_format",
    "deferred_chunk_without_evidence_span", "evidence_span_coverage_gap",
    "interrupted_or_uncertain"))
# Conservative privacy filter, not a general secret detector. In addition to
# deterministic source-copy checks, reject URLs, credential wording and token-like
# strings. Callers still need private/independent review of original paraphrases.
PRIVATE_TEXT = re.compile(r'[%]PDF-|[`"“”«»‹›„‟〝〞〟「」『』]|[A-Za-z][A-Za-z0-9+.-]*://|//|www\.|'
    r'\b[^\s/@:]+:[^\s/@]+@|\b(?:password|passwd|secret|api[ _-]?key|'
    r"access[ _-]?token|authorization|bearer)\b|[A-Za-z0-9_+=/-]{32,}", re.I)


SINGLE_QUOTATION = re.compile(r"(?:^|[\s(])['‘][^'’\n]{2,}['’](?:$|[\s.,;)])")


class LedgerError(ValueError):
    """Controlled code only; never include raw source, response or exception text."""


def _fail(code):
    raise LedgerError(code) from None


def _hash(text):
    if type(text) is not str:
        _fail("invalid_source_context")
    try:
        return sha256(text.encode("utf-8")).hexdigest()
    except UnicodeError:
        _fail("invalid_source_context")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _digest(value):
    return sha256(_canonical(value)).hexdigest()


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail("invalid_ledger_schema")


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _is_hash(value):
    return type(value) is str and HASH.fullmatch(value) is not None


@dataclass(frozen=True, repr=False)
class SourceContext:
    """Ephemeral source. Nothing in document.coverage is trusted or persisted.

    ``sections`` is an optional tuple/list of controlled roles, one per unit.
    Source IDs and exact URLs/versions are retained as hashes, never raw strings.
    ``policy_sha256`` is REQUIRED and must fingerprint the actual complete policy.
    """
    document: object
    chunks: list
    source_id: str
    policy_sha256: str
    kind: str = "scholarly"
    provider: str = "unspecified"
    license_code: str = "unknown"
    sections: tuple | list | None = field(default=None, repr=False)


def _capture(source):
    if type(source) is not SourceContext:
        _fail("invalid_source_context")
    if (not _is_hash(source.policy_sha256) or type(source.kind) is not str or source.kind not in reading.FIELDS or
            type(source.provider) is not str or source.provider not in PROVIDERS or
            type(source.license_code) is not str or source.license_code not in LICENSES or
            type(source.source_id) is not str or not source.source_id):
        _fail("invalid_source_context")
    doc = source.document
    try:
        units, url, version = doc.units, doc.url, doc.version
    except AttributeError:
        _fail("invalid_source_context")
    if (type(units) is not list or not units or type(url) is not str or not url or
            type(version) is not str or not version):
        _fail("invalid_source_context")
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            _fail("invalid_source_context")
    except ValueError:
        _fail("invalid_source_context")
    sections = source.sections if source.sections is not None else ["unknown"] * len(units)
    if (type(sections) not in (tuple, list) or len(sections) != len(units) or
            any(type(s) is not str or s not in SECTIONS for s in sections)):
        _fail("invalid_source_context")
    locations = set()
    manifest_units = []
    text_by_location = {}
    for unit, section in zip(units, sections):
        _keys(unit, ("location", "text"))
        location, text = unit["location"], unit["text"]
        if (type(location) is not str or LOCATION.fullmatch(location) is None or
                location in locations or type(text) is not str):
            _fail("invalid_source_units")
        locations.add(location)
        text_by_location[location] = text
        manifest_units.append({"location": location, "section": section,
            "characters": len(text), "text_sha256": _hash(text)})
    if not any(u["characters"] for u in manifest_units):
        _fail("empty_source_text")
    if type(source.chunks) is not list or not source.chunks:
        _fail("invalid_chunk_plan")
    # A strict ordered interval cursor rules out gaps, overlaps, duplicate ranges,
    # reordered units and invented separators. Zero-length units remain in the
    # manifest and review obligations, although they have no text chunk range.
    nonempty = [u for u in manifest_units if u["characters"]]
    unit_index = offset = 0
    manifest_chunks = []
    for n, chunk in enumerate(source.chunks, 1):
        _keys(chunk, ("id", "text", "ranges"))
        if chunk["id"] != f"C{n:04d}" or type(chunk["text"]) is not str:
            _fail("invalid_chunk_plan")
        ranges = chunk["ranges"]
        if type(ranges) is not list or not ranges:
            _fail("invalid_chunk_plan")
        parts = []
        for r in ranges:
            _keys(r, ("location", "start", "end"))
            if unit_index >= len(nonempty):
                _fail("invalid_interval_coverage")
            unit = nonempty[unit_index]
            if (r["location"] != unit["location"] or not _integer(r["start"]) or
                    not _integer(r["end"], 1) or r["start"] != offset or
                    not r["start"] < r["end"] <= unit["characters"]):
                _fail("invalid_interval_coverage")
            parts.append(text_by_location[r["location"]][r["start"]:r["end"]])
            offset = r["end"]
            if offset == unit["characters"]:
                unit_index += 1
                offset = 0
        if chunk["text"] != "\n".join(parts):
            _fail("chunk_text_mismatch")
        manifest_chunks.append({"id": chunk["id"], "text_sha256": _hash(chunk["text"]),
            "characters": len(chunk["text"]), "ranges": deepcopy(ranges)})
    if unit_index != len(nonempty) or offset:
        _fail("invalid_interval_coverage")
    raw = getattr(doc, "source_bytes", None)
    if raw is not None and type(raw) is not bytes:
        _fail("invalid_source_context")
    return {"source_id_sha256": _hash(source.source_id), "locator_sha256": _hash(url),
        "version_sha256": _hash(version), "policy_sha256": source.policy_sha256,
        "kind": source.kind, "provider": source.provider, "license_code": source.license_code,
        "source_bytes_sha256": sha256(raw).hexdigest() if raw is not None else None,
        "source_bytes_count": len(raw) if raw is not None else None,
        "source_text_sha256": _hash("\n".join(u["text"] for u in units)),
        "units": manifest_units, "chunks": manifest_chunks}


def _new_state(binding):
    return {"schema": SCHEMA, "revision": 0, "binding": binding,
        "checkpoints": [{"chunk_id": c["id"], "state": "pending", "error": None,
            "claims": []} for c in binding["chunks"]],
        "examined_units": [], "obligations": [], "cross_section_attested": False}


def _safe_claim_text(text):
    if type(text) is not str or not 6 <= len(text.split()) <= 90 or len(text) > 4000:
        return False
    normalized = unicodedata.normalize("NFKC", text)
    return (not any(unicodedata.category(c).startswith("C") for c in normalized) and
        not any("QUOTATION MARK" in unicodedata.name(c, "") and c not in "‘’" for c in normalized) and
        PRIVATE_TEXT.search(normalized) is None and SINGLE_QUOTATION.search(normalized) is None)


def _validate_state(state, binding):
    _keys(state, ("schema", "revision", "binding", "checkpoints", "examined_units",
                  "obligations", "cross_section_attested"))
    if (type(state["schema"]) is not int or state["schema"] != SCHEMA or
            not _integer(state["revision"]) or type(state["cross_section_attested"]) is not bool):
        _fail("invalid_ledger_schema")
    # Expected binding is independently reconstructed from the ephemeral source,
    # so an allowlisted saved manifest cannot override actual source coverage.
    if _canonical(state["binding"]) != _canonical(binding):
        _fail("source_binding_mismatch")
    checks = state["checkpoints"]
    if type(checks) is not list or len(checks) != len(binding["chunks"]):
        _fail("invalid_ledger_schema")
    for check, chunk in zip(checks, binding["chunks"]):
        _keys(check, ("chunk_id", "state", "error", "claims"))
        status = check["state"]
        if (check["chunk_id"] != chunk["id"] or type(status) is not str or
                status not in ("pending", "started", "checked", "failed", "interrupted") or
                type(check["claims"]) is not list or len(check["claims"]) > 6):
            _fail("invalid_ledger_schema")
        if status in ("failed", "interrupted"):
            if type(check["error"]) is not str or check["error"] not in FAILURES:
                _fail("invalid_ledger_schema")
        elif check["error"] is not None:
            _fail("invalid_ledger_schema")
        if status != "checked" and check["claims"]:
            _fail("invalid_ledger_schema")
        for claim in check["claims"]:
            _keys(claim, ("field", "text", "claim_sha256", "anchor_sha256", "source_span"))
            if (type(claim["field"]) is not str or claim["field"] not in reading.FIELDS[binding["kind"]] or
                    not _safe_claim_text(claim["text"]) or not _is_hash(claim["claim_sha256"]) or
                    _hash(claim["text"]) != claim["claim_sha256"] or not _is_hash(claim["anchor_sha256"]) or
                    type(claim["source_span"]) is not str or
                    re.fullmatch(re.escape(chunk["id"]) + r":S[0-9]{3,}", claim["source_span"]) is None):
                _fail("invalid_ledger_schema")
    locations = [u["location"] for u in binding["units"]]
    examined = state["examined_units"]
    if (type(examined) is not list or any(type(x) is not str or x not in locations for x in examined) or
            len(set(examined)) != len(examined)):
        _fail("invalid_ledger_schema")
    obligations = state["obligations"]
    if type(obligations) is not list:
        _fail("invalid_ledger_schema")
    ids = set()
    chunk_ids = [c["id"] for c in binding["chunks"]]
    for item in obligations:
        _keys(item, ("id", "kind", "origin_location", "affected_chunks", "resolution"))
        affected = item["affected_chunks"]
        if (type(item["kind"]) is not str or item["kind"] not in OBLIGATION_KINDS or
                type(item["origin_location"]) is not str or item["origin_location"] not in locations or
                type(affected) is not list or not affected or
                any(type(x) is not str or x not in chunk_ids for x in affected) or
                affected != sorted(set(affected)) or not _is_hash(item["id"]) or
                item["id"] != _digest({k: item[k] for k in ("kind", "origin_location", "affected_chunks")}) or
                item["id"] in ids or (item["resolution"] is not None and
                (type(item["resolution"]) is not str or item["resolution"] not in RESOLUTIONS))):
            _fail("invalid_ledger_schema")
        ids.add(item["id"])
    if (examined or any(x["resolution"] is not None for x in obligations)) and not _all_checked(state):
        _fail("invalid_ledger_schema")
    if state["cross_section_attested"] and not _review_prerequisites(state):
        _fail("invalid_ledger_schema")


def _all_checked(state):
    return all(c["state"] == "checked" for c in state["checkpoints"])


def _review_prerequisites(state):
    return (_all_checked(state) and len(state["examined_units"]) == len(state["binding"]["units"]) and
            all(o["resolution"] is not None for o in state["obligations"]))


def _copy_tokens(text):
    # Punctuation, Unicode width and case are not original wording. Keep digits
    # and non-Latin words too; this is intentionally stricter than the legacy
    # ASCII-only copy guard, which still runs unchanged separately.
    return re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold())


def _token_subsequence(needle, haystack):
    return bool(needle) and any(haystack[i:i + len(needle)] == needle
        for i in range(len(haystack) - len(needle) + 1))


def _longest_run(positions):
    longest = run = 0
    previous = -2
    for position in sorted(positions):
        run = run + 1 if position == previous + 1 else 1
        longest = max(longest, run)
        previous = position
    return longest


def _check_fragment_copy(texts, source_text):
    """Conservative lexical safeguards, NOT a semantic/originality detector.

    Four-token matches seed overlap coverage. Reject long individual fragments,
    mostly copied claims, and thirteen source tokens reconstructed across claims
    even when each fragment has a different prose wrapper. Source-position union
    prevents wrapper boundaries from resetting the aggregate copying check.
    Common short phrases can cause deferral; independent review is still needed.
    """
    source_words = _copy_tokens(source_text)
    candidates = [_copy_tokens(text) for text in texts]
    # Store only proposed phrases and union each matching source position once.
    # Repeated claims must not multiply work on a repetitive long source.
    proposed = {tuple(words[i:i + 4]) for words in candidates for i in range(len(words) - 3)}
    matched = set()
    source_covered = set()
    for i in range(len(source_words) - 3):
        key = tuple(source_words[i:i + 4])
        if key in proposed:
            matched.add(key)
            source_covered.update(range(i, i + 4))
    matched_total = token_total = 0
    for words in candidates:
        covered = set()
        for i in range(len(words) - 3):
            if tuple(words[i:i + 4]) in matched:
                covered.update(range(i, i + 4))
        if _longest_run(covered) >= 8 or (len(covered) >= 6 and len(covered) * 2 >= len(words)):
            _fail("privacy_check_failed")
        matched_total += len(covered)
        token_total += len(words)
    if (_longest_run(source_covered) >= 13 or
            (matched_total >= 13 and matched_total * 2 >= token_total)):
        _fail("privacy_check_failed")


def _claim_records(source, chunk, claims):
    if type(claims) is not list or len(claims) > 6:
        _fail("invalid_checked_claims")
    spans = reading.source_spans(chunk)
    by_text = {}
    for span in spans:
        by_text.setdefault(reading.normalize(span["text"]), []).append(span)
    full_text = "\n".join(u["text"] for u in source.document.units)
    full_words = _copy_tokens(full_text)
    records = []
    for claim in claims:
        if type(claim) is not dict or set(claim) != {"field", "text", "quote"}:
            _fail("invalid_checked_claims")
        # Reuse the existing literal anchor, number and 13-word copy gates.
        reading.validate_claim(claim, chunk, source.kind)
        text, anchor = claim["text"], claim["quote"]
        matches = by_text.get(reading.normalize(anchor), [])
        if not matches:
            _fail("claim_anchor_invalid")
        if len(matches) != 1:
            _fail("ambiguous_claim_anchor")
        span = matches[0]
        if (not _safe_claim_text(text) or _token_subsequence(_copy_tokens(text), full_words) or
                reading.normalize(anchor) in reading.normalize(text) or
                reading.has_copied_sequence({"text": text}, full_text, span=13)):
            _fail("privacy_check_failed")
        records.append({"field": claim["field"], "text": text, "claim_sha256": _hash(text),
            "anchor_sha256": _hash(reading.normalize(anchor)), "source_span": span["id"]})
    return records


def _revalidate_saved_claims(state, source):
    """Resume rechecks even short copied text, source-span hashes and aggregate copy.

    Replaying the verifier would change the completed work rather than validate
    its storage. The unchanged policy and recorded successful gate are required.
    """
    all_text = "\n".join(u["text"] for u in source.document.units)
    accumulated = []
    for checkpoint, chunk in zip(state["checkpoints"], source.chunks):
        if checkpoint["state"] != "checked":
            continue
        by_id = {s["id"]: s for s in reading.source_spans(chunk)}
        ephemeral = []
        for saved in checkpoint["claims"]:
            span = by_id.get(saved["source_span"])
            if span is None or _hash(reading.normalize(span["text"])) != saved["anchor_sha256"]:
                _fail("invalid_checked_claims")
            ephemeral.append({"field": saved["field"], "text": saved["text"],
                              "quote": " ".join(span["text"].split())})
        if _claim_records(source, chunk, ephemeral) != checkpoint["claims"]:
            _fail("invalid_checked_claims")
        accumulated.extend(c["text"] for c in checkpoint["claims"])
    if reading.has_copied_sequence({"text": " ".join(accumulated)}, all_text, span=13):
        _fail("privacy_check_failed")
    _check_fragment_copy(accumulated, all_text)


def _file_stat(fd):
    s = os.fstat(fd)
    if (not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode) != 0o600 or
            s.st_uid != os.getuid() or s.st_nlink != 1):
        _fail("unsafe_ledger_file")
    return s


def _open_directory(path, create):
    """Walk using no-follow dirfds, rejecting checkout paths and all symlinks."""
    if (not path.is_absolute() or ".." in path.parts or path == Path("/") or
            path == ROOT or ROOT in path.parents):
        _fail("private_path_required")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            # A git worktree may use a .git FILE; either form is prohibited.
            if _repository_marker(fd):
                _fail("repository_path_forbidden")
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    _fail("private_directory_missing")
                os.mkdir(part, 0o700, dir_fd=fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        if _repository_marker(fd):
            _fail("repository_path_forbidden")
        s = os.fstat(fd)
        if s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
            _fail("private_directory_permissions_required")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _repository_marker(fd):
    if _exists(fd, ".source-snapshot"):
        return True
    try:
        marker = os.stat(".git", dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    # Empty sandbox permission-marker directories are not Git repositories.
    # Files cover worktrees, symlinks fail closed, and HEAD covers real checkouts.
    return not stat.S_ISDIR(marker.st_mode) or _exists(fd, ".git/HEAD")


def _exists(fd, name):
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _unique_object(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            _fail("invalid_ledger_json")
        result[k] = v
    return result


class EvidenceLedger:
    """One exact source/policy/plan per private directory. Use ``open`` to resume.

    No stale-object merging: after another writer changes the ledger, reopen it.
    Never use a new directory to launder a rejected claim into accepted state.
    A source/policy change is separate work requiring fresh review, not a retry.
    """
    def __init__(self, directory, fd, state):
        self.directory, self._fd, self._state = directory, fd, state
        self._poisoned = False

    @classmethod
    def open(cls, private_directory, source):
        binding = _capture(source)
        path = Path(private_directory)
        fd = None
        ledger = None
        try:
            fd = _open_directory(path, True)
            ledger = cls(path, fd, _new_state(binding))
            prior_entries = os.listdir(fd)
            with ledger._locked():
                if _exists(fd, "ledger.json"):
                    state = ledger._read(binding)
                    _revalidate_saved_claims(state, source)
                    ledger._state = state
                    # A lost process cannot tell us whether its reader completed.
                    # Preserve uncertainty and do not auto-retry the chunk.
                    if any(c["state"] == "started" for c in state["checkpoints"]):
                        state = deepcopy(state)
                        for c in state["checkpoints"]:
                            if c["state"] == "started":
                                c.update(state="interrupted", error="interrupted_or_uncertain")
                        ledger._commit(state)
                else:
                    if prior_entries:
                        _fail("ledger_state_missing")
                    ledger._commit(ledger._state)
                ledger._discard_pending()
            return ledger
        except OSError:
            if fd is not None:
                os.close(fd)
            _fail("private_storage_unavailable")
        except BaseException:
            if fd is not None:
                os.close(fd)
            raise

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @contextmanager
    def _locked(self):
        if self._fd is None or self._poisoned:
            _fail("ledger_reopen_required")
        lock = fresh = None
        try:
            fresh = _open_directory(self.directory, False)
            if (os.fstat(fresh).st_dev, os.fstat(fresh).st_ino) != (
                    os.fstat(self._fd).st_dev, os.fstat(self._fd).st_ino):
                _fail("private_directory_replaced")
            lock = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=self._fd)
            _file_stat(lock)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                _fail("ledger_busy")
            yield
        except OSError:
            _fail("private_storage_unavailable")
        finally:
            if lock is not None:
                os.close(lock)
            if fresh is not None:
                os.close(fresh)

    def _read(self, binding):
        fd = os.open("ledger.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self._fd)
        try:
            info = _file_stat(fd)
            if info.st_size > MAX_FILE_BYTES:
                _fail("ledger_capacity_exceeded")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                _fail("ledger_capacity_exceeded")
            try:
                envelope = json.loads(raw, object_pairs_hook=_unique_object,
                    parse_constant=lambda _: _fail("invalid_ledger_json"))
            except (UnicodeError, json.JSONDecodeError, RecursionError):
                _fail("invalid_ledger_json")
            _keys(envelope, ("payload", "sha256"))
            if not _is_hash(envelope["sha256"]) or _digest(envelope["payload"]) != envelope["sha256"]:
                _fail("ledger_checksum_mismatch")
            _validate_state(envelope["payload"], binding)
            return envelope["payload"]
        finally:
            os.close(fd)

    def _commit(self, state):
        state = deepcopy(state)
        state["revision"] += 1
        _validate_state(state, self._state["binding"])
        raw = _canonical({"payload": state, "sha256": _digest(state)}) + b"\n"
        if len(raw) > MAX_FILE_BYTES:
            _fail("ledger_capacity_exceeded")
        name = ".pending-" + uuid4().hex
        fd = None
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self._fd)
            _file_stat(fd)
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(fd)
            os.close(fd)
            fd = None
            os.replace(name, "ledger.json", src_dir_fd=self._fd, dst_dir_fd=self._fd)
            os.fsync(self._fd)
            self._state = state
        except OSError:
            self._poisoned = True
            _fail("ledger_write_uncertain")
        finally:
            if fd is not None:
                os.close(fd)
            # Incomplete files contain only the same allowlisted private payload.
            # If interrupted before replace, resume uses the last committed file.
            try:
                os.unlink(name, dir_fd=self._fd)
            except FileNotFoundError:
                pass
            except OSError:
                self._poisoned = True

    def _discard_pending(self):
        for name in os.listdir(self._fd):
            if re.fullmatch(r"\.pending-[0-9a-f]{32}", name):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self._fd)
                try:
                    _file_stat(fd)
                finally:
                    os.close(fd)
                os.unlink(name, dir_fd=self._fd)
        os.fsync(self._fd)

    @contextmanager
    def _transaction(self, source):
        binding = _capture(source)
        if binding != self._state["binding"]:
            _fail("source_binding_mismatch")
        with self._locked():
            state = self._read(binding)
            if state != self._state:
                _fail("ledger_concurrent_update")
            _revalidate_saved_claims(state, source)
            yield deepcopy(state)

    def _checkpoint(self, state, chunk_id):
        for check in state["checkpoints"]:
            if check["chunk_id"] == chunk_id:
                return check
        _fail("unknown_chunk")

    def run_chunk(self, source, chunk_id, *, model, title, deadline=None):
        """Run the existing final reader gate once, or return its saved claims.

        No caller-supplied success flag/verdict can create a checkpoint. A reader
        exception persists a controlled failure; interrupts persist uncertainty.
        The full batch is rejected on any validation failure: no subset salvage.
        """
        with self._transaction(source) as state:
            check = self._checkpoint(state, chunk_id)
            if check["state"] == "checked":
                return deepcopy(check["claims"])
            if check["state"] != "pending":
                _fail("chunk_unresolved_no_automatic_retry")
            chunk = deepcopy(next(c for c in source.chunks if c["id"] == chunk_id))
            check["state"] = "started"
            self._commit(state)
            state = deepcopy(self._state)
            check = self._checkpoint(state, chunk_id)
            try:
                claims = reading.read_chunk(model, chunk, source.kind, title, deadline=deadline)
                if _capture(source) != state["binding"]:
                    _fail("source_binding_mismatch")
                check.update(state="checked", claims=_claim_records(source, chunk, claims))
                _revalidate_saved_claims(state, source)
            except BaseException as exc:
                # Do not stringify arbitrary exceptions. Known ValueError codes
                # are allowed only when they exactly match a controlled enum.
                code = exc.args[0] if type(exc) in (ValueError, LedgerError, reading.ModelFormatError) and len(exc.args) == 1 else None
                interrupted = not isinstance(exc, Exception)
                code = "interrupted_or_uncertain" if interrupted else code if type(code) is str and code in FAILURES else "reader_failed"
                check.update(state="interrupted" if interrupted else "failed", error=code, claims=[])
                self._commit(state)
                if isinstance(exc, KeyboardInterrupt):
                    raise KeyboardInterrupt from None
                if isinstance(exc, SystemExit):
                    raise SystemExit(130) from None
                raise LedgerError(code) from None
            self._commit(state)
            return deepcopy(check["claims"])

    def _snapshot(self):
        with self._locked():
            state = self._read(self._state["binding"])
            if state != self._state:
                _fail("ledger_concurrent_update")
            return state

    def claims_for(self, chunk_id):
        """Return private saved paraphrases, never a public synthesis or quote."""
        check = self._checkpoint(self._snapshot(), chunk_id)
        if check["state"] != "checked":
            _fail("chunk_not_checked")
        return deepcopy(check["claims"])

    def status(self):
        state = self._snapshot()
        checked = {c["chunk_id"] for c in state["checkpoints"] if c["state"] == "checked"}
        return {"revision": state["revision"], "source_binding_sha256": _digest(state["binding"]),
            "source_text_saved": False, "claims_saved": "validated_original_paraphrases",
            "retrieved_interval_plan_complete": True,
            "all_retrieved_text_processed": _all_checked(state),
            "whole_article_coverage": "not_established", "semantic_completeness": "not_verified",
            "per_chunk_machine_checks": [{"chunk_id": c["chunk_id"], "state": c["state"],
                "error": c["error"], "claim_count": len(c["claims"])} for c in state["checkpoints"]],
            "processed_intervals": [deepcopy(r) for c in state["binding"]["chunks"] if c["id"] in checked for r in c["ranges"]],
            "units": deepcopy(state["binding"]["units"]),
            "unexamined_units": [u["location"] for u in state["binding"]["units"] if u["location"] not in state["examined_units"]],
            "unresolved_obligations": [deepcopy(o) for o in state["obligations"] if o["resolution"] is None],
            "cross_section_review": "attested_not_verified" if state["cross_section_attested"] else "pending",
            "independent_review": "pending"}

    def examine_unit(self, source, location, *, caveats_checked, contradictions_checked):
        """Attest both scans against all completed claims, including later units."""
        with self._transaction(source) as state:
            if not _all_checked(state):
                _fail("retrieved_text_processing_pending")
            if caveats_checked is not True or contradictions_checked is not True:
                _fail("unit_review_incomplete")
            if location not in [u["location"] for u in state["binding"]["units"]]:
                _fail("unknown_source_unit")
            if location not in state["examined_units"]:
                state["examined_units"].append(location)
                self._commit(state)

    def add_obligation(self, source, *, kind, origin_location, affected_chunks):
        with self._transaction(source) as state:
            if (type(kind) is not str or kind not in OBLIGATION_KINDS or
                    type(origin_location) is not str or origin_location not in [u["location"] for u in state["binding"]["units"]] or
                    type(affected_chunks) is not list or not affected_chunks or
                    any(type(x) is not str or x not in [c["chunk_id"] for c in state["checkpoints"]] for x in affected_chunks) or
                    len(set(affected_chunks)) != len(affected_chunks)):
                _fail("invalid_obligation")
            item = {"kind": kind, "origin_location": origin_location, "affected_chunks": sorted(affected_chunks)}
            ident = _digest(item)
            if not any(o["id"] == ident for o in state["obligations"]):
                state["obligations"].append({**item, "id": ident, "resolution": None})
                state["cross_section_attested"] = False
                self._commit(state)
            return ident

    def resolve_obligation(self, source, obligation_id, *, resolution):
        """Record an external review disposition, not a checked semantic fact.

        If claims require revision, leave the obligation unresolved. There is no
        in-place rewriting or accepted-subset promotion API.
        """
        with self._transaction(source) as state:
            if not _review_prerequisites({**state, "obligations": []}):
                _fail("source_unit_review_pending")
            if type(resolution) is not str or resolution not in RESOLUTIONS:
                _fail("invalid_obligation_resolution")
            item = next((o for o in state["obligations"] if o["id"] == obligation_id), None)
            if item is None:
                _fail("unknown_obligation")
            if item["resolution"] is not None and item["resolution"] != resolution:
                _fail("obligation_resolution_conflict")
            if item["resolution"] is None:
                item["resolution"] = resolution
                state["cross_section_attested"] = False
                self._commit(state)

    def attest_cross_section_review(self, source):
        with self._transaction(source) as state:
            if not _review_prerequisites(state):
                _fail("cross_section_obligations_pending")
            if not state["cross_section_attested"]:
                state["cross_section_attested"] = True
                self._commit(state)

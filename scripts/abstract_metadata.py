"""Bounded provider abstracts, never a claim to have read a complete paper.

``provider_text_preserved`` means only that all supplied abstract text survived
ingestion. Providers may themselves supply incomplete abstracts. Missing legacy
completeness metadata is unknown, not evidence of completeness.
"""
import re

MAX_ABSTRACT_CHARS = 6000
ABSTRACT_FIELDS = ("abstract_text", "abstract_source", "abstract_completeness", "preview")
COMPLETENESS = {"provider_text_preserved", "truncated", "invalid_provider_index", "unavailable", "unknown"}


def abstract_record(text, source, *, completeness=None):
    """Keep a bounded abstract separately from its 420-character preview."""
    text = " ".join(text.split()) if isinstance(text, str) else ""
    status = completeness or ("provider_text_preserved" if text else "unavailable")
    if len(text) > MAX_ABSTRACT_CHARS:
        status = "truncated"
    retained = text[:MAX_ABSTRACT_CHARS].rstrip()
    label = source if retained else ""
    if status == "truncated":
        label += f" (truncated at {MAX_ABSTRACT_CHARS:,} characters)"
    elif status == "unknown" and retained:
        label += " (provider-text completeness unknown)"
    return {"abstract_text": retained, "abstract_source": label,
            "abstract_completeness": status,
            "preview": retained[:420] + ("…" if len(retained) > 420 else "")
                       if retained else "Abstract unavailable; bibliographic metadata only."}


def crossref_abstract(text, *, completeness=None):
    return abstract_record(re.sub(r"<[^>]+>", " ", text or ""),
                           "Crossref publisher-supplied abstract", completeness=completeness)


def openalex_abstract(index, *, completeness=None):
    """Reconstruct an unambiguous index without allocating by its largest offset.

    Repeated identical positions are harmless; conflicting words, gaps and
    malformed entries cannot be joined into invented sentences. Retain only
    positions needed for the character cap plus an overflow character. Even
    one-character tokens exceed that cap before this positional window ends.
    """
    source = "OpenAlex abstract index"
    if index is None or index == {}:
        return abstract_record("", source, completeness=completeness)

    def invalid():
        return abstract_record("", source, completeness="invalid_provider_index")

    if not isinstance(index, dict):
        return invalid()
    positions = {}
    has_tail = False
    for word, offsets in index.items():
        if (not isinstance(word, str) or not word.strip()
                or not isinstance(offsets, (list, tuple)) or not offsets):
            return invalid()
        for offset in offsets:
            if type(offset) is not int or offset < 0:
                return invalid()
            if offset > MAX_ABSTRACT_CHARS:
                has_tail = True
                continue
            if offset in positions and positions[offset] != word:
                return invalid()
            positions[offset] = word
    last = max(positions, default=-1)
    if last < 0 or len(positions) != last + 1 or (has_tail and last < MAX_ABSTRACT_CHARS):
        return invalid()
    chunks = []
    remaining = MAX_ABSTRACT_CHARS + 1
    for offset in range(last + 1):
        word = " ".join(positions[offset].split())
        piece = (" " if offset else "") + word
        chunks.append(piece[:remaining])
        remaining -= len(chunks[-1])
        if remaining == 0:
            break
    # The extra character can be a space. Remember overflow before whitespace
    # normalization so an abstract ending exactly at the cap cannot appear
    # complete merely because its next word was omitted.
    return abstract_record("".join(chunks), source,
                           completeness="truncated" if remaining == 0 else completeness)


def merge_abstract(current, incoming):
    """Upgrade text and its provenance together, preserving unrelated analysis."""
    before = current.get("abstract_text") or ""
    after = incoming.get("abstract_text") or ""
    # A replay can annotate identical legacy text, but cannot silently replace
    # a longer source or relabel different text of the same length.
    prior_status = current.get("abstract_completeness")
    next_status = incoming.get("abstract_completeness")
    annotate = (after and after == before and next_status
                and (not prior_status or (prior_status == "unknown" and next_status != "unknown")))
    if len(after) <= len(before) and not annotate:
        return False
    for field in ABSTRACT_FIELDS:
        if field in incoming:
            current[field] = incoming[field]
        else:
            current.pop(field, None)
    return True

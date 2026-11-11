"""Closed schemas for private machine notes, not proof of semantic review.

Only generated paraphrases and bounded provenance may survive preparation.
An integrity hash cannot authorize extra fields, source bodies or approval.
These validators do no retrieval, inference, writes or publication.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from enrich_deep_readings import FIELDS

ERROR = "invalid_prepared_reading_fields"
REVIEW = "machine_checked_not_independently_reviewed"
CHECK = "anchor_numeric_copy_and_second_model_pass"
ENRICHMENT = {"deep_analysis", "partial_reading_candidate", "reading_coverage",
              "complete_reading_attempt"}
STAGED_FIELDS = ENRICHMENT | {
    "source_review", "original_reading", "reading", "analysis", "approved",
    "approval", "publication", "review", "source_checked", "public_eligible",
    "raw_source", "raw_source_text", "source_text", "source_body", "document",
    "raw_document", "document_text", "source_html", "source_pdf", "source_text_saved",
    "source_bytes", "fulltext", "full_text", "original_reading_sha256",
}
FALSE_FLAGS = {"source_text_saved", "tables_figures_visually_checked", "supplements_checked"}
COVERAGE_REQUIRED = FALSE_FLAGS | {
    "source_url", "document_version", "source_sha256", "characters_retrieved",
    "units_retrieved", "retrieved_at", "evidence_status", "chunks_total",
    "chunks_processed", "all_retrieved_text_processed", "empty_claim_chunks",
    "claims_checked", "claim_check", "review_status",
}
COVERAGE_OPTIONAL = {
    "source_bytes_sha256", "source_byte_count", "pages_total", "pages_processed",
    "pages_with_text", "layout_fidelity", "semantic_completeness", "document_format",
    "structured_text_coverage", "source_document_equivalence", "rights_basis",
    "redistribution_granted", "html_completeness", "html_body_selection",
    "html_extraction_version", "html_blocks_extracted", "html_list_items_found",
    "upstream_truncation_possible", "identity_verification", "identity_verification_url",
    "record_doi", "source_doi", "document_title", "source_relation", "retrieval_provider",
    "reported_license", "discovery_basis", "declared_link_purpose", "declared_content_type",
    "acquisition_state_sha256", "acquisition_input_fingerprint", "acquisition_receipt_status",
}
LOCATION = re.compile(
    r"(?:page:[1-9]\d*|paragraph:[1-9]\d*|indexed_section:(?:methods|results|discussion|limitations)"
    r"|xml:[a-z][a-z0-9_.-]*(?:/(?:[a-z][a-z0-9_.-]*:[1-9]\d*|text|tail))*)"
)


def require(condition):
    if not condition:
        raise ValueError(ERROR)


def shape(value, required, optional=()):
    require(type(value) is dict and required <= set(value) <= required | set(optional))


def text(value, maximum=2000, empty=False):
    require(type(value) is str and len(value) <= maximum and (empty or bool(value.strip()))
            and not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value))


def integer(value, maximum=100_000_000, minimum=0):
    require(type(value) is int and minimum <= value <= maximum)


def hashed(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None)


def moment(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(isinstance(value, datetime) and value.tzinfo is not None)
    return value.astimezone(timezone.utc)


def saved_moment(value):
    require(type(value) is str)
    return moment(value)


def day(value):
    require(type(value) is str and len(value) == 10)
    result = date.fromisoformat(value)
    require(result.isoformat() == value)
    return result


def url(value, empty=False):
    text(value, 4000, empty=empty)
    if empty and not value:
        return
    parts = urlsplit(value)
    require(parts.scheme == "https" and bool(parts.hostname) and not parts.username
            and not parts.password and parts.port in (None, 443) and not parts.query
            and not parts.fragment and not re.search(r"\s|\\", value))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode()).hexdigest()


def validate_coverage(value):
    shape(value, COVERAGE_REQUIRED, COVERAGE_OPTIONAL)
    for field in FALSE_FLAGS | ({"redistribution_granted"} & set(value)):
        require(value[field] is False)
    require(value["all_retrieved_text_processed"] is True
            and value["review_status"] == REVIEW and value["claim_check"] == CHECK
            and value["evidence_status"] in {"full_document_retrieved", "partial_full_text"})
    url(value["source_url"])
    text(value["document_version"], 100)
    require(re.fullmatch(r"[A-Za-z0-9_.:-]+", value["document_version"]) is not None)
    hashed(value["source_sha256"])
    # A live fetch finishes after its run's captured `now`; the precise actual
    # timestamp is retained, not compared to that earlier start time.
    saved_moment(value["retrieved_at"])
    for key in ("characters_retrieved", "units_retrieved", "claims_checked"):
        integer(value[key], minimum=1)
    integer(value["chunks_total"], maximum=80, minimum=1)
    integer(value["chunks_processed"], maximum=80, minimum=1)
    require(value["chunks_total"] == value["chunks_processed"])
    empty = value["empty_claim_chunks"]
    require(type(empty) is list and all(type(key) is str for key in empty)
            and empty == sorted(set(empty)))
    chunks = {f"C{number:04d}" for number in range(1, value["chunks_total"] + 1)}
    require(set(empty) <= chunks)
    for key in ("semantic_completeness", "layout_fidelity", "source_document_equivalence", "html_completeness"):
        if key in value:
            require(value[key] == "not_verified")
    if "upstream_truncation_possible" in value:
        require(value["upstream_truncation_possible"] is True
                and value["evidence_status"] == "partial_full_text")
    byte_fields = {"source_bytes_sha256", "source_byte_count"}
    if byte_fields & set(value):
        require(byte_fields <= set(value))
        hashed(value["source_bytes_sha256"])
        integer(value["source_byte_count"], maximum=20_000_000, minimum=1)
    pages = {"pages_total", "pages_processed", "pages_with_text"}
    if pages & set(value):
        require(pages <= set(value))
        for key in pages:
            integer(value[key], maximum=300)
        require(value["pages_total"] >= value["pages_processed"] == value["units_retrieved"]
                >= value["pages_with_text"] > 0)
        if value["evidence_status"] == "full_document_retrieved":
            require(value["pages_total"] == value["pages_with_text"])
    if "document_format" in value:
        require(value["document_format"] in {"jats", "tei"}
                and value.get("structured_text_coverage") == "all_text_in_supplied_article_xml"
                and value.get("source_document_equivalence") == "not_verified")
    if "structured_text_coverage" in value:
        require(value.get("document_format") in {"jats", "tei"})
    if "rights_basis" in value:
        require(value["rights_basis"] in {"article_metadata_permissive_license",
                                           "provider_reported_oa_transient_reading_only"})
    html = {"html_completeness", "html_body_selection", "html_extraction_version",
            "html_blocks_extracted", "html_list_items_found"}
    if html & set(value):
        require(value["evidence_status"] == "partial_full_text" and not (pages & set(value))
                and "document_format" not in value)
    if "html_extraction_version" in value:
        require(type(value["html_extraction_version"]) is str and
                re.fullmatch(r"article-body-v[1-9]\d*", value["html_extraction_version"]) is not None)
    if "html_body_selection" in value:
        require(value["html_body_selection"] in {"article", "full_article", "main",
            "article:explicit_body", "full_article:explicit_body", "main:explicit_body"})
    for key in ("html_blocks_extracted", "html_list_items_found"):
        if key in value:
            integer(value[key])
    for key in ("record_doi", "source_doi"):
        if key in value:
            text(value[key], 1000, empty=True)
            require(not value[key] or re.fullmatch(r"10\.\d{4,9}/\S+", value[key], re.I) is not None)
    if "identity_verification" in value:
        require(value["identity_verification"] == "arxiv_related_doi_title_and_identifier")
    if "identity_verification_url" in value:
        url(value["identity_verification_url"])
    if "source_relation" in value:
        require(value["source_relation"] == "related_preprint")
    for key in ("document_title", "retrieval_provider", "discovery_basis",
                "declared_link_purpose", "declared_content_type"):
        if key in value:
            text(value[key], 2000 if key == "document_title" else 200, empty=key == "document_title")
    if value.get("reported_license") is not None:
        text(value["reported_license"], 1000)
    receipt = {"acquisition_state_sha256", "acquisition_input_fingerprint", "acquisition_receipt_status"}
    if receipt & set(value):
        require(receipt <= set(value) and value["acquisition_receipt_status"] == "revalidated_not_reviewed")
        hashed(value["acquisition_state_sha256"])
        hashed(value["acquisition_input_fingerprint"])
    return value


def validate_analysis(value, *, kind=None, now=None):
    """Validate what the chunk reader actually saves, without claiming truth."""
    now = moment(now)
    require(type(value) is dict and value.get("kind") in FIELDS)
    actual_kind = value["kind"]
    require(kind is None or actual_kind == kind)
    required = set(FIELDS[actual_kind]) | {"claim_evidence", "coverage", "version", "kind",
        "source_depth", "source_url", "source_hash", "model", "basis", "review_status", "created_at"}
    shape(value, required, {"preparation_provenance"})
    require(type(value["version"]) is int and value["version"] == 3 and value["review_status"] == REVIEW)
    coverage = validate_coverage(value["coverage"])
    require(value["source_url"] == coverage["source_url"] and value["source_hash"] == coverage["source_sha256"])
    complete = coverage["evidence_status"] == "full_document_retrieved"
    depth = (("full_text" if complete else "partial_full_text") if actual_kind == "scholarly"
             else ("source_html" if complete else "partial_source_html"))
    require(value["source_depth"] == depth and day(value["created_at"]) <= now.date())
    require(value["model"] == "Qwen2.5-1.5B-Instruct (on-runner; chunked with claim checking)")
    basis = ("Every retrieved text chunk processed; claim-level machine checks. "
             "Not independently reviewed. Figures, tables and supplements not visually verified. "
             + (("All supplied article XML text retrieved; equivalence to the original PDF is not verified."
                if coverage.get("document_format") in ("jats", "tei") else "Whole PDF text retrieved.")
                if complete else "Partial source coverage; not a whole-article review."))
    require(value["basis"] == basis)
    claims = value["claim_evidence"]
    require(type(claims) is list and 0 < len(claims) <= 10000 and len(claims) == coverage["claims_checked"])
    fields = {field: [] for field in FIELDS[actual_kind]}
    known_chunks = {f"C{number:04d}" for number in range(1, coverage["chunks_total"] + 1)}
    seen = set(); ranges_by_chunk = {}
    for claim in claims:
        shape(claim, {"field", "text", "chunk_id", "locations", "evidence_anchor_sha256"})
        require(claim["field"] in fields and claim["chunk_id"] in known_chunks
                and claim["chunk_id"] not in coverage["empty_claim_chunks"])
        text(claim["text"], 20000)
        require(6 <= len(claim["text"].split()) <= 90)
        identity = (claim["field"], " ".join(claim["text"].lower().split()))
        require(identity not in seen); seen.add(identity)
        hashed(claim["evidence_anchor_sha256"])
        locations = claim["locations"]
        require(type(locations) is list and 0 < len(locations) <= 5500)
        size = 0; location_ends = {}
        for span in locations:
            shape(span, {"location", "start", "end"})
            text(span["location"], 2000)
            require(LOCATION.fullmatch(span["location"]) is not None)
            integer(span["start"]); integer(span["end"])
            require(span["start"] < span["end"] <= coverage["characters_retrieved"])
            require(span["start"] >= location_ends.get(span["location"], 0))
            location_ends[span["location"]] = span["end"]
            size += span["end"] - span["start"]
        require(size + len(locations) - 1 <= 5500 and len(location_ends) <= coverage["units_retrieved"])
        if claim["chunk_id"] in ranges_by_chunk:
            require(ranges_by_chunk[claim["chunk_id"]] == locations)
        ranges_by_chunk[claim["chunk_id"]] = locations
        fields[claim["field"]].append(claim["text"])
    # Claims may omit empty/deduplicated chunks. Do not invent full interval
    # evidence absent from the saved reader output, but reject overlapping ones.
    ends = {}
    for chunk in sorted(ranges_by_chunk):
        for span in ranges_by_chunk[chunk]:
            require(span["start"] >= ends.get(span["location"], 0))
            ends[span["location"]] = span["end"]
    for field, parts in fields.items():
        require(value[field] == " ".join(parts))
    if "preparation_provenance" in value:
        proof = value["preparation_provenance"]
        shape(proof, {"publication_window", "source_revalidated_at", "independently_approved"})
        require(proof["independently_approved"] is False)
        window = proof["publication_window"]
        shape(window, {"from", "to", "timezone"})
        start, end = day(window["from"]), day(window["to"])
        checked = saved_moment(proof["source_revalidated_at"])
        require(window["timezone"] == "UTC" and start.weekday() == 0 and (end-start).days == 6
                and end < checked.date() and checked <= now)
    return value


def validate_diagnostics(values):
    require(type(values) is list and len(values) <= 10000)
    optional = {"stage", "provider", "url", "final_url", "failure_url", "candidates", "candidates_retained",
                "candidates_attempted", "retry_after_seconds", "network_attempted"}
    for entry in values:
        shape(entry, {"status", "retryable"}, optional)
        require(type(entry["status"]) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,100}", entry["status"]))
        require(type(entry["retryable"]) is bool)
        if "stage" in entry:
            require(entry["stage"] in {"article", "discovery", "retrieval", "handoff"})
        if "provider" in entry:
            text(entry["provider"], 200)
        if "network_attempted" in entry:
            require(type(entry["network_attempted"]) is bool)
        for key in ("url", "final_url", "failure_url"):
            if key in entry:
                url(entry[key], empty=True)
        for key in ("candidates", "candidates_retained", "candidates_attempted", "retry_after_seconds"):
            if key in entry:
                integer(entry[key])


def validate_saved_record(record, now=None):
    """Validate enrichment only; the caller validates the article's identity."""
    try:
        now = moment(now)
        require(type(record) is dict and record.get("kind") in FIELDS)
        require(not (set(record) & (STAGED_FIELDS - ENRICHMENT)))
        analyses = []
        for key in ("deep_analysis", "partial_reading_candidate"):
            if key in record:
                analyses.append(validate_analysis(record[key], kind=record["kind"], now=now))
        if "partial_reading_candidate" in record:
            require("deep_analysis" in record
                    and record["partial_reading_candidate"]["coverage"]["evidence_status"] == "partial_full_text")
        if "reading_coverage" in record:
            validate_coverage(record["reading_coverage"])
            require(any(record["reading_coverage"] == analysis["coverage"] for analysis in analyses))
        if analyses:
            require("reading_coverage" in record and "complete_reading_attempt" in record)
        if "complete_reading_attempt" in record:
            attempt = record["complete_reading_attempt"]
            shape(attempt, {"status", "last_at", "next_at", "provider_diagnostics"}, {"stage","retry_after","format_failures"})
            require(type(attempt["status"]) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,100}", attempt["status"]))
            last, next_at = day(attempt["last_at"]), day(attempt["next_at"])
            require(last <= now.date() and next_at > last)
            if 'format_failures' in attempt:
                integer(attempt['format_failures'],maximum=1000,minimum=1)
                require(attempt.get('stage')=='synthesis' and attempt['status'] in {
                    'model_json_invalid','model_schema_invalid','model_output_truncated',
                    'verifier_indices_invalid','verifier_schema_invalid',
                    'verifier_output_truncated','verifier_output_incomplete'})
            if 'retry_after' in attempt:
                retry=saved_moment(attempt['retry_after'])
                require(1<=attempt.get('format_failures',0)<=2 and last<=retry.date()<=next_at)
            validate_diagnostics(attempt["provider_diagnostics"])
            if attempt["status"] in {"summarized", "partial_summary"}:
                require(analyses and "stage" not in attempt)
                expected = "full_document_retrieved" if attempt["status"] == "summarized" else "partial_full_text"
                require(record["reading_coverage"]["evidence_status"] == expected
                        and any(analysis["created_at"] == attempt["last_at"] and
                            analysis["coverage"] == record["reading_coverage"] for analysis in analyses))
            else:
                require(attempt.get("stage") in {"retrieval", "synthesis"})
        return record
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError, RecursionError):
        raise ValueError(ERROR) from None


def validate_revalidation(value, deep, input_fingerprint, now=None):
    """Bind the source recheck to these notes; never create review approval."""
    try:
        now = moment(now)
        validate_analysis(deep, now=now); hashed(input_fingerprint)
        shape(value, {"basis", "checked_at", "status", "approved"}, {"reason", "source_sha256", "document_version"})
        require(value["approved"] is False and value["status"] in {"held", "source_revalidated"})
        require(value["basis"] == digest({"input": input_fingerprint, "analysis": deep}))
        checked = saved_moment(value["checked_at"])
        require(checked <= now and checked.date() >= day(deep["created_at"]))
        if value["status"] == "source_revalidated":
            require(set(value) == {"basis", "checked_at", "status", "approved", "source_sha256", "document_version"}
                    and deep["coverage"]["evidence_status"] == "full_document_retrieved"
                    and value["source_sha256"] == deep["coverage"]["source_sha256"]
                    and value["document_version"] == deep["coverage"]["document_version"])
        else:
            require(set(value) == {"basis", "checked_at", "status", "approved", "reason"}
                    and type(value["reason"]) is str
                    and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,100}", value["reason"]))
        return value
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError, RecursionError):
        raise ValueError(ERROR) from None


def strip_staged_enrichment(candidate):
    """Keep input metadata, never inherit claimed source reading or approval."""
    require(type(candidate) is dict)
    return {key: deepcopy(value) for key, value in candidate.items() if key not in STAGED_FIELDS}

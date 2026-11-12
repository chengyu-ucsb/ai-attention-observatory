const HASH = /^[0-9a-f]{64}$/;
const METADATA_FIELDS = new Set(["doi", "url", "title", "authors", "kind", "published", "venue",
  "lane", "relation", "source_group", "source_version", "research_type", "publication_date_provenance"]);
const CLAIM_FIELDS = new Set(["research_question", "study_design", "reported_results",
  "authors_interpretation", "critical_context", "limitations", "open_question", "thesis",
  "reasoning", "examples", "tension", "implications", "qualification"]);

function object(value: unknown): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid_request");
}
function exact(value: Record<string, unknown>, keys: string[]) {
  if (Object.keys(value).sort().join(",") !== keys.sort().join(",")) throw new Error("invalid_request");
}
function bounded(value: unknown, limit: number): asserts value is string {
  if (typeof value !== "string" || !value.length || value.length > limit) throw new Error("invalid_request");
}
function hash(value: unknown) {
  if (typeof value !== "string" || !HASH.test(value)) throw new Error("invalid_request");
}
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") return "{" + Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, item]) => JSON.stringify(key) + ":" + canonical(item)).join(",") + "}";
  return JSON.stringify(value);
}
export async function digest(value: unknown) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical(value)));
  return Array.from(new Uint8Array(bytes), (x) => x.toString(16).padStart(2, "0")).join("");
}
export async function validateRequest(value: unknown): Promise<Record<string, any>> {
  object(value);
  if (value.op === "get_editorial") {
    exact(value, ["op", "key"]); hash(value.key); return value;
  }
  if (value.op === "save_editorial") {
    exact(value, ["op", "key", "revision", "value"]); hash(value.key); object(value.value);
    if (!Number.isSafeInteger(value.revision) || Number(value.revision) < 0 ||
        new TextEncoder().encode(JSON.stringify(value.value)).length > 58000 ||
        !["stage", "edition"].includes(String(value.value.kind))) throw new Error("invalid_editorial_checkpoint");
    if (value.value.kind === "stage") {
      bounded(value.value.stage, 80);
      const attempts = value.value.attempts;
      if (!Array.isArray(attempts) || attempts.length > 2) throw new Error("invalid_editorial_budget");
      for (const [index, attempt] of attempts.entries()) {
        object(attempt);
        if (attempt.attempt !== index + 1 || !["started", "checked", "rejected"].includes(String(attempt.status))) {
          throw new Error("invalid_editorial_budget");
        }
      }
    } else if (!Number.isInteger(value.value.runs) || Number(value.value.runs) < 1 ||
               Number(value.value.runs) > 3 || !["pending", "working", "held", "checked"].includes(String(value.value.status))) {
      throw new Error("invalid_editorial_budget");
    }
    return value;
  }
  if (value.op === "begin_run") {
    exact(value, ["op", "phase", "week", "inputs_hash"]); hash(value.inputs_hash);
    if (!["preparing", "closed"].includes(String(value.phase)) ||
        typeof value.week !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value.week)) throw new Error("invalid_worker_scope");
    return value;
  }
  if (value.op === "finish_run" || value.op === "fail_run") {
    exact(value, ["op", "id", "lease_token", value.op === "finish_run" ? "result" : "reason"]);
    for (const field of ["id", "lease_token"]) {
      if (typeof value[field] !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value[field])) throw new Error("invalid_lease");
    }
    if (value.op === "fail_run") {
      if (value.reason !== "workflow_failed") throw new Error("invalid_failure");
    } else {
      object(value.result);
      exact(value.result, ["phase", "week", "reading_run_sha256", "repository_commit", "attempted", "completed", "failed",
        "deferred_by_limit", "source_text_saved", "independently_approved", "weekly_publication_verified"]);
      hash(value.result.reading_run_sha256);
      if (!["preparing", "closed"].includes(String(value.result.phase)) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(String(value.result.week)) ||
          !/^[0-9a-f]{40}$/.test(String(value.result.repository_commit)) ||
          value.result.source_text_saved !== false || value.result.independently_approved !== false ||
          value.result.weekly_publication_verified !== false) throw new Error("invalid_worker_outcome");
      for (const k of ["attempted", "completed", "failed", "deferred_by_limit"]) {
        if (!Number.isInteger(value.result[k]) || Number(value.result[k]) < 0 || Number(value.result[k]) > 100000) throw new Error("invalid_worker_counts");
      }
      if (Number(value.result.completed) + Number(value.result.failed) !== value.result.attempted) throw new Error("invalid_worker_counts");
    }
    return value;
  }
  if (value.op === "status" || value.op === "probe") {
    exact(value, ["op"]); return value;
  }
  if (value.op === "put_source") {
    exact(value, ["op", "source_id", "kind", "canonical_url", "fingerprint", "metadata", "published_on"]);
    bounded(value.source_id, 2048); bounded(value.canonical_url, 4096); hash(value.fingerprint);
    object(value.metadata);
    if (!Object.keys(value.metadata).every((k) => METADATA_FIELDS.has(k)) ||
        JSON.stringify(value.metadata).length > 24000 ||
        !["scholarly", "nonacademic"].includes(String(value.kind)) || value.metadata.kind !== value.kind ||
        !String(value.canonical_url).startsWith("https://") || await digest(value.metadata) !== value.fingerprint) {
      throw new Error("invalid_source");
    }
    const doi = String(value.metadata.doi || "").trim();
    if (value.source_id !== (doi.toLowerCase() || value.metadata.url) ||
        value.canonical_url !== (doi ? "https://doi.org/" + doi : value.metadata.url)) throw new Error("invalid_source");
    if (value.published_on !== null && (typeof value.published_on !== "string" ||
        !/^\d{4}-\d{2}-\d{2}$/.test(value.published_on))) throw new Error("invalid_source");
    return value;
  }
  if (value.op === "get_checkpoint") {
    exact(value, ["op", "key"]); hash(value.key); return value;
  }
  if (value.op === "save_checkpoint") {
    exact(value, ["op", "key", "source_id", "source_hash", "reader_version", "segment_id", "result"]);
    hash(value.key); hash(value.source_hash); bounded(value.source_id, 2048);
    hash(value.reader_version); bounded(value.segment_id, 32);
    if (!/^C\d{4,}$/.test(String(value.segment_id))) throw new Error("invalid_checkpoint");
    object(value.result); exact(value.result, ["claims", "checked"]);
    if (value.result.checked !== true || !Array.isArray(value.result.claims) || value.result.claims.length > 6) {
      throw new Error("invalid_checkpoint");
    }
    for (const claim of value.result.claims) {
      object(claim); exact(claim, ["field", "text", "source_span", "anchor_sha256"]);
      bounded(claim.text, 2000); hash(claim.anchor_sha256);
      if (!CLAIM_FIELDS.has(String(claim.field)) ||
          !new RegExp("^" + value.segment_id + ":S\\d{3,}$").test(String(claim.source_span))) throw new Error("invalid_checkpoint");
    }
    return value;
  }
  throw new Error("operation_not_allowed");
}

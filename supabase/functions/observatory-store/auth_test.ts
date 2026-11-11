import { generateKeyPair, SignJWT } from "jose";
import { AUDIENCE, ISSUER, verifyGithubToken } from "./auth.ts";
import { digest, validateRequest } from "./validation.ts";

function assert(value: unknown) { if (!value) throw new Error("assertion_failed"); }
async function rejects(operation: () => Promise<unknown>) {
  let failed = false; try { await operation(); } catch { failed = true; } assert(failed);
}
const pair = await generateKeyPair("RS256");
const normal = {
  repository: "chengyu-ucsb/ai-attention-observatory", repository_id: "1424112251",
  repository_owner_id: "242127341", ref: "refs/heads/main", ref_type: "branch",
  workflow_ref: "chengyu-ucsb/ai-attention-observatory/.github/workflows/database-check.yml@refs/heads/main",
  workflow_sha: "a".repeat(40), run_id: "1234", run_attempt: "1", event_name: "push",
  sub: "repo:chengyu-ucsb/ai-attention-observatory:ref:refs/heads/main",
};
async function token(changes = {}) {
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ ...normal, iss: ISSUER, aud: AUDIENCE, iat: now, nbf: now,
    exp: now + 300, jti: "test-only", ...changes }).setProtectedHeader({ alg: "RS256" }).sign(pair.privateKey);
}
Deno.test("OIDC accepts main only and rejects unrelated, fork, stale and forged identities", async () => {
  assert((await verifyGithubToken(await token(), pair.publicKey)).run_id === "1234");
  await verifyGithubToken(await token({
    sub: "repo:chengyu-ucsb@242127341/ai-attention-observatory@1424112251:ref:refs/heads/main",
  }), pair.publicKey);
  for (const change of [
    { repository_id: "42" }, { repository_owner_id: "42" }, { repository: "attacker/ai-attention-observatory" },
    { ref: "refs/pull/1/merge" }, { event_name: "pull_request" }, { event_name: "pull_request_target" },
    { workflow_ref: normal.workflow_ref.replace("database-check", "unrelated") },
    { sub: "repo:chengyu-ucsb/ai-attention-observatory:pull_request" },
    { aud: "https://example.org" }, { iss: "https://example.org" },
    { exp: 1 }, { iat: 1 }, { nbf: Math.floor(Date.now()/1000) + 60 },
    { exp: Math.floor(Date.now()/1000) + 3600 }, { workflow_sha: "untrusted" },
  ]) await rejects(async () => verifyGithubToken(await token(change), pair.publicKey));
  const other = await generateKeyPair("RS256");
  await rejects(async () => verifyGithubToken(await token(), other.publicKey));
});
Deno.test("bridge accepts narrow operations and never arbitrary SQL or source passages", async () => {
  const metadata = { kind: "scholarly", doi: "10.1234/example", title: "Example", published: "2026-11-09" };
  const source = { op: "put_source", source_id: "10.1234/example", kind: "scholarly",
    canonical_url: "https://doi.org/10.1234/example", fingerprint: await digest(metadata), metadata, published_on: "2026-11-09" };
  await validateRequest(source);
  await rejects(() => validateRequest({ ...source, fingerprint: "a".repeat(64) }));
  const body = { ...metadata, full_text: "Publisher text" };
  await rejects(async () => validateRequest({ ...source, metadata: body, fingerprint: await digest(body) }));
  await rejects(() => validateRequest({ op: "sql", query: "drop schema observatory cascade" }));
  await rejects(() => validateRequest({ op: "status", role: "postgres" }));
  const checkpoint = { op: "save_checkpoint", key: "a".repeat(64), source_id: source.source_id,
    source_hash: "b".repeat(64), reader_version: "c".repeat(64), segment_id: "C0001",
    result: { checked: true, claims: [{ field: "limitations", text: "An original paraphrase of a documented limit.",
      source_span: "C0001:S001", anchor_sha256: "d".repeat(64) }] } };
  await validateRequest(checkpoint);
  await rejects(() => validateRequest({ ...checkpoint, result: { ...checkpoint.result, checked: false } }));
  await rejects(() => validateRequest({ ...checkpoint, result: { ...checkpoint.result,
    claims: [{ ...checkpoint.result.claims[0], quote: "Raw passage" }] } }));
  await rejects(() => validateRequest({ ...checkpoint, segment_id: "C0002" }));
});

import postgres from "postgres";
import { canManageRun, canManageEditorial, verifyGithubToken } from "./auth.ts";
import { canonical, digest, validateRequest } from "./validation.ts";

// This is a private backend bridge, never a browser/client API. The platform's
// default connection stays inside Supabase; every query uses a restricted role.
const database = postgres(Deno.env.get("SUPABASE_DB_URL")!, {
  prepare: false, max: 1, connect_timeout: 10, idle_timeout: 20, max_lifetime: 300, ssl: "require",
});
const headers = { "Content-Type": "application/json", "Cache-Control": "no-store" };
function reply(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status, headers }); }
async function boundedBody(req: Request) {
  if (!req.body || Number(req.headers.get("content-length") || 0) > 65536) throw new Error("invalid_body");
  const reader = req.body.getReader(); const chunks: Uint8Array[] = []; let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      length += value.length;
      if (length > 65536) { await reader.cancel(); throw new Error("invalid_body"); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(length); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return JSON.parse(new TextDecoder().decode(bytes));
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return reply({ error: "method_not_allowed" }, 405);
  const token = /^Bearer ([A-Za-z0-9_.-]+)$/.exec(req.headers.get("authorization") || "")?.[1];
  if (!token || token.length > 16000) return reply({ error: "unauthorized" }, 401);
  let identity;
  try { identity = await verifyGithubToken(token); }
  catch { return reply({ error: "unauthorized" }, 401); }
  let input;
  try { input = await validateRequest(await boundedBody(req)); }
  catch { return reply({ error: "invalid_request" }, 400); }
  try {
    const result = await database.begin(async (sql) => {
      await sql`set local role observatory_worker`;
      await sql`set local statement_timeout = '15s'`;
      const owner = `github:${identity.run_id}:${identity.run_attempt}`;
      const runUrl = `https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/${identity.run_id}`;
      if (input.op === "get_editorial" || input.op === "save_editorial") {
        if (!canManageEditorial(identity)) throw new Error("workflow_scope_mismatch");
        if (input.op === "get_editorial") {
          const [row] = await sql`select revision,value from observatory.editorial_checkpoints where cache_key=${input.key}`;
          return row ?? { revision: 0, value: null };
        }
        // Serialize one key, including the first INSERT; unrelated stages remain independent.
        await sql`select pg_advisory_xact_lock(hashtextextended(${input.key},0))`;
        const [current] = await sql`select revision,value from observatory.editorial_checkpoints where cache_key=${input.key} for update`;
        const revision = current?.revision ?? 0;
        if (revision === input.revision + 1 && canonical(current.value) === canonical(input.value)) return { saved: true, revision };
        if (revision !== input.revision) return { saved: false, revision };
        const [saved] = await sql`insert into observatory.editorial_checkpoints(cache_key,revision,value)
          values (${input.key},${revision+1},${sql.json(input.value)})
          on conflict (cache_key) do update set revision=excluded.revision,value=excluded.value,updated_at=now()
          returning revision`;
        return { saved: true, revision: saved.revision };
      }
      if (input.op === "begin_run") {
        if (!canManageRun(identity, input.phase)) throw new Error("workflow_scope_mismatch");
        const start = new Date(); start.setUTCHours(0, 0, 0, 0);
        start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7 - (input.phase === "closed" ? 7 : 0));
        if (start.toISOString().slice(0, 10) !== input.week) throw new Error("worker_week_changed");
        const scope = `readings:${input.phase}:${input.week}`;
        const [row] = await sql`select observatory.begin_worker_run(${scope},${input.inputs_hash},${owner},${runUrl}) as lease`;
        return row.lease;
      }
      if (input.op === "finish_run" || input.op === "fail_run") {
        const [job] = await sql`select * from observatory.jobs where id=${input.id} for update`;
        if (!job || !canManageRun(identity, String(job.input.scope || "").split(":")[1])) throw new Error("workflow_scope_mismatch");
        const leaseHash = await digest(input.lease_token);
        const result = input.op === "finish_run" ? { ...input.result, run_url: runUrl, _worker: owner, _lease_hash: leaseHash } :
          { reason: input.reason, run_url: runUrl, _worker: owner, _lease_hash: leaseHash, weekly_publication_verified: false };
        // A lost HTTP response may retry an already committed write.
        if (job.lease_owner === null && canonical(job.result) === canonical(result)) return { saved: true };
        if (job.state !== "running" || job.lease_owner !== owner || job.lease_token !== input.lease_token) return { saved: false };
        if (input.op === "finish_run") {
          if (job.input.scope !== `readings:${input.result.phase}:${input.result.week}`) throw new Error("outcome_scope_mismatch");
          const [row] = await sql`select observatory.finish_job(${input.id},${input.lease_token},${sql.json(result)}) as saved`;
          return row;
        }
        const [row] = await sql`select observatory.fail_job(${input.id},${input.lease_token},'internal',${input.reason},900) as saved`;
        if (row.saved) await sql`update observatory.jobs set result=${sql.json(result)} where id=${input.id}`;
        return row;
      }
      if (input.op === "put_source") {
        await sql`insert into observatory.sources(source_id,kind,canonical_url)
          values (${input.source_id},${input.kind},${input.canonical_url}) on conflict do nothing`;
        await sql`insert into observatory.source_versions(source_id,fingerprint,metadata,published_on)
          values (${input.source_id},${input.fingerprint},${sql.json(input.metadata)},${input.published_on}) on conflict do nothing`;
        return { source_id: input.source_id, fingerprint: input.fingerprint };
      }
      if (input.op === "get_checkpoint") {
        const rows = await sql`select result from observatory.reading_checkpoints where cache_key=${input.key}`;
        return { checkpoint: rows[0]?.result ?? null };
      }
      if (input.op === "save_checkpoint") {
        await sql`insert into observatory.reading_checkpoints(cache_key,source_id,source_hash,reader_version,segment_id,result)
          values (${input.key},${input.source_id},${input.source_hash},${input.reader_version},${input.segment_id},${sql.json(input.result)}) on conflict do nothing`;
        return { saved: true };
      }
      const [counts] = await sql`select current_user as database_role,
        (select count(*)::int from observatory.sources) as sources,
        (select count(*)::int from observatory.editions) as editions,
        (select count(*)::int from observatory.reading_checkpoints) as checkpoints`;
      if (counts.database_role !== "observatory_worker") throw new Error("role_not_restricted");
      if (input.op === "probe") {
        const key = `database-probe:${identity.run_id}:${identity.run_attempt}`;
        const probeHash = await digest({ purpose: "checkpoint_probe", key });
        const [source] = await sql`select source_id from observatory.sources order by source_id limit 1`;
        if (!source) throw new Error("source_import_required");
        // Test checkpoint persistence inside a savepoint, then remove the fixture.
        // The only durable change is an explicitly labeled connectivity receipt.
        await sql`savepoint checkpoint_probe`;
        await sql`insert into observatory.reading_checkpoints(cache_key,source_id,source_hash,reader_version,segment_id,result)
          values (${probeHash},${source.source_id},${probeHash},${probeHash},'C0001','{"claims":[],"checked":true}'::jsonb)`;
        const [roundtrip] = await sql`select result from observatory.reading_checkpoints where cache_key=${probeHash}`;
        if (roundtrip.result.checked !== true) throw new Error("checkpoint_probe_failed");
        await sql`rollback to savepoint checkpoint_probe`;
        await sql`release savepoint checkpoint_probe`;
        await sql`insert into observatory.jobs(dedupe_key,kind,input,state,result)
          values (${key},'verify',${sql.json({ purpose: "database_connectivity", run_id: identity.run_id,
            workflow_sha: identity.workflow_sha })},'done',${sql.json({ connection: "verified", ...counts,
            checkpoint_roundtrip: true, weekly_publication_verified: false })}) on conflict do nothing`;
        const [saved] = await sql`select id from observatory.jobs where dedupe_key=${key} and state='done'`;
        return { ...counts, receipt_id: saved.id, checkpoint_roundtrip: true, weekly_publication_verified: false };
      }
      const recent = await sql`select id,kind,state,attempts,input->>'scope' as scope,
        result->>'run_url' as run_url,created_at,updated_at from observatory.jobs
        where kind='review' order by updated_at desc limit 10`;
      return { ...counts, recent_runs: recent };
    });
    return reply(result);
  } catch {
    // Never expose database URLs, SQL parameters, tokens, or publisher text.
    return reply({ error: "store_unavailable" }, 503);
  }
});

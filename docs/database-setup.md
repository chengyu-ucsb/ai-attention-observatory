# Database setup and implementation status

## Where the database belongs

The connected project is [ai-attention-observatory](https://supabase.com/dashboard/project/jrndagmzayiwpmyjtczx),
project ref `jrndagmzayiwpmyjtczx`, in US East. The private `observatory`
schema is installed. On November 11, 2026, its metadata import contained 688
source identities and four already-published edition snapshots. These are
indexed records, not a claim that 688 full articles have been reviewed.

GitHub remains the cloud authority for code, versioned publication artifacts and
the deployed site. Supabase becomes the authority for live operational state:
source identities, reading progress, jobs, frozen editions and publication
receipts. The website consumes screened static exports and remains readable
when the operational database is unavailable.

## Implemented in this change

| Component | Behavior | Activation |
| --- | --- | --- |
| Reader export | Small published-edition manifest; content-addressed search index; full readings fetched individually | Pages build |
| Edition display | Featured source cards use the featured edition's frozen source list | Pages deployment |
| Deployment receipt | Fetches the live manifest, permanent edition and RSS; rejects stale or mismatched deployment | Every Pages deployment |
| Retry policy | Two bounded same-day retries for output-format errors; no promotion of unsupported claims | Existing reading runs |
| Private database | Ten tables, row-level access controls, immutable evidence and editions, leased jobs and publication hashes | Installed and tested in the connected project |
| Reading checkpoints | Reuses successfully checked sections only when source, parser, model and chunk hashes match | Scheduled readers use the private GitHub OIDC bridge |
| Queue adapter | Deduplicated inserts; current/backfill lanes; leases and stale-worker fencing; typed failure delays | Ready for worker integration |

Database activation is **not a complete worker-queue migration**. The current
reading model, two-document run limit,
shared GitHub writer lock and scheduling remain in service during this stage.
End-to-end Monday delivery and improved review throughput remain unverified.

## Private worker connection

No database password or Supabase service key is stored in the website or required
in GitHub Actions. `observatory-store` is a deployed Supabase Edge Function that
verifies short-lived GitHub OIDC tokens against GitHub's signed public keys.
It requires the exact repository and immutable owner/repository IDs, the `main`
branch, the expected audience and one of three approved workflow paths:

- `.github/workflows/prepare-weekly-readings.yml`
- `.github/workflows/finalize-weekly-readings.yml`
- `.github/workflows/database-check.yml`

Pull-request tokens, other branches, unrelated workflows, wrong audiences,
expired tokens and invalid signatures fail authentication. The platform's
Supabase-JWT gateway check is disabled because this endpoint accepts GitHub JWTs;
the function performs signature and claim verification before any database query.
No browser CORS policy or browser database credentials are enabled.

The function uses Supabase's built-in server connection and executes every
transaction as the restricted `observatory_worker` role. The three applied
migrations are:

1. `20261111112523_observatory.sql`: private schema and recovery primitives.
2. `20261111113233_observatory_foreign_key_indexes.sql`: covering indexes.
3. `20261111113632_observatory_edge_worker_role.sql`: permit the server connection
   to drop into the worker role; Supabase initially granted membership with
   `SET FALSE`. This grants no browser access or additional worker privileges.

The Python bridge exposes only allowlisted metadata writes, checkpoint reads and
writes, status and a connectivity probe. It cannot execute arbitrary SQL. It
rejects unexpected fields and raw passage fields, bounds requests and retries,
never follows credential-bearing redirects, and never prints tokens or database
errors. Checkpoints contain checked paraphrases and hashes of supporting spans;
exact source passages are reconstructed and validated against the current text.
A partial checkpoint never qualifies a whole paper as reviewed.

`Verify private research database` tests token rejection and payload validation on
pull requests. Its main-branch job uses a real GitHub token, checks the effective
database role, exercises checkpoint write/read/rollback, then persists a labeled
connectivity receipt in `observatory.jobs`. That receipt explicitly says weekly
publication was not verified. Check the actual run and stored receipt before
claiming that the GitHub connection works; a deployed function alone is not proof.

The existing direct PostgreSQL adapter remains available for separately
provisioned backend workers through `OBSERVATORY_DATABASE_URL`. The scheduled
readers prefer `OBSERVATORY_STORE_URL`, the public endpoint URL, and need no such
secret. A configured bridge failure stops the affected reading rather than
pretending progress was saved. Future queue handlers must commit leases before
external work. A lease does not make external side effects exactly-once.

The metadata import copied only allowlisted bibliographic fields and the four
validated published edition snapshots. It copied no source bodies. Snapshot
hashes were read back from Supabase and matched the repository's canonical
encoding. Import does not establish that a new weekly edition has been published.

No source-storage bucket or user-response table is activated by this migration.
The optional retrieval object key requires a documented retention basis; raw
publisher text does not belong in public git. Add a private bucket, retention
rules and object-level policies only when a retrieval workflow needs them.

## Production cutover still to implement

The target is a **Monday noon America/New_York publication**, with a final
closeout starting at Monday midnight in that timezone. Incremental discovery
and reading throughout the previous week should reduce Monday's remaining work.
Eligibility continues to use the previous completed Monday–Sunday **UTC** week
and the source's original publication date. Indexing dates cannot admit old work.

With the database connected, the remaining cutover work is:

1. Move source retrieval, review and synthesis handlers onto the leased queue;
   enforce per-provider limits and store observed outcomes. Protect current-week
   capacity from historical backfill. Run the old and new queues in comparison
   mode before choosing one authority and disabling old writers.
2. Benchmark a stronger reader on a fixed evidence set before choosing hosted
   inference or provisioned compute. Measure accepted summaries, source-supported
   claims, failures, elapsed time and cost. Schema validity alone is insufficient.
3. Add a timezone-aware dispatcher and an external missed-run check. Long reads
   belong on a worker, not inside a short scheduled database/edge request. Freeze
   the validated edition before deployment; verify the exact frozen hash, its
   permanent URL and feed entry afterward. An old issue remaining live is not a
   successful current-week publication.
4. Launch Lab work independently: versioned evidence-linked protocols first,
   then authenticated cross-device saved sessions with per-user row-level access.
   Test with two distinct accounts before storing responses. The existing demos
   remain demonstrations; no efficacy claim or participant research is implied.
5. Website, RSS and the existing chat delivery can use the same edition ID.
   Email subscriber collection and sending need a selected service and separate
   connection; this change does not create a mailing list or send email.

Late sources and failed reviews stay visible in coverage reporting and may form
an explicitly dated correction or later edition. Do not silently rewrite a
frozen issue or wait indefinitely for every source to succeed. If the evidence
gate is unmet, publish a status notice with the latest actual edition link.

## Verification and rollback

The offline suite covers source gates, receipt integrity, retry classes, exact
edition binding and reading resume. `tests/validate_database.cjs` executes the
migration with PostgreSQL semantics through PGlite and checks lease fencing,
duplicates, immutable snapshots, publication hash binding and private access.
Run it with `@electric-sql/pglite@0.5.16` available, or set `PGLITE_MODULE` to its
installed module path. This is not a substitute for testing the connected
Supabase project, including its network and account configuration.

The `Publish observatory website` run must finish its live verification step.
Check the reported edition date and publication window separately from job
success. To disable cloud reading checkpoints, remove `OBSERVATORY_STORE_URL`
from both reading workflows and any optional `OBSERVATORY_DATABASE_URL` secret; existing git-based reading receipts remain usable. Keep database
snapshots and published archives intact when rolling back code.

## Function deployment

Runtime dependencies are pinned in `deno.json`; the same exact versions and npm
integrity hashes are recorded in `package.json` and `package-lock.json` for CI.
Deploy `index.ts`, `auth.ts`, `validation.ts` and `deno.json`, using `deno.json` as
the import map. Do not upload the CI-only npm package files or `node_modules`:
including a package manifest makes the Edge bundler expect a local dependency
tree. Never add credentials to the function source or deployment bundle.

The connected-project tests verified private role access, checkpoint round-trip,
expired-lease recovery, stale-token rejection and semantic holds inside a rolled
back transaction. Test source rows were confirmed absent afterward. Security
Advisor returned no findings after these migrations. The offline suite also
verifies immutable editions and exact publication hash binding.

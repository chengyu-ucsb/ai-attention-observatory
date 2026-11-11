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
| Reading workers | One live lease per reading phase/week; resumable sections; bounded retries; outcome and saved commit recorded | Preparation and final-reading workflows |

Database activation is **not a complete worker-queue migration**. The current
reading model, two-document run limit and shared GitHub writer lock remain in
service. Scheduling now uses America/New_York and retries due reading work.
The database tracks bounded reading passes; individual article fan-out and
synthesis-job migration remain separate work.
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
transaction as the restricted `observatory_worker` role. The applied
migrations are:

1. `20261111112523_observatory.sql`: private schema and recovery primitives.
2. `20261111113233_observatory_foreign_key_indexes.sql`: covering indexes.
3. `20261111113632_observatory_edge_worker_role.sql`: permit the server connection
   to drop into the worker role; Supabase initially granted membership with
   `SET FALSE`. This grants no browser access or additional worker privileges.
4. `20261111135507_observatory_worker_runs.sql`: exclusive leases for bounded
   reading passes, recovery after expiration, and deduplication by exact inputs.
5. `20261111140534_observatory_worker_budget.sql`: a conservative limit of
   six claimed attempts per phase/week per Eastern calendar day.

The Python bridge exposes only allowlisted metadata writes, checkpoint reads and
writes, restricted reading-run operations, status and a connectivity probe. It cannot execute arbitrary SQL. It
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

## Active worker schedule

GitHub's native `timezone: America/New_York` keeps these opportunities on the
local clock through daylight-saving changes. Original-publication eligibility
continues to use the prior completed Monday–Sunday UTC window.

| Stage | Eastern-time opportunities |
| --- | --- |
| Rolling preparation | Every day at 6:17 a.m. and 6:17 p.m. |
| Monday collection/closeout | 12:07, 2:07, 6:07 and 10:07 a.m. |
| Monday final reading passes | 3:27, 6:27, 9:27 and 11:27 a.m.; 3:27 p.m. |
| Later reading recovery | Tuesday–Sunday at 9:27 a.m. |
| Monday composition attempts | 10:17 a.m., 12:17 p.m. and 4:17 p.m., plus successful finalizer completion |
| Later composition recovery | Tuesday–Sunday at 12:17 p.m. |
| Publication-status rebuild | Monday at 12:47 and 5:47 p.m.; other days at 12:47 p.m. |
| Missing-discovery check | Daily at 3:41 and 8:41 a.m.; only a genuinely absent launch is eligible |

Noon is a target, not a guaranteed delivery time. GitHub scheduling and the
shared writer queue can delay starts. Evidence gates can also hold a draft.
`pipeline-status.json` records the timezone-aware target, source window and an
explicit notice when the current edition has not been published. The existing
Monday 1 p.m. chat delivery checks the website independently and reports a delay
instead of calling an old edition new.

Both reading workflows acquire a Supabase lease before model setup. A second
worker for that phase/week is blocked; a lost HTTP response can safely retry the
same lease request. An interrupted lease expires after 110 minutes, longer than
the 80-minute job cap. The token stays in private runner temporary storage.
After validated results are pushed, the worker saves counts and the exact commit
in Supabase. A failed Git save schedules an internal retry; it is not recorded as
completed reading work. A completed pass may still contain failed reviews and
always states `weekly_publication_verified: false`.

A valid final-pass receipt no longer suppresses later due readings. The worker
planner and the actual reader require the same acquired-document receipts and
share the same eligibility/cooldown policy. Metadata-only entries remain access
gaps; they do not dispatch empty reading passes or hold an otherwise valid
edition indefinitely. Existing acquisition schedules keep retrying those gaps. When
more readings are immediately due, a successful saved pass dispatches the next
bounded pass automatically. The server enforces a conservative six-attempt
daily cap, including retries; excess continuations stop before model setup.
Publication waits for immediately due readings and still uses the independent
input/citation gates. Access restrictions and semantic holds remain explicit;
no failed reading is promoted to meet the publication target.

To explicitly start a bounded final reading on a trusted main-branch code push,
include `[run-readings]` in the commit message and change the finalizer workflow
or `scripts/worker_run.py`. Ordinary code pushes do not use that direct recovery
route. Existing trusted upstream-workflow triggers remain supported.

# Database setup and implementation status

## Where the database belongs

Create a hosted **Supabase** project named `ai-attention-observatory` at
<https://supabase.com/dashboard>. A US East region is a reasonable default for
this project. Connect that project through the Supabase integration in ChatGPT
so its schema and access can be inspected without sharing passwords in chat.

GitHub remains the cloud authority for code, versioned publication artifacts and
the deployed site. Supabase becomes the authority for live operational state:
source identities, reading progress, jobs, frozen editions and publication
receipts. The website consumes screened static exports and remains readable
when the operational database is unavailable.

Free is suitable for setup and a pilot. Supabase currently pauses Free projects
after a week of inactivity; a paid plan avoids that pause. Pro starts at $25 per
month for the included project compute, with usage and additional compute billed
separately. This does not include a model provider or an external worker.
See [pricing](https://supabase.com/pricing) and
[Free project pausing](https://supabase.com/docs/guides/platform/free-project-pausing).

## Implemented in this change

| Component | Behavior | Activation |
| --- | --- | --- |
| Reader export | Small published-edition manifest; content-addressed search index; full readings fetched individually | Pages build |
| Edition display | Featured source cards use the featured edition's frozen source list | Pages deployment |
| Deployment receipt | Fetches the live manifest, permanent edition and RSS; rejects stale or mismatched deployment | Every Pages deployment |
| Retry policy | Two bounded same-day retries for output-format errors; no promotion of unsupported claims | Existing reading runs |
| Private database | Ten tables, row-level access controls, immutable evidence and editions, leased jobs and publication hashes | Apply migration after project connection |
| Reading checkpoints | Reuses successfully checked sections only when source, parser, model and chunk hashes match | Add verified backend database secret |
| Queue adapter | Deduplicated inserts; current/backfill lanes; leases and stale-worker fencing; typed failure delays | Ready for worker integration |

The SQL and adapter are tested, but an unconnected project is **not a migrated
production pipeline**. The current reading model, two-document run limit,
shared GitHub writer lock and scheduling remain in service during this stage.
End-to-end Monday delivery and improved review throughput remain unverified.

## Activate safely after connecting the project

1. Apply `supabase/migrations/202611110001_observatory.sql` once through the
   project's migration tooling. Keep `observatory` out of Supabase's exposed
   API schemas. Its tables are private operational data, not a browser API.
2. Verify that anonymous and authenticated browser roles cannot read these
   tables or execute their functions. The migration creates a `NOLOGIN`
   `observatory_worker` group. Provision a separate backend login belonging to
   that group, without owner, superuser or bypass-RLS privileges.
3. Save that backend's connection string in the repository's **Actions secret**
   `OBSERVATORY_DATABASE_URL`. Do not use the owner connection or put the value
   in JavaScript, commits, logs, issues or chat. Use a supported direct or pooler
   connection with TLS; the adapter requires TLS and disables prepared statements
   for pooler compatibility. See
   [connection options](https://supabase.com/docs/guides/database/connecting-to-postgres).
4. In a trusted worker environment, install `requirements-database.txt` and run
   `python scripts/observatory_store.py status`, then `import`. Import copies only
   allowlisted source metadata and already published edition snapshots. It does
   not copy source bodies or certify previous deployment. Verify counts and
   edition hashes against the checked-out repository before cutover.
5. Exercise one real prepared-reading job with the backend connection. Interrupt
   it after a completed section, then resume it and verify reuse. A changed
   source, model or parsing policy must cause a fresh read. No partial checkpoint
   qualifies an article as fully read or independently reviewed.

The existing preparation and final-reading workflows already accept this
optional secret. With no secret, they keep their existing storage behavior.
Once configured, completed sections persist immediately; a database error fails
the affected reading instead of pretending progress was saved. Store calls used
by future workers must commit a lease before doing external work (or use an
autocommit connection). A lease does not make external side effects exactly-once.

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

After the database is connected:

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
success. To disable cloud reading checkpoints, remove the backend Actions
secret; existing git-based reading receipts remain usable. Keep database
snapshots and published archives intact when rolling back code.

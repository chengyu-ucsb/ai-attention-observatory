# Prepare the weekly edition before Monday

The open publication week can be collected and processed before it closes.
The final edition still covers **original publications Monday–Sunday UTC**.
Observation, indexing, modification and `first_seen` dates never establish an
original publication date. Late Sunday publications are eligible, including
those first found during Monday's closing pass.

## Private metadata lane

`scripts/weekly_preparation.py` uses the production scholarly and publisher-feed
collectors. It does not replace them with a separate scraper, change `TODAY`,
write `library.json` or `weekly.json`, invoke a model, approve a reading, or touch
an existing issue. Its output is an input for the separately bounded full-source
acquisition and review stages, not a published edition.

Under the existing **common data-writer lock**, run:

```bash
python scripts/weekly_preparation.py --max-requests 48 --max-feed-requests 24 --max-pages 1 --time-budget 240
```

The CLI always reads the real UTC clock. `now` is injectable in the Python API
for deterministic offline tests, not exposed as a CLI clock override.

Outputs are isolated beneath `data/weekly-preparation/<target-Monday>/`:

- `packet.json`: validated current metadata candidates and quarantined evidence.
- `snapshots/<actual-observation-time>-<content-hash>.json`: durable observations.
- `status.json`: calendar and metadata progress, never editorial approval.
- Acquisition/review may keep `acquisition.json`, `readings.json` and
  `review-status.json` alongside the packet. Intake never reads or changes them.

This is an internal processing namespace, not a security boundary for a public
Git repository. Do not put licensed source documents, credentials, private
account information or unapproved source-text copies here. Public payloads and
Pages deployment must continue to use their existing explicit allowlists.

Scholarly checkpoints use **one shared** `data/academic-discovery-state.json`,
with independent `preparation:<day>:<day>`, `closeout:<Monday>:<Sunday>`, `closeout_late_index:<Monday>:<Sunday>`, and
normal `weekly:<Monday>:<Sunday>` namespaces. Preparation never rewrites a normal
weekly cursor or its date evidence. Provider quota/denial state is shared in
both directions: changing a phase, date or week does not clear a cooldown.
Publisher feeds similarly reuse the existing validated
`data/editorial-feed-cache.json` and its persisted host pauses.

Preparation traverses the target week's daily scholarly query slices, resuming
unfinished searches and replaying completed exact queries without another
request. An overall request ceiling applies across all general searches,
venue searches and DOI/date lookups, not separately to each query. A deadline
prevents starting another request after the budget expires; an already-running
request retains its production transport timeout. Bounded publisher capture
starts from the live feed root, preserves disappearing feed metadata, and
retains missing-date observations in the packet quarantine. Supplemental
Google News search is not part of this early lane.

A daily slice observed before its day ends is provisional. It is **not** a claim
that later arrivals or delayed indexing have been seen. Production cursors are
not a frozen provider snapshot. These gaps are why the independent closing pass
below is mandatory.

## Shared staging packet contract

```json
{
  "schema_version": 1,
  "kind": "weekly_preparation",
  "observation_at": "2026-11-07T15:00:00+00:00",
  "target_publication_window": {"from": "2026-11-02", "to": "2026-11-08", "timezone": "UTC"},
  "phase": "preparing",
  "status": "partial",
  "date_eligibility": "verified_original_publication_date_only",
  "public_eligible": false,
  "source_checked": false,
  "approved": false,
  "run": {
    "date": "2026-11-07",
    "mode": "preparation",
    "publication_window": {"from": "2026-11-02", "to": "2026-11-08", "timezone": "UTC"}
  },
  "items": [],
  "quarantine": [],
  "coverage": {"closeout_required": true, "closeout_started_at": null}
}
```

`validate_packet(packet, now)` returns the normalized target window. It checks
actual observation time, the current open or actual previous closed UTC week,
exact run/window consistency, false public/review/approval flags, unique
identities, and independent `weekly_eligible` original-date evidence for every
item. A publication later than the actual observation day is rejected. A stale
open packet must undergo closeout before consumption in the next week.

The states are independent:

- **Prepared**: the bounded configured metadata queries/snapshots succeeded with
  no retained quarantine. This does not mean the article has been read.
- **Partial**: unfinished, blocked, deferred or unresolved metadata work remains.
- **Closed**: the calendar week ended and a post-Sunday closing pass started.
  It can still be partial.
- **Source-checked**: a separate actual full-document acquisition/review gate.
  Intake does not set it.
- **Approved**: the separate existing editorial/publication gate. Neither a
  prepared packet, calendar closure nor a machine extraction grants approval.

`metadata_observed_at` on scholarly candidates records the actual retained
provider-page observation, so cursor replay does not claim a new provider
check. Feed records retain the actual snapshot observation separately. Packet
`observation_at` is the actual local reconciliation time. None are date evidence. Unchanged substantive date provenance retains its original
`checked_at`, so an operational refresh alone does not invalidate an otherwise
identical source-bound receipt. Changed value, basis, source or version still
changes the evidence and must be revalidated.
Quarantine retains unresolved/conflicting evidence and its history; it never
falls back to `first_seen` to become a candidate.

## Sunday closure and normal weekly validation

After Sunday 23:59:59 UTC has passed:

```bash
python scripts/weekly_preparation.py --closeout --max-requests 48 --max-feed-requests 24
```

This starts a **distinct full-week closeout generation at the provider head**,
not the exhausted preparation cursor. It includes fresh Sunday arrivals and
newly indexed earlier-week records, reconciles date corrections, combines
retained feed snapshots with fresh feed capture, and keeps unresolved evidence
in quarantine. Subsequent closeout calls resume this same generation and do not
repeat already completed searches. Delayed indexing after that pass can still
leave coverage partial in the real world; never claim universal completeness.

The orchestration API is:

```python
packet = prepare(root, closeout=True)
adopted = adopt_closed_packet(packet, canonical_library)
# Controlled caller writes adopted['library'], adopted['weekly'], and
# adopted['quarantine'], then runs the normal source/reading/publication gates.
```

`adopt_closed_packet` is pure: it returns metadata reconciled into a copy of the
canonical library and a normal strict previous-week payload, preserving existing
reading/body/receipt/approval fields. Earlier original dates and new unresolved
conflicts can remove records from weekly eligibility. New acquisition summaries
must be reconciled separately by their identity/version/date fingerprints;
unchanged metadata is not permission to copy a source-checked or approved flag.
`closed_packet` provides the strict weekly input without canonical adoption.
Neither pure function writes or publishes anything. Incoming records are projected
through a metadata allowlist, including quarantine. Staged `source_review`,
`deep_analysis`, body text, source-check and approval fields cannot be imported;
invalid original-reading receipts are rejected by the existing source gate.

Do **not** immediately run `update.main` or another complete live search after
adoption. Once all configured closeout queries finish,
`adopt_closeout_checkpoint(path, now)` can clone that validated generation into
an **absent** normal weekly namespace. Later ordinary resume then replays the
same query results. It never overwrites an existing weekly cursor and never
seeds a partial closeout. If adoption is skipped, continue the closing generation
rather than launch another full search merely to fill a checkpoint.

For the controlled canonical-write step, under the same writer lock:

```bash
python scripts/weekly_preparation.py --closeout --adopt
```

This writes each of `library.json`, `weekly.json`, the discovery quarantine, and
`runs.json` by atomic replacement. It does not claim a multi-file transaction.
On an interrupted write, repeat validated adoption from the saved packet; do not
repeat provider searches solely to recover file writes. Public/approved output
files are never written by this command.

One later, deliberately named closing pass can find a Sunday publication that
was not indexed during the first post-midnight scan:

```bash
python scripts/weekly_preparation.py --closeout --closeout-pass late_index --adopt
```

It requires an initial closeout for this target week and cannot start before
Monday 06:00 UTC. The separate `closeout_late_index` namespace starts at the
provider head once. Restarts resume the same saved generation, without clearing
provider controls or duplicating completed searches. Once it has started,
default `--closeout` calls resume this later generation; an explicit attempt to
regress to the initial pass is rejected. Existing normal weekly checkpoints
remain untouched even when this second pass finds additional records. Later
index changes beyond these bounded observation checkpoints remain a coverage
limitation, not a promise of completeness.

Integrating or scheduling this lane must retain the common writer lock and the
public builders' original-date, source-access, source-version, summary and
approval gates. The orchestration below starts daily preparation during the week and performs
early Monday reconciliation before final synthesis. Set future cadence changes
from measured acquisition/review queue duration, not an assumption that one day
always suffices. This module alone does not establish deployment readiness.

## Offline regressions

```bash
python -m unittest discover -s tests -p 'test_weekly_preparation.py' -v
python -m unittest discover -s tests -q
```

Fixtures cover late Sunday additions, delayed indexing, unknown/conflicting
dates, true observation time, immutable published files and prepared receipts,
shared quota/denial state, bounded resumption, complete-query replay, fresh
closeout cursors, and no-overwrite adoption into normal weekly discovery.

## Rolling schedule and final-stage handoff

The repository now defines the orchestration in the following workflows. A local
implementation is not evidence that these schedules have been activated or that
any production run succeeded. Verify the first real runs before claiming that.

- **Prepare rolling weekly readings**, daily at 01:29 UTC: stage the actual open
  week, bounded to 48 academic requests, 24 feed requests and 240 seconds; acquire
  at most 12 records within 480 seconds; then attempt at most two machine
  readings with the existing local 1.5B model. No canonical library, public
  projection, edition or approval is written by this workflow.
- **Update research library**, Monday at 00:23 and 06:37 UTC, with 12:53 and
  19:53 recovery opportunities: weekly mode reconciles/adopts the preparation
  packet instead of repeating `update.py` discovery. The first real post-Sunday
  run starts the initial full-week generation. Once it exists and Monday 06:00
  has passed, one separate late-index generation may start, even if quotas left
  the initial attempt partial. Each generation keeps its own cursors/history.
  Repeated runs resume the latest generation without resetting finished queries.
  Backfill still uses its existing `update.py` route, and rebuild stays local.
- **Resume weekly source discovery** keeps its four daily opportunities and
  current strict-window guard. It can advance to that same single late-index
  generation or resume it, bounded to 48 requests/240 seconds and no new live
  feed requests. Existing publisher date/genre verification stays separately
  bounded. It never creates an extra generation for every retry.
- **Finalize weekly source readings** follows successful trusted closeout/resume
  runs and has Monday/Tuesday 10:11 and 18:11 UTC recovery opportunities. It
  requires a real closed, adopted late-index packet; acquisition, review,
  source/version/hash revalidation and application run before rebuilding public
  projections. A no-model/awaiting-input report cannot count as a completed
  reading stage. Actual failed readings are recorded as failures, not successful
  full reviews. A fully unchanged finalized input set skips another model run.
- **Publish weekly edition** follows final reading, not unrelated historical
  backlog completion. Its scheduled/manual recovery also checks the exact
  final-reading receipt first. It still requires the existing substantive
  evidence, source citations, date window and synthesis validation. Properly
  labelled abstract-backed evidence remains usable; source acquisition and
  machine notes never create independent approval.

The longest event chain is closeout → final reading → edition → Pages, three
`workflow_run` links. Daily staging does not start a public workflow. The
canonical acquisition queue and historical backfill retain their separate work,
but are not prerequisites for this week's final-reading stage or synthesis.

All shared metadata writers (including publisher-feed snapshots and canonical
source acquisition) queue under `observatory-index` with `queue: max` and no
cancellation. This prevents a staged acquisition from racing provider cooldown,
source-denial, scholarly cursor or publisher-cache updates. A data push race
retries/rebases the completed commit, not the external collection.

The two reading jobs have an 80-minute ceiling to include bounded acquisition,
two potentially 20-minute reading attempts, final source revalidation, model
setup and offline validation. This timeout is a cap, not measured throughput.
Validated packet snapshots, acquisition receipts, generated paraphrases and
provider controls are saved even if a later model, validation or push step fails.
Recovery artifacts contain only that validated allowlist, not source PDFs,
article bodies or the whole runner directory. Each file is validated independently. An invalid packet or reading file is
excluded and makes the step fail, while valid provider/cache checkpoints can
still be preserved. Recovery retains the namespace captured before work began,
even if a delayed job crosses Monday UTC. Each writing stage also checks the
captured expected week against its actual clock before external work; if a
setup delay crossed Monday, it fails instead of quietly choosing another week.
Historical observations are never
relabelled as current publication input. Metadata-only recovery commits use a
clean detached worktree, leaving dirty failed canonical projections untouched
in the original ephemeral checkout. Completed closeout metadata can be
re-adopted after an interrupted canonical write without repeating collection.

`reading-run.json` records the stages actually executed and their outcomes.
`final-reading.json` is written only after the final stages and local builders.
It binds the exact packet, acquisition state, reading bundle, canonical library,
weekly snapshot and execution receipt. A changed input, stale week, changed
receipt or absent late-index pass requires finalization again. These are local
integrity receipts, not attestations of human/expert review.

Coverage distinguishes eligible/quarantined metadata, canonical current-week
records, full and partial acquired documents, full and partial machine-checked
readings, newly completed versus failed attempts, and separately accepted
original readings already present in canonical data. Independent approvals
granted by this pipeline are always zero; existing accepted original readings
are retained, not re-labelled as approval by this workflow.

A later operational observation date must not create a second edition for the
same previous Monday–Sunday UTC publication window. `compose_issue.pending`
checks accepted drafts and published archives by that strict window. It does not
rewrite observation dates, source publication dates, existing issue IDs or RSS
identities. A genuinely different publication week remains eligible.

## Lead-time evidence, not a publication promise

Observed cron delays were approximately **4–8 hours**, synthesis **12–18 minutes**,
and Pages about **1 minute**. Together that is **4h13m–8h19m** for the known
schedule/synthesis/deployment components alone, excluding acquisition, model
setup, remaining reading work and further serialized queue waits. These measured
ranges are not a bound on future GitHub scheduler delay.

Full-review throughput has not been verified. No honest full-corpus completion
estimate or guaranteed Monday delivery time can be derived from those numbers.
Start rolling work each day throughout the publication week rather than waiting
for Monday; preserve a genuine post-Sunday reconciliation and one later index
pass. Daily attempts create several earlier opportunities, but do not guarantee
that every source becomes available or that every model review passes.

Read the offline report with `python scripts/preparation_pipeline.py lead-time`.
After authorized deployment, measure actual acquisition/review durations, queue
age, completed/partial/failed counts and end-to-end delay before adjusting the
cadence or promising a deadline. Public-repository staging is **unpublished**, not
confidential storage; existing Pages allowlists exclude it.

# Recovering an absent weekly launch

## Observed November 9, 2026

At 15:51 UTC, no `Update research library` run had been created for the new
week, despite the then-configured 12:23 primary and 15:37 recovery cron times passing. The
19:53 recovery remained upcoming under that previous schedule. The raw snapshot was still November 7 and
covered October 26–November 1. The next collection must cover November 2–8;
changing a snapshot date cannot establish that evidence.

Other scheduled jobs ran that morning. GitHub's status page reported an
Actions/Webhooks incident resolved at 11:50 UTC, before the primary schedule.
It does not establish causation. Official documentation permits delayed or
dropped scheduled events. The exact cause remains unknown; workflow state
could not be definitively read through the connected inspection tools.

Sources:
- https://github.com/chengyu-ucsb/ai-attention-observatory/actions/workflows/refresh.yml
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://www.githubstatus.com/

## Proposed local implementation, not deployed

The new daily 08:41 UTC watchdog is a separate chance to notice that no launch
occurred. It is also subject to GitHub's scheduling delays and is not an
independent availability guarantee. An external read-only monitor should
report a missing collection after the recovery window.
Daily includes weekends, allowing a late recovery before the UTC week rolls
over. These are metadata checks, not seven new article searches.

The planner only permits a recovery request when all these facts are known:

1. Monday's 00:23 UTC primary time and eight-hour grace have elapsed.
2. The raw weekly snapshot has an exact, valid older collection date and its
   complete matching publication-window declaration. Future, missing,
   nonweekly or malformed snapshots are held, never repaired automatically.
3. The intended `refresh.yml` workflow is active. Disabled workflows are not
   enabled by the watchdog.
4. Complete paginated run history contains no active, queued, waiting or
   unrecognized-status discovery run from any week and no discovery attempt
   active at any point this week. Runs are not filtered by branch, event or
   conclusion. Reruns of older IDs are detected from start/update timestamps.

Any failed, cancelled or successful current-week attempt with a stale
snapshot is held for inspecting logs and recovery artifacts. A new search is
not used to repair a failed push. This **no-replay rule applies to the new
watchdog**. The existing Monday cron recoveries and explicitly requested
manual runs use the bounded initial/late-index closeout orchestration described
in `rolling-weekly-preparation.md`; they resume durable generations rather than
resetting completed searches. The watchdog does not reinterpret those attempts.

The proposed write is the normal dispatch endpoint with `ref=main`,
`mode=weekly`, and `only_if_due=true`. No credentials are created. The watchdog
needs repository `actions: write` only for dispatch and `contents: read` for
checkout; provider secrets remain in the existing trusted collection workflow.
PR verification receives no write token or provider secret.

The target workflow then checks out fresh main and repeats both the raw-window
and attempt-history checks under the existing `observatory-index` workflow
lock, excluding only its own verified dispatch run ID. Thus a late scheduled
run that succeeds, fails, is cancelled, or cannot push cannot be replayed by
this recovery request. If a concurrent successful collection wins the race,
no new provider requests occur. The watchdog has its own concurrency group,
so its read-only inspection does not delay collection writers.

The recovery's own run must be attempt 1. A second job-level guard also blocks
provider work on later recovery attempts, including GitHub's failed-jobs
rerun path that can retain a successful earlier preflight's outputs. A retry
of the recovery itself cannot masquerade as a missing initial launch.

The planner conservatively counts push/rebuild runs too: the run listing
alone cannot prove that a source step never executed. Publishing a change to
`refresh.yml` starts its existing rebuild workflow, so this patch's deployment
can itself make the watchdog hold for that collection week. Deployment is not
an immediate recovery action. Inspect any such run and use a separately
authorized normal manual weekly launch when appropriate; do not erase the
history or label a rebuild as a successful new collection.

A dispatch request is not a collection success. A failed API response or
uncertain result is never retried blindly. Verify the new run, its committed
strict publication window, source checks, downstream edition, and Pages
result before reporting completion. The existing source, reading, synthesis
and publication gates are unchanged, and completed closeout generations are resumed without resetting their cursors.
The accompanying orchestration deduplicates editions by the strict publication
window, without rewriting observation dates, source dates or existing issue IDs.

## Verification and activation boundary

Offline tests cover timing, UTC/year rollover, invalid metadata, disabled
workflows, complete pagination, API inconsistency, all completed conclusions,
older active/rerun IDs, other branch dispatches, and the locked race recheck.
The planner has no networking or dispatch code and modifies no input data.
The actual API dispatch exists only in the proposed workflow step.

This work is local preparation only. No job has been dispatched or retried,
no PR or remote commit has been created, and the previously denied early-week
readiness fix is untouched. Deployment requires its own normal review and
approval. Afterwards, verify the first actual scheduled run and its logs;
passing fixture tests alone does not establish hosted reliability.

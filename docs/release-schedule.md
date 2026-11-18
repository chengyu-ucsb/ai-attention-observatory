# Monday newsletter release

**Reader deadline: Monday at noon America/New_York.** The internal target is
a checked synthesis deployed and verified by **11:30 a.m.** A coverage-only
notice is a missed newsletter deadline, even if its build is green.

The website and this repository remain authoritative. Scheduled ChatGPT checks
supervise and repair the website pipeline; they do not create a separate edition
or replace the website-owned collection and publication jobs.

| Stage | Eastern time | Completion criterion |
| --- | --- | --- |
| Rolling collection and source reading | Throughout the week; final Sunday collection starts 4:17 p.m. | Sources, access failures, checked reading progress and retries saved |
| Supplementary web research | Wednesday, Friday and Sunday 6 p.m. | Search academic and news sources beyond feeds, follow emerging questions and record queries and candidate outcomes |
| Prepublication audit | Sunday 6 p.m. | Inspect source coverage, unresolved readings, model holds and the previous run's errors; resolve available blockers |
| Close the source week | Sunday 9:07 p.m. | Adopt the completed Monday–Sunday UTC publication window |
| Late-index sweep | Monday 2:07 a.m.; recovery 6:07 a.m. | Preserve existing work and collect delayed indexing without restarting the corpus |
| Final source reading | Monday 3:27 and 6:27 a.m., plus upstream completion triggers | Revalidate the exact evidence packet and retain explicit gaps |
| Compose and review | Monday 4:17, 7:17 and 9:17 a.m., plus final-reading completion triggers | Checked synthesis with source-linked claims and final review |
| Operational supervision | Monday 8, 10 and 11 a.m. | Inspect actual stage outcomes; repair actionable failures, not merely report them |
| Verify the public release | Monday 8:45, 10:45 and 11:30 a.m. | Live permanent page, RSS and JSON match the saved synthesis |
| Deliver the edition | Monday noon | Share the verified edition in the existing newsletter chat |

The source-publication week closes at midnight UTC, which is Sunday evening
Eastern. The 9:07 p.m. closeout is after that boundary in both winter and summer.
The six-hour late-index waiting period remains intact; the 2:07 a.m. sweep is
after that period in both seasons. The edition does not publish before Monday
starts in Eastern time.

## Time budgets and competing work

The bounded jobs allow up to 35 minutes for collection, 80 minutes for source
reading, and 60 minutes for composition and review. The plan reserves another
20 minutes for build/deployment and verification. The last pre-deadline drafting
start, 9:17 a.m., therefore leaves **83 minutes** before noon beyond those last
two processing budgets. Provider and runner delays can consume that buffer.

At 7 a.m., a compact edition may use the checked subset of at least two sources.
This moves the scope decision from 11:30 a.m. to the start of the release window;
it does not lower source-date, citation or factual checks. More sources remain
preferable when supported, and coverage limitations must be visible.

Follow [the research coverage procedure](research-coverage.md). The compact
option is a release contingency, not a research target. Check discovery and
reading completeness independently of the publication check; a verified page
does not establish sufficient coverage.

New-week preparation starts after noon on Monday. Monday's mid-morning discovery
resume, source-acquisition and bulk-backfill slots move after release. Existing
provider quotas, concurrency locks, checkpoints and bounded retries remain in
force. In-flight event-triggered work is not killed. Supervision must inspect
queue delays and source changes that can invalidate a draft.

## Failure handling

- An 8 or 10 a.m. supervision run investigates missing source material, held
  readings, incorrect genre classification, stale receipts and deployment
  errors. Use the existing repair/manual source-checked publication paths.
- A dated placeholder, an old issue, a green workflow that skipped composition,
  or a saved issue that is not live does not satisfy the deadline.
- `Verify Monday newsletter release` runs independently of acquisition and
  inference. It fails if the current saved synthesis and live page/feeds differ.
- The noon delivery reports a specific failure if synthesis is still missing.
  It must not present a coverage notice as the finished newsletter.
- The existing 12:05 p.m. fallback may publish an honest coverage notice. It is
  incident communication, not success. Recovery upgrades the same Monday URL.

These schedules are saved in GitHub and ChatGPT Automations. Exact start times
remain subject to the scheduling services; successful on-time operation must
be verified from the real Monday runs, not inferred from configuration or tests.

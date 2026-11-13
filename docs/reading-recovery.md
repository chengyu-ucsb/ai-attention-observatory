# Bounded reading recovery

Rolling collection keeps its existing 06:17/18:17 America/New_York schedule.
Recovery opportunities at 08:17/10:17/20:17/22:17 use the same worker lease and
validated current-week acquisition queue. They do not rediscover metadata or
attempt new acquisition routes. Source identity is still rechecked before
reading, so recovery can make source requests; it is not an offline review.
Idle, missing, stale, closed or exhausted queues do not load inference models.
GitHub scheduling is best-effort; these are not exact 15-minute timers.

Format failures receive at most two further attempts for unchanged selected
source metadata and reader revision, across dates. Intervening retrieval errors
do not erase the counter. This fingerprint is not a model-weight or document
hash: existing verified source-refresh reconciliation clears stale attempts.
Changing substantive source metadata or reader code permits a new bounded set.
Rejected evidence and copied prose retain normal holds, not fast retries.

Verifier partition errors now distinguish duplicate support/rejection,
overlapping decisions, missing indexes and out-of-range indexes using bounded
counts and booleans only. No source excerpts or raw model responses are saved.
All original evidence checks and the production prompt/grammar remain unchanged.

A local four-case synthetic probe of a proposed explicit-index grammar change
on the existing Qwen2.5-1.5B model still produced two overlapping verdicts and
one false rejection. The proposal was therefore not released. Diagnostics and
recovery scheduling do not establish successful article reading, factual
accuracy, or publication. Verify actual scheduled outcomes separately.

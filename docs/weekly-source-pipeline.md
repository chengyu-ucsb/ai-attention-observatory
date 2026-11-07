# Previous-week discovery and article acquisition

The collection week uses the site's existing UTC/Monday convention. Each weekly
run targets original publication dates in the preceding completed Monday–Sunday
week, inclusive. A run on any day November 2–8, 2026 targets October 26–November
1, 2026. It does not use a rolling seven-day period, first-seen date, registry
index date, or article modification date.

## Discovery is not full-text retrieval

Academic discovery searches the four research themes and the maintained venue
queries. Publisher-supplied original publication events take priority over later
issue/print dates. Incomplete, conflicting, or unverified dates stay in the
acquisition index with an unresolved status, outside the weekly set. Historical
DOI nominations and rotating historical queries run only in explicit backfill
mode. Original scholarly quality screening remains separate from date checks.

The nonacademic source register covers journalism, opinion, policy, and analysis
using twelve individually checked publisher feeds. Article category defaults are
provisional, not proof of evidence quality. Original RSS pubDate or Atom
published dates count; Atom updated and Google News index dates do not. Google
News results remain unverified leads until the publisher URL/date is established.
Known tracking parameters are removed for deduplication without discarding query
parameters that identify distinct articles. Conflicting original dates require
review and cannot be silently overwritten.

Provider pagination is bounded and audited. Finite feeds may not reach the
beginning of the target week; errors, rate limits, skipped requests, and truncated
windows remain visible. There is no claim to collect every relevant page on the
web. Paywalls, access challenges, unavailable originals, incomplete dates and
short feed archives remain real coverage gaps.

## Acquisition queue

`collect_weekly_sources.py` consumes only the current strict weekly snapshot.
It attempts scholarly and nonacademic sources independently of later publication
screening, using the existing bounded, identity-checked lawful retrieval path.
No account, model API, new credential, library access, or subscription is added.
Original document bytes and extracted prose stay transient. Metadata includes
source/version identity, text and byte hashes where available, observed page or
HTML coverage, exact retained chunk intervals, and unresolved provider outcomes.
Text coverage is not semantic, visual, scientific-quality, or publication review.

The queue resumes per record and source stage instead of restarting discovery or
repeatedly downloading completed unchanged sources. New source candidates reopen
a record. Request/time budgets, pending counts, rate-limit retry times and access
failures are explicit. An unavailable source is a completed search attempt, not
a collected article. HTML remains partial unless completeness is established.
An older related preprint cannot silently stand in for a current-week article.

The new workflow runs after weekly discovery and makes four bounded retry checks
per UTC day on that same weekly queue. It skips stale/missing weekly snapshots.
It records metadata only in `data/weekly-source-acquisition.json`, never paper
text, PDFs or inferred summaries. Publication and summary-quality approval remain
separate. Existing historical full-text recovery stays separate from this queue.

## Publication boundary

Every weekly selection stage rechecks original dates. Brief nominations and
source-lineage links cannot pull an older paper into the new-publication set.
Thin weeks are not padded with older context. The public issue and RSS state the
exact publication window. Earlier approved editions retain their historical
labels and content; a new collection rule does not rewrite them.

The library may still show earlier research. This is archival access, not a claim
that those articles were published in the current weekly window. A metadata-only
article remains excluded from substantive public readings until ordinary source
and quality gates pass.

## Verification

Offline checks use synthetic dates, feed fixtures and mocked retrieval. They
cover week/year boundaries, original-versus-updated dates, incomplete dates,
DOI/version identity, duplicates and conflicts, feed pagination and partial
coverage, retries, source-text nonpersistence, and publication/RSS boundaries.
They do not prove complete provider coverage or successful unattended synthesis.

```
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
node tests/validate_article_ui.cjs
node tests/validate_weekly_issue.cjs
node tests/validate_weekly_window.cjs
python scripts/collect_weekly_sources.py --known-sources-only --limit 3 --time-budget 180
```

The last command is a live retrieval operation, only valid after weekly discovery
has produced the current previous-week snapshot. Inspect the actual workflow
results before claiming deployment, retrieved-document counts, or scheduled
success. A green workflow is not itself evidence that each source was retrieved.

Acquisition checkpoints use a closed metadata schema and integrity check. Invalid
or legacy state is rejected before fetching or saving, rather than copied into a
public report. After a partial batch failure the workflow validates any saved
checkpoint, commits it without repeating retrieval, and retains a seven-day
metadata-only recovery artifact. Push races get three bounded rebase/push attempts;
conflicts fail visibly and leave the validated artifact for manual reconciliation.
Artifacts do not guarantee recovery from abrupt runner termination before a
checkpoint is written.

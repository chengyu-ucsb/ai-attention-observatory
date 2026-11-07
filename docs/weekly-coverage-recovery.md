# Weekly collection coverage and recovery

The weekly source set contains only articles whose original publication date is
in the previous completed Monday–Sunday week, interpreted in UTC. A modified,
indexed, first-observed or Google News timestamp is never substituted. Missing
or conflicting publication evidence is held out. Earlier archives remain separate.

## Short publisher feeds

Some publisher feeds retain only a few hours or days of headlines. A Monday-only
poll cannot recover entries that disappeared before Monday. `editorial_feed_cache.py`
therefore stages a small metadata index four times daily, before the weekly
collection. It keeps publisher title, canonical publisher URL, authors, exact
publication-date evidence, publisher genre tags and observation times. It does
not visit article pages or retain RSS descriptions, article bodies or PDFs.

The staging index is not the weekly library. Its current-week entries are not
retrieved as articles or published. `discover_editorial.py` admits staged items
only when their exact publication dates fall inside the next collection's
previous-week window. Cached candidates can survive a later live-feed outage.
The same date-conflict, deduplication, source-access and publication gates still
apply. Changed feed configuration invalidates old cached candidates.

The cache retains metadata observed within 28 days, reports pagination/budget shortfalls,
respects persisted provider cooldowns and does not automatically retry a 401/403.
Retry-After supports seconds and HTTP dates. Pages not reached in one run retain
a continuation URL. The next run revalidates the live advertised page chain from the root before reaching that cursor, so shifted intermediate pages are not silently skipped. Source budgets remain explicit.
All returned original-date evidence, including old or future contradictory dates, is preserved when the same article appears
with conflicting dates. The weekly collector marks it unresolved rather than
choosing whichever date fits the window. Compact conflicting-date markers survive
capacity trimming and later snapshots, so dropping an evidence row cannot silently
restore weekly eligibility. The closed metadata schema is also validated for
removed or changed source configurations before saving a checkpoint.

Four daily snapshots reduce losses; they cannot guarantee complete publishing
coverage. A busy feed can still roll over between polls. The collection reports
snapshot count and the largest unobserved interval during the publication week.
It never backfills imaginary observation history. A feed whose newest entry is
older than the target week is explicitly marked stale, not treated as evidence
that the publisher produced no relevant articles.

## Date and genre verification

Publisher RSS/Atom dates are declared publication metadata, not an independent
article check. Article-page verification can confirm exact original publication
metadata and explicit publisher genre labels. A general topic such as technology
or education does not establish whether an article is reporting or opinion.
Unverified outlet defaults remain provisional. No genre label certifies study
quality or peer review.

## Production boundary

`Preserve publisher feed metadata` is a bounded metadata-only workflow.
Article retrieval remains a separate strict-window stage. Neither a green cache
workflow nor an accepted citation means that a full article was retrieved,
reviewed, summarized or published. Check actual Actions run IDs and the durable
source reports before making any numerical coverage or deployment claim.

## Bounded academic continuation

`academic_state.py` checkpoints provider pages and their next cursors together,
so an interrupted library write can replay already fetched metadata without
losing a page. Provider-wide cooldowns honor Retry-After, and 401/403 stop further
automated access. Parameters and original-date evidence remain tied to the
exact query and publication window. `DISCOVERY_RESUME_ONLY=1` advances only a
previously established current-window plan; without one, it does not start a
new search. Old windows are retained for audit but cannot enter current weekly
recovery. Checkpoint metadata is in the public repository but is excluded from
the public website payload. It contains no credentials or full article text.

Completed queries are not continuously rescanned for late indexing. Cursor
completion means completion of the configured provider traversal, not exhaustive
literature coverage. Crossref's current cursors can persist across runs; OpenAlex
requires its free API key beyond the first cursor page. Existing repository
configuration is reused; no institutional access or new account is required.

## Scheduling and queue integrity

The snapshot workflow runs at 02:07, 08:07, 14:07 and 20:07 UTC; bounded discovery
recovery follows at :17 in those hours. GitHub can delay starts. Recovery does not
run before initial weekly discovery establishes the correct current window. It
uses staged feed metadata, advances existing academic cursors, verifies limited
publisher metadata, and rebuilds the source shelf. It does not generate an issue.

Writers share serialized repository access and use GitHub's supported `queue: max`
with `cancel-in-progress: false`, rather than silently replacing a pending job.
Rejected upstream events use separate skip groups. Pull-request verification
cannot start privileged downstream acquisition or deployment via workflow_run.

References: [GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency),
[Crossref cursor changes](https://community.crossref.org/t/changes-to-cursors-filtering-and-sorting-in-the-rest-api/16246),
[OpenAlex paging](https://help.openalex.org/api/paging/).

# Previous-week source acquisition

`scripts/collect_weekly_sources.py` is a metadata-only, resumable acquisition
stage. It consumes the selected academic and nonacademic records in
`data/weekly.json`, including records held by later quality screening. It does
not discover the web, generate model summaries, publish readings, or claim that
all articles on the web have been collected.

## Strict input dates

`run.publication_window` must contain the exact inclusive `from` and `to` dates
for the previous completed UTC Monday–Sunday week and `timezone: "UTC"`.
For any run on November 2–8, 2026, that is October 26–November 1. A missing,
rolling-seven-day, current-week, or stale window fails before any article fetch.
There is deliberately no historical-date override on this CLI.

Each selected item must pass the shared `collection_window.weekly_eligible`
original-publication gate. Legacy registry dates without sufficient provenance,
partial dates, unresolved dates, old Google News redirect metadata, updated or
first-seen dates, and historical-backfill records are not acquisition authority.
No quality score, abstract, existing model, or public-reading status is required.
The queue never substitutes an explicitly older candidate or a related preprint
for a newly published journal record. Date evidence remains metadata evidence,
not an independent investigation of every publisher's entire publication history.

## Run and resume

```sh
python scripts/collect_weekly_sources.py \
  --input data/weekly.json \
  --state data/weekly-source-acquisition.json \
  --limit 30 --time-budget 900 --item-time-budget 60 --max-candidates 8
```

For bounded verification without any DOI locator discovery:

```sh
python scripts/collect_weekly_sources.py \
  --input /tmp/verified-weekly-pilot.json \
  --state /tmp/weekly-pilot-acquisition.json \
  --known-sources-only --limit 3 --time-budget 150 --item-time-budget 45
```

Use only actual, verified input dates in a live pilot. Never change old article
dates to force eligibility. Keep live pilot inputs, results, and logs outside the
repository; do not commit real run outputs as code or test fixtures.

- A run advances at most `--limit` distinct records by one checkpoint each. A
  checkpoint is one known source or one existing anonymous locator plus up to
  `--max-candidates` of its returned sources. Repeated runs advance the saved
  per-record cursor instead of restarting at the first source.
- A fair queue cursor keeps capped records visible and gives unattempted records
  their turn on the next run. Remaining sources are `pending_routes`; counts and
  the run's limit/time-stop reason are saved.
- Each retrieval runs in an isolated process. The smaller of the item time cap
  and remaining run budget bounds that worker, which is terminated on timeout.
  Process cleanup and state-file writes add a small amount of overhead.
- Unchanged completed acquisition input is not fetched again. A change to the
  title, publication evidence, exact source URL, candidate version/route, source
  hint registry, or known-sources-only policy reopens it. A changed URL query
  affects the fingerprint but is never stored in the ledger.
- A successful whole-source extraction finishes retrieval for that record.
  Partial text remains explicitly partial, even after all routes are exhausted.
  `complete: true` means the current acquisition plan finished, not that the
  article was fully read, semantically checked, or approved for publication.
- Retryable failures preserve their checkpoint and `next_retry_at`. HTTP 429 is
  separate from temporary transport/server failure and permanent access blocks.
  Retrieval stops immediately after a 429, including nested publisher PDF and
  robots requests. Integer and HTTP-date Retry-After values are honored from
  response time. The actual failing article host is paused across known sources
  and different locators, as well as the current locator stage. Existing host
  cooldowns also apply to nested PDF links, robots requests, and redirect targets
  when their landing-page host differs. Skipping an already-paused host records
  `rate_limit_pause`, not a new HTTP response or permanent access denial. No account
  creation, credentials, CAPTCHA, or proxy workaround is attempted. Completed
  source-URL hashes prevent repeating permanent failures through other locators.
- A new week does not authorize fetching the old week's pending content. Its
  unresolved record metadata moves into `closed_windows`, with pending counts
  and an explicit separate-historical-backlog notice. It is not counted as
  completed and is not silently reclassified as new content.

The default locators reuse existing Europe PMC, OpenAIRE, CORE, and Semantic
Scholar functions with ordinary anonymous requests, only for a valid exact DOI.
DOI-less news finishes its known sources without scholarly locator calls. This
stage does not enable Unpaywall contact-email transmission or OpenAlex key-based
access. Direct OpenAlex/TEI routes and credential-bearing source URL queries are
rejected too. The same anonymous-source policy covers nested PDF links, requests,
and redirects, without stripping credentials and fetching a different resource.

Locator continuation uses exact URL hashes, not response offsets. Reordered
responses and newly inserted candidate URLs cannot cause earlier completed URLs
to be repeated or unseen URLs to be skipped. Each returned candidate passes the
same original-date, related-version, and credential policy as a known source.
This is not a frozen snapshot of all possible future routes.

## Rights and evidence

Article parsing reuses the established exact-identity checks, approved hosts,
robots policy, redirect guards, access-challenge rejection, and byte/page limits
in `full_document_access`. The optional `known_sources` argument on `retrieve`
restricts a call to its current checkpoint. This queue also uses
`anonymous_only=True`, a scoped policy inherited by nested requests and redirects.
Existing callers retain their default access policy.

Documents and PDF bytes remain in worker memory. Only numeric unit lengths,
chunk interval ranges, hashes, byte/page/character counts, source URL paths,
version labels, per-unit non-whitespace flags, and allowlisted status fields are saved. Unknown exception prose,
article paragraphs, source titles copied from retrieved bodies, credentials,
URL queries, and PDF bytes are not persisted. Writes are atomic, including a
checkpoint before retrieval so interrupted attempts can resume honestly.

The interval proof covers every character of the **retrieved** text, including
long documents beyond the old lede cutoff. It proves neither original-document
completeness nor semantic comprehension. HTML remains partial unless a separate
validated whole-source extractor establishes otherwise. PDFs retain physical
page/text counts with `semantic_completeness: "not_verified"` and
`review_status: "not_reviewed"`. `redistribution_granted` is always false in this
stage. Public accessibility does not authorize raw-text republication.

## Checkpoint validation and audit

Persisted checkpoints use schema version 2. `validate_state(state)` is a pure
offline validator returning the state or raising
`ValueError('invalid_acquisition_state')`. It neither fetches nor saves anything.
It validates a closed schema recursively, including archived/disposition rows,
allowed status values, sanitized URLs, hash syntax, exact chunk intervals,
physical-page counts, cursor bounds, completion evidence, and summary counts.
Whitespace-only PDF pages retain character coverage but are not counted as
text-bearing pages. An integrity checksum detects changed checkpoint bytes; it
is not an authenticity signature or independent proof of retrieval.

Every saved checkpoint is sealed and validated, including an interrupted
`in_progress` checkpoint. Old-schema or corrupt state is refused before any save
or source fetch; it is not silently reset, auto-migrated, or treated as a new
queue. Preserve such a file for manual review rather than overwriting it. The
earlier metadata-only pilot evidence remains historical evidence, not a v2
checkpoint to resume automatically.

Same-week records removed from input, newly excluded by date evidence, or
replaced with changed candidates retain their prior metadata in `dispositions`,
with the reason and observation time. Re-adding an unchanged completed record
can reuse that validated result without fetching again. Old-week unfinished
records remain separately visible in `closed_windows`. Neither disposition is
misreported as successful acquisition.

The fetch deadline covers the entire metadata IPC frame, not merely the first
byte. Parser output and stderr are suppressed in the isolated worker so raw
source fragments cannot leak through warnings.

## Tests

```sh
python -m unittest discover -s tests -p 'test_weekly_source_acquisition.py' -v
python -m unittest discover -s tests -q
```

Fixtures are synthetic and offline. They cover strict week boundaries and date
provenance, held records, cursor fairness, unchanged completion, changed versions,
partial HTML, PDF/chunk coverage, rate and access failures, provider backoff,
credential/exception redaction, killed workers, crash checkpoints, and old-week
pending metadata. They do not establish live source availability or summary
accuracy. Workflow scheduling/integration and its real run remain separate work.

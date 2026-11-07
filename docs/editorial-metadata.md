# Publisher original-date and article-type verification

`scripts/editorial_metadata.py` is a bounded metadata stage. It does not perform
feed discovery, resolve Google News redirects, retrieve article readings, call
models, save source pages, or claim comprehensive source coverage.

## Contract

```python
from editorial_metadata import parse_metadata, verify_record, process

# Pure metadata parsing and record verification, suitable for saved fixtures.
parsed = parse_metadata(html, publisher_url)
updated = verify_record(record, html, url=final_publisher_url, checked_at=now)

# Bounded resumable production operation. The original arguments are unchanged.
library, attempt_state, report = process(
    library,
    attempt_state,
    now=now,
    max_records=24,
    max_requests=60,
    deadline_seconds=90,
)
```

The optional fixture `fetcher(url)` returns `(html, final_url)`; one invocation
counts as one request. Do not use this hook to bypass production access rules.
The default fetcher counts robots requests, page requests, and each redirect
against the actual request budget. It reuses robots rules within a run, checks
the deadline before requests and body reads, caps each socket timeout at the
remaining deadline or 22 seconds, and limits HTML to 2 MB. Use a request budget
of at least two so an uncached robots check can be followed by a page request.

`process` attempts only nonacademic previous-week candidates and records with
no exact publication day. It skips known outside-week publications, scholarly
records, and historical-backfill records before any fetch. An undated lead's
page check is metadata verification, not a full-article retrieval.

## Evidence rules

- Match the requested record title against page title metadata or a matching
  Article JSON-LD node. An HTML title may include the exact named publisher.
  A general body mention of the title is insufficient.
- Validate canonical/OG URLs against the final page's exact host, path, and
  meaningful query identity. Identity-changing same-host redirects, cross-host
  redirects and mismatching canonical destinations require review.
  Tracking parameters are ignored for identity; other query parameters are not.
- Read `datePublished` only from the matching Article node, not unrelated
  recommended articles or WebSite metadata. Explicit publication meta fields
  include `article:published_time`, `datePublished`,
  `citation_publication_date`, `dc.date.issued`, `dcterms.issued`, and
  `parsely-pub-date`. Convert exact datetime values to UTC days.
- Never treat `dateModified`, feed `updated`, first-seen/index dates, a URL year,
  or partial dates as original publication dates.
- Preserve RSS `pubDate` and Atom `published` evidence if a matching page simply
  lacks publication metadata. This is reported as `publisher_feed_only`, not
  an independently verified page date. An explicit partial/invalid publication
  field creates unresolved original-day evidence.
- Any contradictory original dates, including a publisher date outside the
  current week, leave the record unresolved. Do not silently rewrite its stored
  date. Once contradictory or imprecise evidence requires explicit resolution,
  a later convenient matching response cannot clear that requirement.
- Only recognized explicit `articleSection`, `genre`, article type/section meta,
  or specific Schema.org article types can verify `source_type`. Recognized
  labels include Opinion, Analysis, Policy brief, Reporting, and their documented
  synonyms in the module. General topical sections and the publisher's identity
  do not establish genre. A provisional feed default can be strengthened;
  conflicting publisher item classifications remain visible as a conflict.
- Metadata verification does not establish methodological quality, full-text
  access, completeness, editorial review, or permission to redistribute.

## Access and retry policy

The network adapter uses the existing `full_document_access` user agent, host
allowlist, URL checks, redirect guard, and access-challenge recognition. It
passes an explicit copy of the approved hosts, so no wildcard/suffix allowance
can admit a new editorial subdomain. Every request must be anonymous HTTPS on
an exact approved host. Credential-like query parameters, embedded credentials,
nonstandard ports, and cross-host redirects are rejected. Robots rules precede
page requests and are rechecked for redirected page paths. Robots 404 permits
the request; robots denials and other failures do not. Publisher-declared
restricted access stops verification without fetching another route.

HTTP 401/403 and bot challenges stop that host for future runs in the saved
state. They require a reviewed state reset, not automatic alternate routes.
HTTP 429, 408/425, temporary server errors, and transport failures back off
across the host. Retry-After seconds and HTTP dates are honored without shortening
a longer server cooldown; an unrepresentable delay holds the host for review. No login, CAPTCHA solving, proxy, cached copy, or
paywall fallback is implemented.

Successful or terminal unchanged records are not refetched. An input fingerprint
change can reopen ordinary metadata checks but never an access-denied host.
Least recently attempted records are considered first so an early failed row
cannot starve the remaining queue.

## Persistence and production integration

Persist the returned library and durable `attempt_state` before
rebuilding `weekly.json`. The production CLI does this with atomic per-file replacements. Rebuild the weekly selection from the updated library
using `collection_window.weekly_eligible`; do not keep a stale pre-verification
weekly selection after a conflict or outside-window date is found.

Suggested separate files:

- `data/editorial-metadata-state.json`: durable attempts, fingerprints, sanitized
  source paths, terminal statuses, and host retry/backoff state.
- `data/editorial-metadata-status.json`: the latest report's current publication
  window, bounded requests/attempts, outcomes, and verified metadata counts.

The pure/library API returns these objects without writing files. The production
CLI writes these default files and the updated library. It does not alter
workflows. Do not publish the durable state as a current-week result. State can retain
historical attempts while the report counts only currently eligible records.
Only the module's closed state schema is retained on resume. Source bodies,
script contents, arbitrary exception messages, headers, credentials, URL query
strings, and fragments are never stored in this state.

Invoke after publisher discovery reconciliation and before weekly/full-article
retrieval. A separate bounded recovery invocation may call the same API with the
saved state; it must not rerun full discovery just to resume metadata checks.
The return report distinguishes metadata verification from full-article access
and contains no `full_articles_retrieved` claim.

The library's existing article readings and fields are preserved. Metadata
status is attached under `editorial_metadata`; verified original-day evidence
uses the existing accepted bases `publisher_datePublished` and
`publisher_meta_published_time`. Explicit genres use
`source_type_basis="publisher_structured_metadata"`.

## Bounded production command

```sh
python scripts/editorial_metadata.py \
  --max-records 24 --max-requests 60 --time-budget 90
```

Default destinations are resolved from the repository root, not the caller's
working directory:

- `data/library.json`
- `data/editorial-metadata-state.json`
- `data/editorial-metadata-status.json`

`--library`, `--state`, and `--status` can select explicit paths for a staged run.
The three destinations must be distinct. Record/request budgets are nonnegative
integers; the time budget is finite nonnegative seconds. Zero is a supported
no-request run. The first missing state file starts fresh without a prompt.
An existing malformed, unsupported-version, or structurally invalid state file
fails closed before network work so saved access stops are not silently erased.
Malformed retry timestamps or access-stop booleans also fail closed.

Before saving, the state is validated and reduced again to the closed schema.
All three JSON payloads are serialized before any replacement. Each is written
to a temporary file in its destination directory, flushed and fsynced, then
committed with `os.replace`. Save order is **state, library, status**. This is
atomic per file, not a transaction across all three files. Attempt fingerprints
include the resulting metadata status and verification time, so an interrupted
library save is detected and resumed even when the original date/type did not
change. Temporary files are removed if a write fails. A failed status save can
be repaired by rerunning without refetching unchanged successful records.

The command exits zero after a completed bounded batch, including budget stops,
backoffs, and publisher access refusals recorded in the report. It exits nonzero
for invalid inputs or persistence failures. Standard output is the metadata
report containing verified original-date and source-type counts and operational
request/budget outcomes. It does not claim full-article/full-text retrieval.
Failure output contains only a failure status and exception class, never source
bodies or arbitrary exception details.

Run this command **after cached publisher discovery and before `build_weekly`**.
Run the same bounded command for recovery without repeating external discovery.
Do not build weekly output from an earlier library snapshot after this command.

## Validation

```sh
python -m unittest discover -s tests -p test_editorial_metadata.py -v
python -m unittest discover -s tests -p test_editorial_collection.py
python -m unittest discover -s tests -p test_collection_window.py
python -m unittest discover -s tests -p test_weekly_source_acquisition.py
```

The dedicated suite uses fixtures and mocked HTTP only. A passing suite is not
proof that any publisher was checked live or that production wiring ran.

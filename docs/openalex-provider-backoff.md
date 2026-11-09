# Shared OpenAlex full-text backoff

The full-text workflow runs the OpenAlex XML stage before its licensed PDF
fallback. Both use the same provider allowance, so
`data/fulltext-backfill-state.json` controls both stages through its UTC
`quota_pause_until` value. This pause does not block independent providers such
as Europe PMC, Semantic Scholar, Unpaywall, or publisher HTML retrieval.

The PDF stage checks the shared pause before making a request or changing any
paper's attempt record. While paused it returns `waiting_for_budget`, makes
zero requests, and leaves the library and shared state unchanged. A 429 from
either the metadata lookup or the PDF download immediately stops the batch,
persists the shared pause, and marks only the attempted paper as `budget_retry`.
Completed earlier outcomes are retained; untouched papers keep their previous
attempt history and eligibility.

The PDF stage reuses the XML stage's existing reset calculation: use
`X-RateLimit-Reset` or `Retry-After` seconds, adding two minutes and waiting at
least one hour. If the value is absent, invalid, negative, or over one day,
wait until 01:00 UTC the next day. Retry timestamps include the time of day;
the deferred paper can resume when the pause expires, rather than waiting for
a generic two-day PDF error retry. Ordinary non-429 errors retain that two-day
per-paper retry and do not stop the rest of the batch.

PDF run statistics distinguish provider throttling from ordinary failures:

- `lookup_attempts`: metadata requests dispatched, including failed requests.
- `pdf_downloads`: the existing content-request attempt counter, including
  unsuccessful downloads. This name is retained for compatibility and does
  not mean the bytes were received or the article was recovered.
- `request_attempts`: the sum of metadata and PDF request attempts.
- `rate_limited`: the number of 429 responses, at most one per run.
- `errors`: non-quota failures.
- `fulltexts_recovered`: successfully extracted licensed articles, not requests.

Existing `python scripts/enrich_pdf_fulltext.py`, `run()`, API-key behavior,
lookup/download budgets, and license/extraction checks are unchanged.
`run(library_path=None, state_path=None)` optionally accepts isolated files;
without an explicit state path, the state file is adjacent to the chosen
library. Other XML-stage summary fields are preserved when the PDF stage
updates or clears the shared pause.

Offline regressions cover XML-to-PDF and PDF-to-XML pauses, metadata and content
429s, mid-batch interruption, preservation of untouched records, exact expiry,
ordinary network errors, missing state, and legacy no-argument budgets:

```bash
python -m unittest discover -s tests -p 'test_openalex_shared_pause.py' -v
python -m unittest discover -s tests -p 'test_pdf_fulltext.py' -v
python -m unittest discover -s tests -p 'test_backlog_and_publication.py' -v
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
```

These tests use synthetic responses and temporary data. They require no live
provider calls or credentials and do not demonstrate any new full-text coverage.

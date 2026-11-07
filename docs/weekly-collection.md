# Weekly publication collection

A weekly edition collected on any day of a UTC Monday–Sunday week covers the
**previous completed Monday–Sunday publication week**, inclusive. For example,
all runs dated November 2–8, 2026 cover October 26–November 1. The collection
`run.date` remains unchanged for compatibility. `run.publication_window` records
`from`, `to`, `timezone: UTC`, `inclusive: true`, and the scope
`original_publication_date_previous_completed_week`.

## Publication evidence, not discovery time

`scripts/collection_window.py` is the common gate used by scholarly discovery,
nonacademic discovery, and final weekly selection. It accepts complete calendar
dates and ISO datetimes (converted to UTC), rejecting unknown, partial and
invalid dates. It never fills an absent month or day with January or the first.

- Crossref metadata retains the original `published-online`, `published-print`,
  `published` and `issued` date parts. The earliest precise publication event
  wins. A later print/issue date cannot make an online-first paper new again.
- An imprecise or malformed publication event that could precede the selected day makes
  the original day unresolved. Registry `created`, `deposited`, `indexed` and
  update dates are never publication substitutes.
- DOI-backed OpenAlex candidates are checked against Crossref publication events
  before weekly admission, with lookup results cached within the run (recognized
  arXiv DOI identifiers use the official first-version route below instead). An earlier
  generic OpenAlex day conflicting with later publisher events is quarantined,
  never relabeled as Crossref evidence. Missing or
  failed original-date verification excludes that candidate from the weekly set.
  OpenAlex records without a DOI stay in the internal metadata quarantine until
  explicit original-publication evidence is available. Its generic provider
  publication date alone cannot certify the original week. Unverified records,
  including budget-deferred original-date lookups, are retained with no assigned
  original publication day and counted in `publication_date_unverified` and
  `publication_date_quarantine_records`; they do not enter the weekly shelf.
- Recognized arXiv identifiers use official Atom metadata with an exact `id_list`
  query pinned to `v1`. The returned versioned identifier and normalized full
  title must match; a changed first-version title is held for review. Only
  `published`, never `updated`, determines the original day. No Atom summary or
  article text is saved by this verifier. Calls are serial, at least three
  seconds apart, cached by identifier, and capped at 20 requests per run.
  Provider failures, title/version conflicts and budget deferrals are counted.
  General DataCite and Zenodo original-date verification is not implemented;
  those records remain quarantined rather than receiving inferred dates.
- Legacy Crossref/OpenAlex records and scholarly DOI records without precise
  original-date provenance require refreshed date evidence. Legacy automated feed records similarly require original publication
  provenance; Google News redirect URLs are not accepted as canonical weekly
  sources. Direct publisher feeds use published/pubDate, never Atom updated.
- First-seen dates, current index timestamps, editorial nominations, and a
  curated flag cannot override publication boundaries. Historical records remain
  available in the internal library without entering the weekly publication set.

These are bibliographic source checks, not verification of study quality or
findings. Citation-only metadata still cannot appear as a substantive public
reading. Unknown dates reduce coverage rather than being guessed.

## Scholarly query coverage and its limits

Weekly search runs all 12 thematic queries across four lenses against OpenAlex
and Crossref, plus all eight configured recognized-venue queries. Each provider
query is bounded by five pages of 100 results by default. The DOI original-day
verification pass has a separate 100-lookup Crossref budget and a 20-request
arXiv budget. These are API/resource bounds, not editorial selection caps.

`stats.provider_windows` and the corresponding priority/journal statistics
record provider, query, filter, page count, records seen, provider total, page
budget, status, and truncation reason. Repeated/missing cursors, inconsistent
short pages, exhausted budgets and provider failures are surfaced rather than
being silently treated as exhausted search results. Quota failures defer the
remaining provider work. Original-date lookup deferrals are counted. A partial
provider run produces `discovery_status: partial`; even `complete` means only
that the configured provider queries finished, never that all web or academic
publications were found.

All eligible discovered records survive final weekly selection. Theme
interleaving no longer silently drops records after 36 or discards records
without one of the four standard lane labels. Broader retrieval can still miss
sources due to search vocabulary, provider indexing delays, unavailable source
metadata, access restrictions, or the declared budgets. No all-web completeness
claim is made. No embedded personal email is sent in these Crossref queries.

## Separate historical acquisition

`MODE=backfill` searches the historical matrix from 2023 and verifies nominated
older DOI leads. It writes the acquisition library and run audit without
replacing `weekly.json`. Weekly runs do not rotate historical years, retrieve
old priority DOI nominations, or widen a date window after an empty result.

The nonacademic collector owns news, opinion, policy and analysis discovery.
The old competing Google News loop in `update.py` has been removed so that
there is a single source-specific publication-evidence policy.

## Offline checks

Run the focused tests without API calls:

```sh
python -m unittest discover -s tests -p 'test_collection_window.py' -v
python -m unittest discover -s tests -p 'test_academic_weekly_collection.py' -v
python -m unittest discover -s tests -p 'test_arxiv_publication.py' -v
python -m unittest discover -s tests -p 'test_priority_research.py' -v
python -m unittest discover -s tests -p 'test_search_plan.py' -v
python -m unittest discover -s tests -p 'test_pipeline_status.py' -v
```

Then run `python -m unittest discover -s tests -v` and
`python -m compileall -q scripts tests`. Passing these checks establishes the
fixture-backed behavior, not a successful scheduled live collection. Inspect
the next authorized run's provider audits and saved window before reporting
actual retrieval coverage.

## Provider documentation checked

- [Crossref date fields](https://github.com/CrossRef/rest-api-doc/blob/master/api_format.md) distinguish publication events from registration, metadata deposit and indexing.
- [Crossref date filters](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/) support publication-day filtering; client-side evidence checks remain necessary because source dates may be partial.
- [Crossref pagination guidance](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/) describes cursor traversal and stopping conditions.
- [Official arXiv API manual](https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md) documents `id_list` version pinning and the distinction between `published` and `updated`.

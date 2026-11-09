# Reusing acquisition receipts in the reading stage

`scripts/acquisition_handoff.py:retrieve_for_reading` is a drop-in retrieval
callback for `comprehensive_readings.process`. It returns the existing
`(Document, diagnostics)` shape. It does not generate a summary, save source
text, change a reading's approval, or publish anything.

## Receipt binding

The adapter reads the metadata-only weekly acquisition checkpoint and its
matching weekly source snapshot. The checkpoint must pass the existing closed
schema and checksum validator. Its publication window, duplicate-aware input
fingerprint, known-route hashes, DOI, normalized exact title, original URL,
publication date and substantive date provenance must still match the current
article. Only the current-vs-weekly observational `checked_at` timestamp is
ignored; the exact checkpoint-to-weekly fingerprint still includes it. A fresh
feed check cannot erase a valid receipt or rewrite its original observation.

A valid saved document supplies its source URL and recorded document version as
the first known location. It supplies no license grant and no source prose. The
normal reader fetches that source afresh through the same exact-host, robots,
redirect, article-identity, structured-license and size guards. Saved HTTP
401/403 host/provider denials and exact-URL route denials are not replayed.
They remain effective across metadata mismatches and other records in the current
checkpoint. Active host/provider cooldowns also remain in force, including nested
PDF, robots and redirect requests.

Before a returned document can inherit the receipt reference, its text hash,
byte hash/count where recorded, version, extraction status and HTML-parser
revision must agree. A changed document, version or redirect is held with an
explicit diagnostic. HTML remains partial. A returned independent source keeps
its own version, source URL, hashes, coverage and license metadata; it never
inherits the old source's receipt.

Verified arXiv first submissions remain pinned to their exact v1 URL, including
when no receipt is available. Unversioned aliases, newer versions and unverified
first-version metadata cannot be substituted. This does not declare a preprint
peer-reviewed or equivalent to a later journal article.

Revalidated documents contain only receipt hashes and
`acquisition_receipt_status: revalidated_not_reviewed` in their coverage metadata.
Neither a matching hash nor complete text extraction is semantic review,
redistribution permission, or publication acceptance.

## Missing and stale metadata

Unrelated/missing receipts use ordinary retrieval, subject to the first-version
rule above. Active global host/provider cooldowns from a valid checkpoint still
apply even when a particular receipt no longer matches or its weekly snapshot is
missing. A corrupt checkpoint is held without network I/O rather than silently
reset or treated as trusted evidence. Changed weekly inputs do not inherit an
old receipt. Historical metadata is not relabeled as a new weekly acquisition.

A source whose content changed needs a fresh acquisition receipt or independent
source review. This conservative check may defer a harmless publisher re-encoding
or parser update; it never silently carries prior version evidence onto new bytes.
No full text cache or public raw-document storage is introduced.

## Integration and tests

Explicit handoff holds raise a stable `ValueError` in the public callback. The
existing reader records a retrieval-stage failure without falling back to stale
indexed sections or invoking synthesis. Ordinary source misses still return the
normal pair and may use the separately labeled partial-section fallback.

The module can be used as the default `retriever` in
`comprehensive_readings.process`. Callers can continue injecting offline test
retrievers. Its queue import is lazy so the queue's shared chunk-coverage helpers
do not create an import cycle. The adapter has no scheduling or publication side
effects; wiring it into a recurring workflow is a separate integration step.

`tests/test_acquisition_handoff.py` covers current-input binding, duplicate route
plans, source changes, HTML partial status, arXiv v1, host/provider cooldowns,
recorded and new denials, robots and article identity, renewed XML license
checks, and the existing summary/publication boundary. Fixtures are synthetic
and all source requests are mocked; these tests establish workflow behavior,
not future source availability or model-summary quality.

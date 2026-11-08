# Article retrieval review, 8 November 2026

## What changed

The whole-document reader now uses exact-DOI Crossref publisher deposits in
addition to its existing official XML, OpenAIRE, Unpaywall, CORE, Semantic
Scholar, author and repository routes. It discovers PDF/HTML locations without
mistaking a link for access or permission. It also retains OpenAlex's open
repository locations when its cached XML is missing, using the same API response.

Source attempts are now shared across providers: rejected hosts do not consume
the document budget, each provider gets one initial attempt, and remaining
locations are revisited if budget remains. A host's 401/403 response stops further
requests to that host in the retrieval run; Retry-After pauses also apply to
nested PDF requests. Independent hosts remain eligible. PDF typography such as
`ﬁ`/`ﬄ` is normalized without fuzzy title matching or relaxing identity checks.

## Measured access outcomes

The checked-in JSON audit contains source URLs, exact identifiers, version labels,
hashes, diagnostics and counts. No source prose or PDF bytes are included.

- Microsoft Research knowledge-worker survey: 23 of 23 pages yielded text.
- LMU-hosted *Cognitive ease at a cost*: 7 of 7 pages yielded text.
- IJLTER mathematics/creative-metacognition study: 33 of 33 pages yielded text.
- Frontiers overreliance/GenAI-feedback study: 21 of 21 pages yielded text.
- EFF's *Tech Tips for Parents*: 27 article blocks retrieved, still conservatively
  labeled partial HTML because whole-source equivalence is not independently verified.
- Springer nursing study: robots access unavailable/disallowed in this executor.
- Europe PMC language-instruction XML: temporary HTTP 500; not retried immediately.

The new Crossref path retrieved Frontiers and IJLTER with the curated source
registry deliberately disabled. This verifies a working new route, not a claim
that these papers were previously absent everywhere. Four distinct complete-text
retrievals were obtained across seven document-test records. **No new completed
summary or public reading-count increase is claimed by this access audit.**

For the latest *CogOffload* paper, the publisher PDF returned HTTP 403. Crossref
and Semantic Scholar identified that same publisher; Europe PMC, OpenAIRE and
CORE returned no exact candidate. OpenAlex was unconfigured in this executor,
and Unpaywall lacked an explicitly configured contact address. These are
separate outcomes, not evidence that no free copy exists.

## Requested broader sites

LibGen (`libgen.rs`) and Anna's Archive (`annas-archive.org`) were explicitly
checked through the web tool. Both returned non-retryable open errors. No source
was retrieved or verified through either, and no rotating mirror network was
used. Search-result mentions and an accessible index would not by themselves
verify an article's identity, completeness, version or reuse rights.

## End-to-end boundary

Retrieval, extraction completeness, synthesis, evidence checking and public
publication must remain separate. The production whole-document workflow has a
small two-record budget twice weekly. This change passes the same existing
OpenAlex provider secret used by research backfill to its trusted scheduled/manual
reading step; PR tests receive no secret. No credentials are created or expanded.
Successful source access alone cannot repair a
weak summary or promote a pending reading. The separate summary work should
consume complete source packets, preserve page/section provenance, keep measured
results separate from interpretation, and publish only after evidence validation.
The existing successful-main workflow completion already triggers public-payload
rebuilding and Pages publication; this change leaves those gates intact.

Before the workflow edit, official releases were checked: checkout v7.0.1 and
setup-python v7.1.0 both use Node 24 and require runner v2.327.1 or later.
The existing v7 references and GitHub-hosted Ubuntu 24.04 runner were retained.
A completed production run remains necessary to verify live secret availability,
model results, warnings and publication after integration.

## Provider contracts

- [Crossref: accessing full texts](https://www.crossref.org/documentation/retrieve-metadata/rest-api/text-and-data-mining-for-researchers/)
  explains deposited links, version/purpose metadata and independent publisher access limits.
- [OpenAlex: location objects](https://help.openalex.org/data/locations/)
  documents PDFs, landing pages, versions and the distinction from cached content.
- [OpenAlex: open access](https://help.openalex.org/data/works/open-access/)
  distinguishes readable locations from license metadata.

This is a bounded reproducible engineering audit, not an exhaustive search of
all websites or a guarantee of universal access. Do not copy restricted source
text into the public repository. The original rights, robots, identity, source
quality, publication-date, version, and summary gates remain in place.

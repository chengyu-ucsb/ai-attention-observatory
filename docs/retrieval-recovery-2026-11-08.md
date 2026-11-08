# Targeted source recovery, 8 November 2026

The relevant backlog is 23 screened scholarly records without a full-text reading,
not every one of the 556 scholarly items in the discovery index. This pass
retrieved three new complete PDFs for those pending records. A complete PDF
retrieval is not a completed summary or publication approval.

## Recovered sources

- **Notification batching** (10.1016/j.chb.2019.07.016): 11/11 pages and 60,719
  extracted characters from the publisher-format copy linked by the author's
  [publication list](https://www.kushlev.com/research). Publisher copyright is
  retained. The shared asset CDN is approved only for this exact reviewed file.
- **Reflective-learning dashboards** (10.14742/ajet.11584): 18/18 pages and 60,832
  characters from the [publisher](https://ajet.org.au/index.php/AJET/article/view/11584).
  Crossref's old PDF identifier 2331 returned 404; the landing page declared the
  current PDF 2341, which the reader followed without guessing an alternate URL.
  CC BY-NC-ND 4.0 is recorded. The PDF itself inconsistently says 42(5) in its
  header and 42(4) in its citation; no silent bibliographic correction was made.
- **Reliable GenAI scaffolding** (10.1016/j.compedu.2025.105448): 19/19 pages and
  103,390 characters from [Monash's final published version](https://research.monash.edu/en/publications/towards-reliable-generative-ai-driven-scaffolding-reducing-halluc/),
  CC BY 4.0. Online publication is 2 September 2025; its journal-volume year is
  2026. The original date is preserved.

All three have exact-title/DOI evidence, source links, version labels and content
hashes. All PDF pages yielded text; visual table/figure fidelity and supplements
have not been checked. No PDFs or whole-source prose are stored in this repository.
`data/retrieval-recovery-audit-2026-11-08.json` is metadata-only evidence.

## Operational repairs

The weekly acquisition worker previously omitted Crossref even after the reader
supported it. Crossref is now appended after the existing four providers. Old
checkpoints remain valid under their original provider plan. Only selected,
unchanged current-week records migrate to the new plan, preserving denied-source
history, fingerprints, cursors, pauses and already successful documents. Exhausted
non-full records receive only the new route, not a replay of old requests.
Completed legacy HTML rows with parser-refresh history retain their original
provider plan and evidence until a separate provenance-safe migration is available.

HTTP-200 pages titled "Site Unavailable" are now distinguished from incorrect
article identity. They receive a one-hour cooldown; another same-host location
is not immediately tried. The pause survives separate weekly candidate calls and
is checkpointed for later records without pausing independent locator APIs.
Publication, identity, rights and historical-date gates
remain intact. The access pilot includes the three recovered copies and retains
previous portal 401/403 outcomes without reprobing them on every code push.

## Remaining access limits

Fourteen exact-DOI OpenAIRE searches yielded no additional independent copy.
Four ScienceDirect HTML tests returned a tiny unavailability page, not article
text. SAGE returned 403 and subsequent same-host URLs were skipped. De Gruyter
responses did not verify the requested document identity. AISeL, LIUC and OSF
returned 403; MDPI returned 429. UCI's historical interruption paper was readable
through the web tool but the automated reader stopped at its robots check. These
are distinct failures, not evidence that no copy exists anywhere.

The requested LibGen and Anna's Archive domains had already returned
non-retryable web open errors in this task. Targeted index searches produced no
verified exact copy; no mirror network or access-control workaround was used.
Other free routes included institutional repositories, author sites, publisher
OA pages, official bibliographic locators and author-upload aggregators.

One apparent missing article (10.1093/arclin/acag065.178) is a one-page conference
abstract; no longer paper was identified. A separate citation-only item
(10.1007/s12528-026-09507-2) has a substantive university-hosted abstract, but not
retrieved full text. Neither is counted as a full-paper recovery. The audit lists
all 23 targets and the specific checks, rather than claiming universal access.

# Full-article access and reading-quality audit

Updated: 2026-11-05. This is the canonical audit note; update this file rather than creating parallel copies.

## November 5: reusable acquisition workflow

`scripts/retrieve_articles.py` now accepts a DOI/title bibliography and retrieves documents without loading a language model. It checkpoints each article, records provider and source failures separately, retains version and identity evidence, and skips completed unchanged inputs on a later run. A new verified candidate reopens the corresponding record. Temporary provider failures receive a shorter retry interval than an unresolved search.

The reusable input is a JSON list, or an object with a `records` list. Each record needs `title`, plus a DOI or exact source URL when available. Optional `projects` tags allow one article to serve several projects without duplicate retrieval. `fulltext_candidates` can supply independently verified source URLs. Outputs must be outside this public repository. The command stages files; the caller must verify saving to its authoritative private cloud destination before delivery.

```bash
python scripts/retrieve_articles.py /private/project/input.json \
  --report /private/project/retrieval-results.json \
  --stage-pdfs /private/project/papers \
  --limit 12
```

Use `--known-sources-only` to test supplied/registered sources without locator API calls. `--force` deliberately repeats records, for example after correcting a source relationship. The report preserves attempt counts, input fingerprints, next actions, retry dates, source and byte hashes, physical page counts, and limitations. PDF staging is explicitly labeled as awaiting verified cloud saving; it is never reported as an automatic cloud sync.

### Changes supported by actual retrieval

- Known source URLs, `open_access_url`, and DOI-less arXiv records are tried before locator APIs. `data/fulltext-source-hints.json` supplies verified alternatives for existing Observatory papers.
- OpenAIRE is an additional exact-DOI locator. A live lookup for `10.1016/j.chb.2024.108386` produced several repository alternatives; the LMU Munich PDF worked after other routes failed. The adapter checks the publication's own DOI, not identifiers found in its references, and handles singleton/list response structures.
- Complete PDF text is preferred when available. If all sources remain partial, the richer partial extraction is retained; a mostly scanned PDF does not displace substantial HTML simply because it is a PDF.
- Changed-title arXiv versions require a live metadata check of the related journal DOI, source title and arXiv identifier. The earlier version is labeled separately from the journal article.
- Source manifests and saved reading URLs remove query credentials. `UNPAYWALL_EMAIL` must be explicitly configured for the newer reader; no personal contact address is supplied implicitly. Other providers continue independently when that provider is unconfigured or unavailable.

The November 5 bounded live test retrieved these five Observatory documents through the same acquisition command:

| Paper | Successful source | Physical PDF pages | Version qualification |
| --- | --- | ---: | --- |
| The Impact of Generative AI on Critical Thinking, `10.1145/3706598.3713778` | Microsoft Research | 23 | Author-hosted conference version |
| AI makes you smarter but none the wiser, `10.1016/j.chb.2025.108779` | arXiv `2409.16708v2` | 27 | Earlier title: Performance and Metacognition Disconnect when Reasoning in Human-AI Interaction; not the final journal version |
| Knowing (Not) to Know, `10.1287/isre.2024.1431` | EconStor | 89 | Working paper, not the journal version |
| Cognitive ease at a cost, `10.1016/j.chb.2024.108386` | LMU Munich | 7 | Published version |
| AI Tools in Society, `10.3390/soc15010006` | MDPI, located through DOAJ | 28 | Published version |

The Taylor & Francis route for `10.1080/10494820.2026.2744894` remained blocked. These six selected papers are a route-validation set, not a random sample or corpus-wide success rate. The historical `full_text_extracted` total is unchanged by this acquisition-only command. Retrieved text has not automatically become a reviewed article summary. Figure, table, supplement and semantic completeness checks remain separate.

The larger private test bibliography and its document files belong to the private research workspace and are not included in this repository. Reusable code and public Observatory source hints remain here. Offline tests cover resumability, identity mismatch, multiple-project deduplication, provider failure isolation, partial-source selection and private-output boundaries.

## Implementation status

The production reading changes were merged into `main` through [PR 25](https://github.com/chengyu-ucsb/ai-attention-observatory/pull/25), squash commit `83f3726e4008253aca03a26b1587c31c3416f995`. The scheduled `Deepen source readings` workflow now invokes `scripts/comprehensive_readings.py` rather than the old truncated-input reading step.

The implementation is installed and its offline tests passed. This is NOT a claim that the entire acquisition backlog has been reprocessed, that a new comprehensive summary has completed end to end, or that generated summaries have been independently reviewed. Existing newsletter editions were not rewritten as part of this change.

## Alternative access tests: observed results

The machine-readable report is [data/fulltext-access-tests.json](../data/fulltext-access-tests.json). The report inspected for this update was checked at 2026-11-04T08:02:52Z. It tests two exact journal DOIs and a small number of direct public routes, not all articles on each service:

- `10.1287/isre.2024.1431`: Knowing (Not) to Know: Explainable Artificial Intelligence and Human Metacognition.
- `10.1080/10494820.2026.2744894`: ChatGPT as cognitive scaffold: computational thinking and metacognition in AI-embedded instruction.

| Service | Observed result | What it establishes |
| --- | --- | --- |
| Unpaywall | Three distinct locations for the INFORMS paper, including the EconStor PDF and SSRN; no candidates for the Taylor & Francis test paper | Useful exact-DOI and version-aware discovery, not automatic full-text access to every location |
| EconStor | The working-paper PDF was retrieved, its title verified, and text extracted from all 89 pages | A demonstrated cloud retrieval route without institutional authentication |
| Semantic Scholar | Returned an SSRN location for the INFORMS paper; HTTP 429 for the other test paper | A useful locator with rate-limit constraints, not a universal PDF provider |
| CORE | API responded, but no exact-match candidates for these two DOIs | This small test produced no additional usable location; not evidence that the service has no relevant papers |
| ResearchGate | HTTP 403 from the runner; an earlier interactive/indexed page displayed no downloadable file and an author-request option | No full article was obtained through this tested route |
| SSRN | HTTP 403 from the runner | A locator exists, but a complete document was not retrieved from SSRN in this test |

The EconStor result was 198,047 extracted characters across 89 pages, divided into 37 chunks with exact coverage of all retrieved text. The report explicitly records `working_paper_not_journal_version`, `tables_figures_visually_checked: false`, `supplements_checked: false`, and unverified layout/semantic completeness. Retrieval is not a completed article review. Raw PDF bytes and extracted passages were not saved to the repository.

The earlier public probe, [run 41778534923](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/41778534923), also retrieved the EconStor document while direct INFORMS, Wiley, and Taylor & Francis requests returned 403 from that runner. Availability differs between an interactive reader and unattended cloud requests.

### Supplied Reddit discussion

The requested short link was `https://www.reddit.com/r/research/s/NotSVRW5kg`. It could not be read with the available web route. A separate unauthenticated cloud check, [run 41794582800](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/41794582800), returned HTTP 403 and no comments. The exact recommendations in that thread remain unverified. The services tested above must not be attributed to that thread without its contents.

## Installed changes

### Separate reading access from public redistribution

`scripts/full_document_access.py` adds exact-identifier Unpaywall, CORE, and Semantic Scholar lookup with provider-failure isolation. It keeps both PDF and landing-page alternatives, document-version metadata, and up to eight candidate attempts. It supports explicitly approved repositories including EconStor and named university repositories. It does not accept arbitrary hosts or treat a license value as blanket redistribution permission.

Retrieved documents remain in memory. The module checks HTTPS, hosts, redirects, response size, robots rules, article identity, and challenge-page indicators. Authentication barriers are not bypassed. Cross-host redirects that need additional review remain blocked; not every DOI or handle landing link is automatically usable.

PDF extraction processes every page up to an explicit document budget. Larger documents are deferred, not silently shortened. HTML is conservatively labeled partial when completeness cannot be established. A readable document is separate from permission to retain or republish its text.

### Eliminate silent summarizer input truncation

`scripts/comprehensive_readings.py` processes all retrieved text in bounded chunks rather than feeding only the first approximately 16,000 characters. Page/paragraph labels and character ranges are preserved and checked for gaps. Exceeding the chunk or time budget defers the document rather than publishing a shortened reading as complete.

Fallback to already retained article sections is explicitly partial, because upstream extraction may have omitted text. Conceptual articles and reviews do not universally require an empirical Results field. Partial inputs remain eligible for fuller retrieval on a later permitted attempt. Existing source-checked notes are preserved, and a partial candidate does not overwrite a prior complete reading.

### Check claims rather than two phrases per article

Each generated claim requires a matching source anchor, supported numerical tokens, and a check against long copied sequences. A second model pass compares every proposed claim with its original source segment. Output retains original paraphrases, page/paragraph ranges, and anchor hashes, not source quotations.

These checks are safeguards, not a guarantee of truth. The model is still the existing on-runner Qwen2.5-1.5B model. Its second pass is not independent editorial review. Outputs carry `machine_checked_not_independently_reviewed` and explicit coverage limitations. Figures, tables, equations, and supplements are not claimed to have been visually verified.

### Validate before changing production

Added 16 offline regression tests in `tests/test_complete_source_reading.py`. The full suite ran 180 tests successfully, including tests for long-document tails, interval coverage, unsupported numbers, evidence anchors, copying, conceptual text, partial inputs, provider failures, unsafe hosts, and source-text nonpersistence. Existing article UI and weekly-issue checks also passed.

Final pre-merge verification: [run 41796331846](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/41796331846). These offline tests use controlled model outputs and do not establish real-model summary accuracy. The live access tests separately measure actual retrieval outcomes. A successful diagnostic workflow does not mean all tested providers returned documents.

The existing scheduled workflow now processes at most two documents per run using the new reader. Code and diagnostic reports are saved in this repository. No paid hosted inference service, new account, or institutional credential was introduced.

## Historical baseline, not a newly measured recovery total

The [November 4 retrieval run 41753343863](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/41753343863), before these changes, reported:

- 423 scholarly records in the internal acquisition inventory.
- 147 with at least some machine-extracted full-text sections.
- 1 separate original full-article synthesis.
- 275 without full-text sections.

The same run reported 69 public readable records and 33 full-text-labeled canonical readings. The internal inventory and screened public collection use different denominators. Extracted sections are not equivalent to comprehensive reviews.

Among the 275 unresolved records, independent-repository statuses were: 90 license_unverified, 31 pdf_host_unapproved, 103 no_oa_pdf_reported, 27 provider_incomplete, 20 not_tried, and 4 pdf_unreadable_or_blocked. These historical counts must not be described as current recovery performance after the new reader was installed.

## Remaining work and limitations

1. A corpus-wide reprocessing and independent comparison of real generated summaries with complete source documents has not been verified. New tests do not establish that every article is recoverable or every claim correct.
2. Visual inspection of relevant tables, figures, formulas, appendices, and supplements is not implemented by the text-only reader. Text coverage cannot certify their interpretation.
3. The existing public renderer and historical evidence labels have not been comprehensively migrated. New coverage metadata does not automatically upgrade every abstract-only record or historical edition to a fully reviewed article.
4. Zotero remains a scoped availability diagnostic, not a production full-text ingestion/summarization path. Its current private collection and indexed-page completeness were not inspected here. Institutional access was not established.
5. Publisher-authorized text-mining access, institution-supported document delivery, and author-supplied manuscripts remain separate options to investigate or authorize. No requests were sent to authors and no subscriptions or accounts were created.
6. Some otherwise legitimate landing-page redirects are intentionally held for review. Identity/version checks should be improved with verified relationships, not disabled to force a success.

The most concrete result is now a tested chain: exact-DOI discovery can identify a repository alternative, the cloud runner can retrieve that document, and the new chunking path can preserve its entire extracted text. Whether a subsequent generated reading is accurate still needs source-level evaluation.

## Documentation and source locators

- [EconStor working paper](https://www.econstor.eu/bitstream/10419/334511/1/1947737333.pdf)
- [INFORMS journal article](https://pubsonline.informs.org/doi/10.1287/isre.2024.1431)
- [CORE API](https://core.ac.uk/services/api)
- [OpenAlex full-text and structured content](https://help.openalex.org/access/fulltext/)
- [Crossref full-text/TDM locators](https://www.crossref.org/documentation/retrieve-metadata/text-and-data-mining/)
- [Zotero indexed full-text and coverage API](https://www.zotero.org/support/dev/web_api/v3/fulltext_content)
- [UCSB Library text and data mining support](https://guides.library.ucsb.edu/text-data-mining/home)

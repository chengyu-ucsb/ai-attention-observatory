# Full-article access and reading-quality audit

Updated: 2026-11-06. This is the canonical audit note; update this file rather than creating parallel copies.

## November 6: free-source routing and structured full text

The current acquisition inventory at commit `79f123cd6ea561763c815f3f022b4d13a094904f`
contains 423 scholarly records: 156 with machine-extracted sections, one separate
editorial full-article synthesis, and 266 without either. These categories do not
mean 157 completed whole-document reviews.

The latest [production deep-reading run](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42284828976)
attempted two records and completed zero summaries. It retrieved zero new source
documents, fell back to two partial indexed inputs, and rejected output for
`claim_length_invalid` and `copied_source_passage`. The green workflow exit is not
successful article synthesis. No quality gate is weakened by the changes below.

### Sources actually opened through the web reader

Eleven records previously missing extracted full text have verified, free,
source-hosted PDF routes in `data/free-access-candidates.json`. Both publisher PDFs
and all nine exact versioned arXiv PDF URLs were opened successfully through the
web reader, with page counts and article identity checked. This is **not** a
production-runner download, parser-coverage test or completed summary:

- BMC Nursing `10.1186/s12912-026-05512-z`: the publisher's actual Download PDF
  points to an 18-page `_reference.pdf`, explicitly an article-in-press version
  under CC BY 4.0. Guessing the ordinary `.pdf` URL misses this route.
- IJLTER `10.26803/ijlter.25.10.23`: the official OJS viewer links to a 33-page
  article download without a `.pdf` filename suffix. Its CC BY-NC-ND 4.0 terms
  are not permission to store the source body in the public repository.
- Nine arXiv records include three with empty DOI fields. Their 16–53-page PDFs
  can be addressed directly by arXiv identifier. Version-pinned routes preserve
  the matching source title: `2609.24616v1` is the 21-page version matching the
  indexed title; v2 has a different title and 24 pages and is not silently
  substituted. Preprint access does not establish peer-review status.

The metadata-only source register now includes these routes. Restricted or
nonexclusive redistribution licenses remain distinct from transient reading and
original factual paraphrase. No source PDF, extracted body, private credential or
model response is committed.

### Implementation changes and limits

The whole-source reader now has an official Europe PMC full-text JATS route,
separate from human article pages. It resolves an exact DOI and open-access PMCID,
then checks article-header DOI/title and an article-level permissive license.
It also supports OpenAlex TEI when an already authorized environment supplies an
existing key. No key is created, moved or wired into another workflow here;
production's deep-reading workflow currently does not pass that key, so this
optional route will report `openalex_key_not_configured` there.

Both XML formats preserve all text supplied in the article XML, including the
introduction, nested sections, captions/table text, final qualifications and
references. Compressed and expanded input sizes are bounded; internal entities,
unsupported encodings and ambiguous identity are rejected. Legacy OpenAlex
`html/body/tei/text/div` and standard TEI body layouts are handled. The manifest
explicitly says XML-to-original-document equivalence, layout and semantics are
unverified. This is not a claim that PDF-only figures, supplements or equations
were visually read.

Publisher HTML can now follow declared PDF links and same-host Download PDF
links rather than guessing suffixes. Supplement/appendix links are excluded.
A partially readable PDF cannot displace richer HTML, and a later complete PDF
is still attempted. Robots, challenge-page, host, redirect, identity and size
checks remain in effect. The source allowlist adds only the verified IJLTER
publisher host. Existing arXiv routing works without a DOI.

Access-only acquisition is already separate from editorial source screening and
model inference through `scripts/retrieve_articles.py`. The new pilot can be
validated in an authorized network-enabled executor without opening articles to
public publication:

```bash
python scripts/retrieve_articles.py data/free-access-candidates.json \
  --report /tmp/observatory-free-access-report.json --known-sources-only --limit 11
```

That command has **not** been run against external sources in this restricted
executor. No live JATS/TEI bytes were retrieved here, and no production recovery
count is claimed. No hosted LLM, model change, paid service, new account,
institutional login or source-trained verifier run is introduced. The existing
Zenodo recovery remains indirectly invoked by repository full-text recovery.

Validation: 30 new offline route/parser tests; 332 selected Python tests passed
(the holdout-named module and its sealed fixture were not loaded); Python
compilation and JavaScript syntax passed; article UI validation passed for 69
reading pages and weekly validation for the 8-source issue. Independent review
identified and prompted additional tests for restrictive shorthand licenses,
UTF-16 entities, partial-PDF fallback and supplement-link confusion. These tests
use controlled data and do not establish live access or model summary accuracy.

### Next verification gates

1. Run the bounded access-only pilot on the exact proposed branch; inspect all
   failures and per-document identity, pages, source version and text coverage.
2. Verify real official JATS/TEI examples, including final sections, rather than
   treating an offline parser fixture as evidence of live source recovery.
3. Continue exact-title/identifier repository searches for unresolved records.
   A locator miss, a processing-license restriction and a missing free copy are
   separate states; none alone proves that an article is inaccessible.
4. Complete and independently check actual source-grounded summaries before
   promoting the acquired documents. Existing local-model semantic limitations
   documented below remain unresolved; checkpointing or more downloaded papers
   does not fix them.

## November 6: source-reviewed claim checks

[PR 34](https://github.com/chengyu-ucsb/ai-attention-observatory/pull/34) adds controlled positive and negative claims before any further production model change. Its development fixture contains 15 cases across three primary papers: 6 supported paraphrases and 9 deliberately misleading claims or claims paired with irrelevant evidence. Each paper has a checked article-specific CC BY 4.0 notice, attribution and exact section/offset locators. Only 107–137 words of licensed excerpts per source are included. All cases pass the existing deterministic anchor, number-presence and copying checks, so the experiment measures semantic verification rather than those simpler gates.

The labels and source passages were checked by assistants, not independently adjudicated by domain experts. The set is deliberately challenging, small, and not a representative sample of the corpus. One source studies non-generative algorithmic offloading. A supported case follows from the full selected excerpt and has a relevant short anchor; the anchor need not independently contain every detail.

### Observed results on the frozen development set

| Diagnostic | Valid quality outcomes | Supported accepted | Misleading accepted | Interpretation |
| --- | ---: | ---: | ---: | --- |
| [1.5B baseline, run 42143742527](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42143742527) | 0 of 15 | Undefined | Undefined | All 15 verdicts had invalid claim-index partitions, so no semantic accuracy estimate is available |
| [1.5B exact partition, run 42144752119](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42144752119) | 15 of 15 | 6 of 6 | 8 of 9 | Formatting was repaired, but misleading claims were usually accepted |
| [7B exact partition, run 42145600528](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42145600528) | 15 of 15 | 6 of 6 | 3 of 9 | Better on this set, but two numeric-role swaps and one unmeasured long-term benefit were still accepted |
| [7B supplemental checks, run 42147533395](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42147533395) | 10 of 15 | 3 of 4 tested | 1 of 6 tested | Reached the 720-second cap; still accepted a numeric swap and rejected a supported claim |

The exact-partition grammar permits every complete supported/rejected partition; it does not encode the expected answers. These comparisons preserve the original verifier instruction and all deterministic gates. All results use prescribed fixture claims rather than model-written summaries. They do not establish full-article comprehension, successful generation, independent editorial review, or a corpus-level error rate. No production model or prompt has been changed on these results.

The baseline's malformed verdicts must not be credited as correct rejections. The proposed production diagnostic correction distinguishes invalid schema/indices and unfinished output from a complete semantic rejection while retaining final failure behavior for negative-looking and incomplete-index verdicts. Existing pure-format recovery remains bounded to its original single retry; duplicate support indices additionally fail closed. No partial JSON prefix or supported subset is recovered.

### Strict supplemental check and a separate holdout

The supplemental diagnostic adds one bounded number/scope/anchor check only after the original verifier accepts a claim. Its prompt asks for explicit number-to-outcome matching, measured-versus-unassessed outcomes, decisive caveats and anchor relevance. It cannot revive a previous rejection. Malformed or incomplete supplemental output is excluded from quality metrics, and a valid supplemental rejection is final.

The actual run completed the first ten cases, then hit the 720-second cap while processing the third source. Among completed cases it accepted three supported claims, rejected one supported claim, rejected five misleading claims and accepted one numeric-role swap. It newly rejected the Lee long-term-benefit overclaim but wrongly rejected the supported allocation claim. All five Iqbal cases are unavailable, not successful or failed quality outcomes. The partial result must not be compared with the complete 15-case rates as if their denominators matched. There is already enough evidence not to promote this candidate; repeating the unfinished tail would not remove its demonstrated false acceptance and false rejection.

A separate holdout was frozen before this supplemental run: 10 cases across two different primary papers, including 4 supported claims and 6 misleading claims. Its curator and independent assistant source reviewer did not inspect candidate prompts or model outputs. The two CC BY 4.0 excerpts are 123 and 92 words, with checked publisher attribution and exact location metadata. The holdout remains unrun because the candidate already failed on the development set. It is reserved for a defensible future candidate, not consumed by repeated prompt tuning.

- Development canonical fixture SHA-256: `1680c0405ecf5369747bc2f8710d5928fb966aa0232f7e897aa96cfffe8afc70`.
- Holdout canonical fixture SHA-256: `c38cc64e80e94b2bd7d2604973c0f5f1f8ea54873bebbc1037a2a39324c35b89`.

The diagnostic uses official local Qwen2.5-7B Q4_K_M weights with both split files pinned and SHA-256 checked, llama-cpp-python 0.3.36, seed 7, ChatML and a 6,144-token context. Worker loading and inference are capped at 720 seconds, downloads at 480 seconds, and the job at 30 minutes. No hosted API service, new credentials or paid inference was introduced. Reports contain controlled IDs, hashes and outcomes, not source prose or raw model checks. After these measurements, pull requests run only offline tests; model diagnostics require an explicit manual run with an allowlisted variant and fixture set. Neither option is endorsed for production. No recurring model diagnostic was added.

The proposed workflow change removes only production runs caused by code pushes. Offline pull-request checks and the existing Tuesday/Friday schedule and manual trigger remain. The production reading workflow was verified active before editing, with an actual scheduled run on November 3. No user-requested scheduled updates are suspended. The hosted offline checks at candidate `d46f77852d5e66db31adc4e9cce6dbdd070ca963` passed 302 tests without Actions warning/error annotations; the final manual-only workflow guard adds one more passing offline test. Workflow health is separate from synthesis success: no new full-document summary has been validated by this work.

## November 5: article-synthesis format failures

The initial production reading attempt inspected here, [run 41981146610](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/41981146610), retrieved both attempted documents but completed **zero** summaries. Its separate synthesis failures were `invalid_claim_list` and `JSONDecodeError`. These were not failed downloads. The affected articles were:

- Artificial intelligence in language instruction: impact on English learning achievement, L2 motivation, and self-regulated learning, DOI `10.3389/fpsyg.2023.1261955`, retrieved from Frontiers.
- Challenges and Opportunities of Generative AI for Higher Education as Explained by ChatGPT, DOI `10.3390/educsci13090856`, retrieved from White Rose Research Online.

[Run 41796490716](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/41796490716) also completed zero summaries with the same two failure categories, using partial inputs. Both workflows exited successfully because the pipeline saved per-record failures; a green workflow is not evidence of successful article synthesis.

The reader requested a generic JSON object, but did not constrain its keys, claim-array shape, or field names. It allowed six claims of up to 90 words plus evidence anchors within only 1,100 output tokens, and did not inspect the completion reason or retry malformed responses. The saved logs do not contain model output, so truncation is a plausible failure route, not an established explanation of the historical JSON error.

The focused repair supplies JSON schemas for both claim generation and source verification, checks the returned shape independently, allows 2,200 generation tokens, and rejects truncated or otherwise unfinished responses even if their text parses as JSON. It permits one format-only retry using the same complete source segment, bounded by the existing document deadline. Missing anchors, unsupported numbers, copied passages, unexplained empty segments, and second-pass evidence rejections still fail closed without an evidence-validation retry. No incomplete JSON prefix or partial set of accepted claims is published. Failure records now distinguish `retrieval` from `synthesis`.

Eighteen new offline regressions reproduce malformed JSON, missing or invalid claim lists, truncation, exhausted retries, deadlines, and preservation of prior readings. They also confirm that format recovery cannot bypass anchor, numeric, copying, or second-pass checks and does not persist source quotations. The complete offline suite passes 234 tests; article and weekly-issue validators also pass. These use controlled model outputs. A new successful real-model whole-document synthesis and independent source-level review have **not** been verified by these tests, and no historical coverage count is increased.

### Production validation and anchor-length correction

[PR 29](https://github.com/chengyu-ucsb/ai-attention-observatory/pull/29) was merged as `84fac5db3b1bcd8a3195fec1c38e0e6434a0e408`. Its actual [production reading run 42114141036](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42114141036) completed on November 5 with two attempts, one retrieved full document, one partial indexed input, and **zero completed summaries**. Both failures were `claim_anchor_invalid` in the synthesis stage, rather than malformed JSON or invalid claim-list structure. These were different records from the earlier failure set:

- `10.3389/fpsyg.2026.1974520`: The psychology of learning with generative AI in foreign language education: building a theory of metacognition, trust, and human–AI co-regulation through a systematic review. The Frontiers PDF was retrieved.
- `10.1080/09297049.2026.2744732`: A new task of sustained attention: investigating the role of ADHD symptoms and response time variability in a task requiring children and adolescents to wait. Publisher access returned 403; the reader used retained partial sections without claiming a whole-document reading.

The schema now guarantees that each quote is a string, but initially left the existing 5–24-word anchor rule to prompt instructions and post-generation validation. Both real outputs failed that rule. Raw model outputs were not retained, so the precise anchor lengths and wording are unknown. The pipeline withheld both candidates, saved their failure stages, and preserved prior readings. Its normal rebase reconciled the concurrent Lab merge. The subsequent [Pages deployment 42114902331](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42114902331) succeeded; deployment success is separate from synthesis success.

The follow-up correction puts the same 5–24-word bound into the quote-generation grammar and explicitly asks for a short source span, not an overlong sentence. The pattern uses syntax supported by the inference engine's schema converter; conversion was checked against its official implementation. The ordinary validator remains unchanged: a backend ignoring the grammar still fails immediately, a correctly sized but absent quote is still rejected, and numerical, copying and second-pass checks remain mandatory. No quote is shortened, invented or accepted solely because it fits the grammar. Two additional regressions cover boundary lengths and a backend ignoring the constraint; the full offline suite passes 236 tests. A successful whole-document synthesis remains unverified pending the next production result.

### Source-span selection after the second production result

[PR 30](https://github.com/chengyu-ucsb/ai-attention-observatory/pull/30) was merged as `7f53ba8ef0d756ef4bdba04e2dac313de19e1141`. Its [production run 42117550135](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42117550135) again attempted two documents, retrieved one full document, used one partial input, and completed **zero summaries**. Anchor lengths now passed, but both generated anchors were absent from the source (`claim_anchor_absent`). The affected DOIs were `10.1016/j.chbr.2026.101340` and `10.3389/feduc.2026.1878665`. Both candidates were withheld. [Pages deployment 42117960478](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42117960478) subsequently succeeded without promoting those failed readings.

The next correction changes evidence selection rather than relaxing validation: the model selects a chunk-qualified ID for a source span instead of attempting to reproduce a quotation. Deterministic 5–24-word slices partition the entire source segment; concatenating their raw text exactly reconstructs every character, including whitespace and the tail. These labels are not a sample or a claim that every substantive finding was captured. IDs resolve only through the current segment's map. The literal source span then passes the unchanged anchor, numeric and copying checks, followed by the full-source model check, which must reject irrelevant selected evidence or unsupported claims. A valid ID is not itself evidence that the claim is true. Source text and span inventories remain transient; only the existing paraphrases, hashes and source-location metadata are retained.

The existing Qwen model uses explicit ChatML formatting so the reader can tokenize the same fully rendered prompt as the inference handler before reserving the requested output tokens. Inputs exceeding context capacity and fragments too short to supply an anchor are deferred, never shortened or silently declared complete. Offline tests cover exact span coverage, Unicode and short tails, unknown and cross-chunk IDs, irrelevant anchors, complete verifier context, template-aware token limits, and preservation of all prior rejection gates. The full suite passes 240 tests. This remains a proposed recovery mechanism until a real-model whole-document synthesis completes; model checks are not independent editorial review.

### Source-span production outcome and negative drafting comparison

[PR 31](https://github.com/chengyu-ucsb/ai-attention-observatory/pull/31) was merged as `31491000ee20cc4c40ad035fc1af75b516ae55a7`. Its [production run 42119863741](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42119863741) retrieved both attempted full documents but completed **zero summaries**. DOI `10.3389/fpsyg.2026.1955418` failed the copied-source gate; DOI `10.3389/fpsyg.2026.1906199` failed claim verification. Both candidates were withheld. [Pages deployment 42120300153](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42120300153) succeeded without promoting those readings. Valid source-span selection does not establish claim quality.

A bounded, non-publishing comparison in [PR 32](https://github.com/chengyu-ucsb/ai-attention-observatory/pull/32), [run 42123056636](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42123056636), then compared current drafting with evidence-first schema ordering and an explicit concise-original-paraphrase instruction. Each variant received the identical first 5,500-character chunk of each of those same two retrieved documents, confirmed by matching source and chunk hashes. Both used Qwen2.5-1.5B Q4_K_M, llama-cpp-python 0.3.36, ChatML, a 6,144-token context, seed 7, temperature 0.1, and unchanged validation and verifier instructions. The downloaded model SHA-256 was `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`.

- `10.3389/fpsyg.2026.1955418`: both current and evidence-first drafting failed `copied_source_passage`.
- `10.3389/fpsyg.2026.1906199`: current drafting failed `claim_verification_failed`; evidence-first drafting failed `copied_source_passage`.
- Both variants passed **0 of 2 tested first chunks**. All four attempts completed within the 720-second bound, so this result is not a timeout comparison.
- The hosted offline suite passed 257 tests, including 17 evaluator regressions. The library-mutation check passed, and the inspected workflow logs contained no Actions warning or error annotations. Source text and generated claims were not saved or logged.

This diagnostic found **no measured benefit** from the candidate instruction and ordering. Different rejection categories do not establish better or worse overall quality: an earlier gate can prevent a later check from running. The first chunks represent only 1 of 15 and 1 of 11 document chunks respectively, not full-article validation, an independent source review, or a corpus-wide success rate.

The candidate is not being promoted to production. All existing gates remain intact, and this negative result does not justify another speculative production run. A useful next evaluation would use a small, lawfully reusable, manually source-reviewed fixture set containing supported paraphrases, misleading claims, irrelevant anchors, and decisive caveats. It should measure false acceptance as well as false rejection before testing a stronger model; a stronger model is an unverified hypothesis, not an established fix.

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



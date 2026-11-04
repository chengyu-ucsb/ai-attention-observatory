# Full-article access and reading-quality audit

Updated: 2026-11-04. This is the canonical audit note for this investigation; update this file rather than creating parallel copies.

## What was actually verified

The published newsletter working does not establish that the underlying articles have been read completely. This investigation inspected the current retrieval and summarization code, read recent retrieval logs, opened public publisher/repository sources, and executed a separate public-access diagnostic on a GitHub-hosted runner. No existing article summary, evidence label, or published newsletter was changed. No subscription credentials were used. No article text was committed.

The diagnostic workflow is [fulltext-access-probe.yml](../.github/workflows/fulltext-access-probe.yml). Its first execution was [run 41778534923](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/41778534923), job 126404453237, completed successfully. The measurements below were emitted at 2026-11-04T05:19:38Z. A successful diagnostic means the checks executed, not that all URLs were accessible.

## Observed access tests

| Source | Interactive web retrieval | GitHub-hosted public probe | Interpretation |
| --- | --- | --- | --- |
| Knowing (Not) to Know, publisher article, DOI 10.1287/isre.2024.1431 | Full publisher HTML and PDF accessible; PDF first page inspected | PDF returned HTTP 403 after robots check | The article can be read through one available surface, but that does not prove unattended publisher retrieval works |
| Knowing (Not) to Know, EconStor working-paper version, DOI 10.2139/ssrn.5383106 | Repository PDF accessible; cover/version inspected | PDF retrieved: 89 total pages, 89 processed, text on all 89; 198,047 extracted characters; 3,541,820 response bytes | A concrete repository route works from the cloud runner without campus authentication; it is not automatically the journal version |
| Prompt-based emotional scaffolding, DOI 10.1111/bjet.70094 | Publisher HTML includes methods, results, discussion and limitations | Publisher HTML returned HTTP 403 after robots check | Interactive reading works; scheduled direct publisher retrieval still does not. This paper already has an original source-checked note in the repository, so this is not a newly recovered corpus item |
| ChatGPT as cognitive scaffold, DOI 10.1080/10494820.2026.2744894 | Publisher-indexed abstract located; complete article not verified | Publisher HTML returned HTTP 403 after robots check | Remains unresolved; a /doi/full/ URL or a search snippet is not proof of full-article access |
| Reflective learning dashboards, DOI 10.14742/ajet.11584 | Complete primary article not successfully retrieved | Not included in this runner probe | Unresolved; secondary bibliographic pages are not substitutes for the paper |

The PDF probe checked that text extraction ran across all pages. It did NOT verify that tables, formulas, figures, footnotes, or reading order were extracted correctly. Section-word presence was deliberately labeled as diagnostic, not proof of section completeness. The source text was kept in memory and discarded; only measurements were logged. An 89-page working paper is one source version, not 89 sources.

Source locators:

- [INFORMS publisher HTML](https://pubsonline.informs.org/doi/10.1287/isre.2024.1431)
- [INFORMS publisher PDF](https://pubsonline.informs.org/doi/pdf/10.1287/isre.2024.1431)
- [EconStor working paper](https://www.econstor.eu/bitstream/10419/334511/1/1947737333.pdf)
- [Wiley emotional-scaffolding article](https://bera-journals.onlinelibrary.wiley.com/doi/10.1111/bjet.70094)
- [Taylor & Francis cognitive-scaffold article](https://www.tandfonline.com/doi/full/10.1080/10494820.2026.2744894)

The October 26 archived edition described the INFORMS article as abstract-based. This audit has not changed that historical edition or upgraded the current library record.

## Baseline: extracted sections are not complete readings

The [November 4 retrieval run 41753343863](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/41753343863), job 126323491098, reported after its retrieval steps:

- 423 scholarly records in the internal acquisition inventory.
- 147 records with at least some machine-extracted full-text sections.
- 1 separate original full-article synthesis.
- 275 records without full-text sections.

These are internal acquisition counts, not counts of editorially accepted studies or completed comprehensive reviews. The same run reported 69 public readable records and 33 full-text-labeled canonical readings. Those public and internal denominators must not be conflated.

Within the 275 unresolved records, the independent-repository status partition was: 90 license_unverified; 31 pdf_host_unapproved; 103 no_oa_pdf_reported; 27 provider_incomplete; 20 not_tried; and 4 pdf_unreadable_or_blocked. Provider-specific classifications overlap across retrieval systems and must not be added together. Semantic Scholar was rate-limited in this run; its thirteen attempted repository recoveries yielded zero new full texts. There is therefore no basis for promising that more identical retries will solve the backlog.

## Code findings

1. **Reading eligibility is coupled to public reuse.** `scripts/enrich_repository_fulltext.py` accepts a narrow set of permissive licenses and rejects NC/ND variants. It also uses a small exact-host list that excludes EconStor, INFORMS and most institutional repositories. That is relevant because accepted extracted sections are saved in the public repository. It should not be interpreted as evidence that every rejected article is unavailable to read. Access, permitted analysis, storage and redistribution require separate decisions; do not simply broaden the license gate and publish restricted text.

2. **The source locator misses legitimate alternatives.** The repository module uses Unpaywall PDF URLs, does not pursue its landing-page/HTML alternatives, and tries only the first two approved candidates. Exact DOI matching is valuable, but accepted manuscripts and working papers also need explicit version relationships. A similar title alone is insufficient.

3. **Full-text labels conceal truncation.** `scripts/enrich_deep_readings.py` takes at most 4,200 characters from each scholarly methods/results/discussion/limitations field, caps the assembled source at 16,500 characters, and then gives the model at most 16,000. A document can therefore be labeled full_text even though much of its evidence was never passed to the model. It also requires a results field, which is inappropriate as a universal gate for conceptual articles and some reviews.

4. **Two matching phrases do not validate a summary.** The local reading model is Qwen2.5-1.5B. Its acceptance checks include two short matching anchors, field lengths and copied-text detection. These do not establish that every claim, sample size, effect direction, causal inference or limitation is correct. Model size alone is not the diagnosis; evidence coverage and claim verification are missing controls.

5. **Zotero is only a diagnostic connection.** `scripts/zotero_sync.py` reads indexed text for DOI-matched attachments in the named collection, counts whether at least 500 characters are available, and discards it. It never passes that text to the summarizer. A configured key is not an article-reading pipeline. This audit did not verify the current private collection or grant broader library access.

## Recommended implementation, not yet installed

### Separate acquisition from publication

Preserve a permissively reusable structured-text route for material whose license supports that use. Add a distinct, permission-checked read-and-summarize route for legitimate public or authorized institutional copies. Keep restricted source text transient or in an explicitly approved private cloud destination; publish only original analytical prose and source/version/coverage metadata. Do not commit PDFs, long extracts, browser sessions or private Zotero content. Do not bypass login barriers or assume that ordinary subscription access authorizes bulk text mining.

Prioritize exact-identifier repository discovery and verified university/subject repositories, rather than accepting arbitrary hosts. Validate redirected destinations and document identity. Record version_of_record, accepted_manuscript or preprint/working_paper separately. Try publisher HTML and structured XML as well as PDFs. Crossref metadata can provide TDM full-text links; those links do not themselves grant access. Existing OpenAlex structured-content access should be retained, not presented as a newly added solution.

### Read all relevant sections before synthesizing

Use section- and page-aware chunks across the whole document, with a coverage manifest. Extract a structured account of the question, theory, design, sample, measures, analyses, main and null results, authors' interpretation, limitations and scope. Use a separate structure for conceptual/review/commentary sources. Check tables/figures visually when a claim depends on them; track supplements separately. Never silently omit the end of a long article.

Synthesize from these section notes and attach each substantive claim to a page, section or table. Check quantities, direction, uncertainty, allocation design and whether an inference is measured or interpretive. Preserve the distinctions between assisted performance, independent learning/transfer and directly measured attention. Missing text should cause a narrower labeled summary, not an invented conclusion.

### Make evidence status explicit

Distinguish metadata_only, abstract_only, partial_full_text, full_document_retrieved, full_document_summarized and source_checked_summary. Retrieval success is not a review status. Record DOI, retrieved URL, document version, retrieval date, document hash, page/section coverage, tables/figures/supplements checked, model/version and unresolved gaps. Do not automatically label an entire document fully read because it contains the word Results.

### Use existing institutional infrastructure only where authorized

Zotero's full-text API exposes indexedPages/totalPages or indexedChars/totalChars; compare them before claiming completeness. Its read-only, named-collection boundary should remain in place. The authenticated campus browser was unavailable from this chat, so no UCSB or Cincinnati access was established here. For subscription-only items, approved publisher text-mining APIs and the institution's TDM support are more appropriate to investigate than copying personal login sessions into GitHub Actions. Do not make routine OA discovery depend on the user manually collecting PDFs.

## Verification gates for the next implementation

Use a small, deliberately varied pilot before a corpus-wide change: publisher XML, publisher PDF, repository accepted manuscript, working paper, conceptual article, review, table-heavy empirical paper and a genuinely inaccessible subscription item. Measure correct-document access, page/section coverage, table fidelity and claim accuracy separately. Preserve unresolved cases and compare summaries against the actual sources. Count gains in the relevant public reading set separately from gains in the broad acquisition inventory. No full-text recovery rate or fully automated accuracy guarantee follows from this four-URL probe.

## Official documentation checked

- [OpenAlex full-text and structured content](https://help.openalex.org/access/fulltext/)
- [Crossref full-text/TDM locators and access limitations](https://www.crossref.org/documentation/retrieve-metadata/text-and-data-mining/)
- [Zotero full-text API and indexed-page counts](https://www.zotero.org/support/dev/web_api/v3/fulltext_content)
- [UCSB Library text and data mining support](https://guides.library.ucsb.edu/text-data-mining/home)

## Change boundary

Implemented in this investigation: a bounded public-access diagnostic workflow and this audit note, saved in the existing GitHub repository. Verified: the diagnostic completed, EconStor yielded text on all 89 pages, and the three tested publisher routes returned 403 on that runner. Not implemented: the revised production retrieval/summarization architecture, a new corpus-wide recovery, private Zotero ingestion, or new article summaries. The existing newsletter and its evidence labels remain unchanged.

# AI & Attention Observatory

**[Website](https://chengyu-ucsb.github.io/ai-attention-observatory/)** · **[The Weekly Edit](https://chengyu-ucsb.github.io/ai-attention-observatory/#issue)** · **[Newsletter preview](https://chengyu-ucsb.github.io/ai-attention-observatory/newsletter.html)** · **[RSS subscription](https://chengyu-ucsb.github.io/ai-attention-observatory/subscribe.html)**

## About

An open research and design project about **AI, attention, cognitive effort, and the ways technology may support—or undermine—focused thinking**. The observatory connects scholarly research with journalism, commentary, and early design experiments.

Developed by [Chengyu Fang](https://chengyufang.org/). This is an evolving research resource, not a definitive evidence review or a validated attention intervention.

## Explore

| Section | What's there |
| --- | --- |
| [The Weekly Edit](https://chengyu-ucsb.github.io/ai-attention-observatory/#issue) | A short, cross-source editorial with key themes, productive tensions, and a small experiment |
| [Research library](https://chengyu-ucsb.github.io/ai-attention-observatory/#library) | Searchable, source-attributed readings with explicitly marked levels of access |
| [Evidence atlas](https://chengyu-ucsb.github.io/ai-attention-observatory/#atlas) | Visualizations of the *indexed collection*, not population-level research estimates |
| [Experimental Lab](https://chengyu-ucsb.github.io/ai-attention-observatory/#lab) | Browser-local design prototypes exploring attention, interruptions, and graduated AI assistance |
| [Newsletter archive](https://chengyu-ucsb.github.io/ai-attention-observatory/issues/) | Permanent copies of approved editions |
| [Weekly RSS](https://chengyu-ucsb.github.io/ai-attention-observatory/subscribe.html) | Subscribe to new approved editions through a reader |

**Direct feed:** https://chengyu-ucsb.github.io/ai-attention-observatory/issue-feed.xml

RSS follows *approved editorial issues*. It does **not** publish every incoming bibliographic record. A new week without reviewed editorial copy leaves the latest published issue available. The email-style newsletter is a public reading preview: **email delivery, subscriber storage, and mailing-list signup are not connected**.

## Private Zotero access

The optional GitHub Actions workflow **Check Zotero research access** connects to
the user's Zotero Web API with the read-only key stored in the repository's
Actions secret ZOTERO_API_KEY. It follows Zotero's supported API v3 endpoints.

1. In Zotero, create a collection named **AI & Attention Observatory** and
   move or copy the relevant paper records into it. Nested subcollections are
   included. Other personal Zotero collections are not read.
2. Create a Zotero API key with user-library read access and no write
   permissions, then save it as repository secret ZOTERO_API_KEY. Never paste
   the key in an issue, chat, README, commit, log or public file.
3. GitHub Actions checks that the key is valid, locates that exact collection,
   matches Zotero records to existing Observatory DOIs, and checks whether
   Zotero has **synced indexed full-text content** for matching PDF attachments.
   The workflow is read-only and uses no university browser session or cookies.
4. See [Check Zotero research access](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/workflows/zotero.yml)
   for status only. Statuses include secret_missing, collection_missing_or_ambiguous,
   collection_empty, connected_no_doi_overlap, connected_no_synced_fulltext,
   and connected_indexed_fulltext_available.

**Bulk import:** Download the [Zotero RIS bibliography of indexed papers still missing extracted full text](https://chengyu-ucsb.github.io/ai-attention-observatory/exports/zotero-fulltext-backlog.ris).
Import it into the **AI & Attention Observatory** collection and use Zotero's
**Find Available PDFs** while authenticated through UC. This file contains
only already-public bibliographic references. Zotero does not automatically
gain university access from the API key, and publisher terms still apply.

**Privacy boundary:** This is a *connectivity and available-text audit*,
not blanket authorization to publish university-subscription content. The
Zotero API key may cover more of the user's library than the Observatory
collection; the program deliberately limits queries to the named collection.
Raw Zotero text, PDF attachments, private titles, account IDs and item keys
stay out of the public GitHub repository, GitHub Actions logs, public Pages
data and workflow artifacts. GitHub-hosted jobs are ephemeral.

If the PDF exists only in the desktop Zotero app or the institution's browser
session, it might not appear via the Zotero cloud full-text API. Zotero access
also does not automatically inherit University of Cincinnati library login.
Institutional terms may restrict text mining or third-party processing even
when an individual user can read the paper. A separate local-only analysis and
rights-review workflow is needed before publishing original derived readings.

## Independent full-text recovery

The four-times-daily full-text backfill also attempts **independent DOI lookups**
using [Semantic Scholar's Academic Graph API](https://api.semanticscholar.org/api-docs/)
and [Unpaywall's per-DOI API](https://data.unpaywall.org/products/api).
It searches the backlog still lacking substantive article sections; it does not
require a UCSB or Cincinnati login, LibKey, or Zotero setup.

The job checks for open-access PDFs on a restricted set of scholarly domains.
**A discovered PDF link is not counted as full text.** Automated processing
requires a matching DOI, an explicitly recognized permissive license
(CC BY, CC BY-SA, or CC0/public domain), an accepted HTTPS host, a valid bounded
PDF, and a substantive results/discussion section extracted from that PDF.
No unknown-licensed or authenticated PDFs are downloaded in this fallback.
PDF bytes are discarded after extraction. New content is explicitly labeled
as automatically parsed and not independently reviewed.

The [full-text backfill workflow](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/workflows/backfill-fulltext.yml)
prints provider counts and an internal triage of the remaining gap: unverified
license, unreadable PDF, no independent OA PDF, temporary provider error,
not-yet-checked, or no DOI. Both providers enforce rate limits, so a successful
run may recover zero new papers. No counts are invented or estimated from links.

**Configuration:** An optional GitHub Actions secret named
SEMANTIC_SCHOLAR_API_KEY permits authenticated Semantic Scholar queries;
anonymous requests are supported where the provider allows them. No key is
needed for Unpaywall's DOI API, which uses an academic contact address.
This is a supplementary check, not a guarantee of additional full-text coverage.
Later, CORE's researcher API could supply more repository versions, but it
requires a separately issued API key; it is **not connected** in this iteration.

## How the research pipeline works

1. **Weekly discovery** (`.github/workflows/refresh.yml`) collects source records from academic and nonacademic publishers.
2. **Full-text catch-up** (`.github/workflows/backfill-fulltext.yml`) makes smaller, repeated attempts to retrieve legitimately reusable machine-readable articles. Rate limits pause work, and retry status is retained between runs.
3. **Reading preparation** separates reported results from author interpretations, retains provenance, and generates short, source-grounded notes. Machine condensation is *not* an independently verified critical review.
4. **Editorial synthesis** (`data/issue-editorial.json`) connects themes across a complete weekly reading set. `scripts/build_issue.py` checks source links before an issue can be approved.
5. **Publication** (`.github/workflows/publish.yml`) validates the site, newsletters, RSS, and integrity checks before deploying to GitHub Pages.

### How in-depth readings are produced

Source types now follow different reading structures. Journalism and commentary use an **argument map**: central claim, reasoning, concrete examples, a substantive tension, possible design implications, and an open question. Research papers use **evidence analysis**: question, design, reported results, author interpretation, critical context, limitations, and future questions. Sections appear only when source material supports them. Publisher-only blurbs remain explicitly limited rather than being passed off as complete reviews.

Six public essays and product references have been given source-specific extended notes; those are editorially written and distinguish arguments from experimental results. Other nonacademic sources retain their publisher synopses unless fuller accessible content has actually been processed.

The separate `.github/workflows/deepen-readings.yml` workflow runs **without any hosted language-model API, API key, or inference bill**. It downloads an openly licensed, quantized Qwen2.5 0.5B instruction model to the GitHub Actions runner and executes it locally on CPU with `llama-cpp-python`. The model file stays on the runner, not in Git. Every Tuesday and Friday, the workflow attempts up to four source readings. These use only permitted public article HTML or already indexed scholarly full-text sections. It does not defeat paywalls or scrape forbidden pages, and it never publishes the copyrighted source body. There is no configuration step or paid API key. The repository still uses separate public bibliographic services for research discovery; "no API" here specifically means no paid/hosted LLM inference. Hosted-runner time, storage, and network access remain subject to GitHub's limits and terms.

Each generated reading is labeled **local-model, not independently reviewed**. Source-matching anchors and copying checks reject some unsupported or excessively extractive outputs, but **cannot guarantee factual accuracy**. The 0.5B local model may produce less nuanced readings than a larger service. Records from inaccessible, incomplete, or paywalled articles show a short publisher summary (when available) and the source link, never a manufactured article analysis. Future contributions can add editorially verified in-depth readings.

## Original research and derivative commentary

When a news article or expert explainer discusses an identifiable paper, the **original scholarly publication is the canonical research entry**. Its public-facing companion is linked on that reading page rather than counted as another independent research contribution. The research archive preserves the companion's original URL, including older links. Only editor-verified relationships are collapsed; sharing a topic, author, or terminology is insufficient evidence of duplication.

Source links and original-paper records are tracked in `data/source-lineage.json` and resolved by `scripts/source_lineage.py`. The first verified pair is Luke Rowe's October 2026 *The Conversation* explainer and the original August 2026 `Education Sciences` paper (DOI: [10.3390/educsci16081291](https://doi.org/10.3390/educsci16081291)). The primary is a **conceptual framework** proposing staged educational uses of AI, *not* a controlled test of those stages. Its record includes the publisher link and an attributed short account of the proposed framework; a full-text analysis is only marked after actually retrieving and processing permitted article text.

This is an initial, explicit source-lineage system. Not every journalistic reference has yet been traced to the research behind it; unresolved links are kept separate rather than matched by guesswork.

The internal acquisition database is `data/library.json`. The public reading projection lives in `data/public-library.json`. **Citation-only and substantively unsupported records are excluded from the public site and RSS.** Open-access links alone do not count as full-text extraction.

The newsletter generator is `scripts/build_newsletter.py`. It builds the latest preview (`newsletter.html`), permanent editions (`issues/`), and RSS 2.0 (`issue-feed.xml`) with stable permalinks and publication dates.

## Weekly search and PDF intake

Every Monday, the Observatory's GitHub Actions [research refresh](.github/workflows/refresh.yml)
runs the four-theme OpenAlex/Crossref discovery and an additional field-specific
journal search. The latter uses DOI-verified priority leads and cross-checks
journal names before accepting a candidate. The editorially nominated,
publisher-verified DOI queue is in [`data/priority-research.json`](data/priority-research.json).
It includes empirical AI-cognition, metacognition and intervention studies
from *Computers & Education*, *Computers in Human Behavior*, and related
specialist journals. It is a discovery queue, **not** a set of published
study reviews. Automatic summaries still require a substantive source abstract
or lawful full-text extraction. The weekly run now reports if discovery was
partial because an API was down or throttled. OpenAlex search and Crossref
search are complementary, not a systematic exhaustive review.

### Importing PDFs already obtained through a library

**Preferred direct workflow:** Attach a batch of PDFs to the Observatory
conversation. The assistant can match DOI/title, distinguish methods from
results and interpretations, and prepare short attributed research notes
without committing PDF bytes to GitHub.

**Repeatable personal-library workflow:** Import the same PDFs into a private
Zotero collection named exactly `AI & Attention Observatory`. Institutional
access does not give a public website permission to redistribute PDF files.
The [private Zotero health check](.github/workflows/zotero.yml) currently checks
DOI overlap and whether indexed attachment text is available; it does not
yet ingest articles automatically. Never upload the original PDFs to this public
repository, store institutional sign-in credentials, or commit indexed text
under `data/`. The [public RIS backlog](exports/zotero-fulltext-backlog.ris)
can be imported into Zotero to locate missing papers. PDFs need to be
read/extracted locally under the library's applicable terms, then reviewed
and summarized before only permissible notes are published.

### Open access is not the same as permission to republish extracted text

For a concrete example, the October 2026 BJET article
[`10.1111/bjet.70094`](https://doi.org/10.1111/bjet.70094)
is openly readable at Wiley. The registry identifies a restrictive
CC BY-NC-ND license. Previously the site stopped at its abstract because
the automated XML/PDF pipelines required a license allowing reuse and
the publisher HTML reader supported only Frontiers/MDPI.

The revised publisher-backfill now checks official Wiley article pages
separately from the license-gated text reproduction path. It records
whether a public article page is actually accessible and has section
headings, without saving the copyrighted article text. When a full
article has been individually reviewed, original, source-grounded
paraphrases can be added to
[`data/verified-full-article-notes.json`](data/verified-full-article-notes.json).
That review is explicitly labeled as editorially verified full-article
analysis; it is **not** called machine-extracted text or counted as
new machine-extracted sections. The first reviewed example reports a
144-student preregistered randomized classroom experiment; knowledge
improved in all groups, while the treatment interactions for learning
were not significant. The study's affective and task-level regulation
results have distinct qualifications.

The Wiley checker does **not** bypass rate limits, publisher restrictions,
rights terms or anti-bot blocks. If direct HTML fetches fail, it records
the precise limitation rather than falsely reporting that the paper
contains no full text. No legal or institutional PDF access is required
from the user for openly readable source analysis.

## Article-level commentary quality gate (October 2026)

**Discovery is not an article reading.** RSS/Atom descriptions are stored as
`source_preview` and cannot qualify as a full commentary analysis merely
because a paragraph is longer than a headline. The source-quality screen
requires a verified publisher article or an explicitly attributed authorized
republication; a substantive reading must have an actual thesis, chain of
reasoning, source-specific examples, a tension, and a qualification. If
retrieval or local synthesis fails, the article stays out of featured cards,
public research counts and weekly commentary. Old links resolve to a clear
*Awaiting full-article reading* page rather than an inflated one-sentence
reading. A separate public locator file `data/public-pending-sources.json`
contains only titles/URLs and the pending status; the full acquisition
backlog stays internal to the repository.

Source-checked reviews are in
[`data/editorial-source-readings.json`](data/editorial-source-readings.json).
The first case is Trent Wintermeier's October 2026 expert analysis of AI
"kill switches"; it is based on full attributed republications of The
Conversation article, with a link to the republication actually reviewed.
The distinction matters: an argument based on examples of infrastructure and
human responsibility is not an experimental study of safety interventions.

The twice-weekly deep-reading workflow separately attempts robots-compliant
publisher HTML retrieval and local source-grounded synthesis with a larger
Qwen2.5 1.5B model. If source access or validation fails, it records distinct
retrieval/model status codes and retries within limits. It does not substitute
a generic title-based commentary. A passing unit test or downloaded model is
not evidence of successful publisher full-text retrieval; consult actual
workflow logs and the depth/provenance on each reading.

## Research quality and news reading

The public reading library uses a **field-specific venue baseline**, an explicit
relevance check, and minimum standards for substantive source content. The
editable watchlist is [`data/venue-standards.json`](data/venue-standards.json):
communication and media research; cognitive psychology; HCI/CSCW; educational
technology; organizational and information-systems research. Venue matching is
a *discovery and editorial screening prior*, never a certification of a study's
methods or findings. This follows [DORA](https://sfdora.org/read/) and
[COPE/DOAJ transparency principles](https://doaj.org/apply/transparency/).
Distinctive, highly relevant work from new journals and preprints is retained
in the internal acquisition index for source and peer-review checks. Unknown
publisher labels (for example “OpenAlex” and “Crossref”), machine-learning
“cross-attention” papers unrelated to human cognition, and weak topical matches
are not automatically treated as substantive attention research. We never
automatically label an unverified journal predatory or fabricate a quality
ranking from title metadata.

The audit [`data/source-quality-audit.json`](data/source-quality-audit.json)
records public research counts and how many candidate records were deferred
for each reason. Those records are not deleted and a researcher can revisit
the decision. The source classifications are conservative heuristics—not a
fully peer-reviewed systematic screening process or an exhaustive journal list.

**News integrity:** Publisher RSS/Atom descriptions are discovery leads, not
full article text. Google News redirect URLs and headlines repeated as RSS
descriptions are quarantined rather than displayed as analyses. Some verified
original publisher articles receive source-specific editorial readings,
including Natalia Kucirkova's September 2026 Guardian essay on pacing in
children's media (editorially checked against the original article). Longer
automated news analyses are only accepted when the original article text can
actually be retrieved under site rules and supported by source-anchored checks;
the absence of an accepted reading is displayed as insufficient access, not
invented content. Original copyrighted texts are not stored in the public repo.

## Source selection and evidence coverage

The Observatory is a **structured, evolving discovery index**, not an exhaustive
systematic review or a census of published research. Its collection methods are
documented and testable:

- **Core AI research:** Searches beginning in 2023 for generative AI, human
  cognition, offloading, attention, learning, workplace use, and interventions.
- **Adjacent attention research:** Studies of notifications, interruptions, and
  digital distraction without a direct generative-AI exposure are distinguished.
- **Earlier foundations:** Older work, including the 2008 interruptions paper
  and the 2019 notifications paper, is retained for historical context but
  excluded from charts showing AI-specific research since 2023.
- **Historical coverage:** `scripts/search_plan.py` runs four thematic lenses
  over rotating 2023–2025 periods weekly and the full historical matrix when
  backfill mode is requested. `scripts/seed_historical.py` resolves a small
  set of DOI-verified foundational AI papers through bibliographic APIs.
- **Deduplication and screening:** Papers are deduplicated using DOI, relevance
  screened using title/abstract and source provenance, then assigned to direct
  AI, adjacent, or historical groups. These rules are heuristic, not formal
  independent dual-screening.

Full-text retrieval runs separately, starting with lawful, accessible XML
sources from Europe PMC and licensed OpenAlex OA GROBID. The system revisits
previously abbreviated extractions and records which article sections were
available. Absence of a legally accessible machine-readable full text **never**
causes an abstract to be represented as a full paper. A paper with a link to
an open-access landing page does not automatically count as full-text processed.

**Interpretation of visual counts:** Publication-year bars represent only
the AI-specific papers currently indexed from 2023 onward. They are not
a bibliometric estimate of the total number of studies or annual publication
trends. The library provides scope filters for the adjacent and older literature.

## Research and design standards

- Distinguish **empirical findings**, **author interpretations**, **conceptual ideas**, and **editorial synthesis**.
- Prioritize full texts when legally accessible; label abstract-based coverage rather than inferring missing study details.
- Do not reproduce or redraw a paper's empirical figure without verified data and reuse rights. The site's original concept diagrams are illustrations, not study figures.
- Present concise research ideas first; keep original titles, methods, qualifications, and source excerpts accessible.
- Treat Experimental Lab activities as unvalidated prototypes, not effectiveness claims. The prototypes run locally in the browser and do not store participant responses.
- Keep GitHub Actions on supported runtimes and runners, and verify actual deployment and retrieval logs after changes.

More detailed assistant-maintenance requirements are in [AGENTS.md](AGENTS.md).

## Run and contribute

### Weekly brief handoff and publication status

The GitHub collector and the ChatGPT weekly brief are separate processes.
GitHub cannot read a private ChatGPT conversation. A chat response alone does
not change this repository. Nominate its sources in `data/brief-leads.json`
with a title, DOI (or canonical arXiv URL), lane, discovery-week date, and
human-readable origin. Do not add private chat URLs or identifiers.

`scripts/brief_intake.py` verifies identifiers, titles and publication dates
against Crossref or arXiv. It stores provider metadata, never chat-generated
findings. Existing articles retain their acquired text and reading notes.
Identity mismatches and provider failures remain in
`data/brief-intake-status.json`; preprints still require the existing article
screen before appearing in the public library. No additional API key is needed.

The weekly workflow now finishes all intake stages before
`scripts/build_weekly.py` freezes the complete discovery-week membership.
Earlier per-channel display caps no longer truncate the final source shelf.
Historical backfills remain excluded, and `build_public.py` still quarantines
citation-only and otherwise ineligible records. This is a discovery week,
not a claim that every source was published during that week.

Each build saves the eligible source shelf to
`data/editorial-queue/YYYY-MM-DD.json`. That queue survives the next collection.
The public `data/pipeline-status.json` reports collection status, the featured
issue date, pending editorial dates, intake results, and (on Actions) the
actual checked-out revision and build-run link. Pending review creates an
Actions warning; a green deployment does not mean a new editorial was written.

To publish an edition, examine its sources and add grounded editorial text
under its date in `data/issue-editorial.json`, following the existing schema.
For an older queued edition:

```bash
python scripts/build_issue.py --edition-date YYYY-MM-DD
python scripts/build_newsletter.py
python scripts/build_issue.py
python scripts/pipeline_status.py
python -m unittest discover -s tests -v
```

Commit the reviewed editorial and generated approved issue/archive together.
The regular Pages workflow publishes the latest approved edition. Until that
review is complete, the previous approved issue stays featured. The pipeline
does not fabricate or automatically approve editorial prose.

Weekly discovery remains Monday at 12:23 UTC (08:23 New York daylight time,
07:23 standard time); GitHub may delay scheduled starts. Manual runs default
to weekly mode, with backfill still available explicitly. After a change,
check the discovery and publishing Actions runs, warnings, the deployed
`data/pipeline-status.json`, and both RSS feeds. Restore the previous commit
to roll back code; retain source records and approved issue archives.

The site is static HTML, CSS, and JavaScript. To preview it, serve the repository locally:

```bash
python -m http.server 8000
```

Then visit http://localhost:8000/. To validate reading and publishing logic:

```bash
python -m unittest discover -s tests -v
node tests/validate_playground.cjs
node tests/validate_article_ui.cjs
node tests/validate_weekly_issue.cjs
```

The published resource updates through GitHub Actions. API keys belong in repository **Actions secrets**, never in public files.

Questions, possible sources, and collaboration ideas are welcome through [GitHub Issues](https://github.com/chengyu-ucsb/ai-attention-observatory/issues) or [Chengyu's website](https://chengyufang.org/).

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

The internal acquisition database is `data/library.json`. The public reading projection lives in `data/public-library.json`. **Citation-only and substantively unsupported records are excluded from the public site and RSS.** Open-access links alone do not count as full-text extraction.

The newsletter generator is `scripts/build_newsletter.py`. It builds the latest preview (`newsletter.html`), permanent editions (`issues/`), and RSS 2.0 (`issue-feed.xml`) with stable permalinks and publication dates.

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

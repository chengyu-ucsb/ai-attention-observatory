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

## How the research pipeline works

1. **Weekly discovery** (`.github/workflows/refresh.yml`) collects source records from academic and nonacademic publishers.
2. **Full-text catch-up** (`.github/workflows/backfill-fulltext.yml`) makes smaller, repeated attempts to retrieve legitimately reusable machine-readable articles. Rate limits pause work, and retry status is retained between runs.
3. **Reading preparation** separates reported results from author interpretations, retains provenance, and generates short, source-grounded notes. Machine condensation is *not* an independently verified critical review.
4. **Editorial synthesis** (`data/issue-editorial.json`) connects themes across a complete weekly reading set. `scripts/build_issue.py` checks source links before an issue can be approved.
5. **Publication** (`.github/workflows/publish.yml`) validates the site, newsletters, RSS, and integrity checks before deploying to GitHub Pages.

The internal acquisition database is `data/library.json`. The public reading projection lives in `data/public-library.json`. **Citation-only and substantively unsupported records are excluded from the public site and RSS.** Open-access links alone do not count as full-text extraction.

The newsletter generator is `scripts/build_newsletter.py`. It builds the latest preview (`newsletter.html`), permanent editions (`issues/`), and RSS 2.0 (`issue-feed.xml`) with stable permalinks and publication dates.

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

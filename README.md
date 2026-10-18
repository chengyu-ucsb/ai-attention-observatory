# AI & Attention Observatory

A public-facing research discovery and reading room curated by [Chengyu Fang](https://chengyufang.org/). It tracks how AI influences attention, cognitive offloading and sustained engagement, together with possible interventions and relevant adjacent research.

## What the site offers

- **This week:** latest indexed papers and reporting, key-idea excerpts, topic counts, and a publication timeline.
- **Source cards:** in-site reading notes, conceptual pathway visualizations, study metadata and links to original publications. Curated synopsis, automatically indexed abstract, and openly licensed full-text excerpts are distinguished.
- **Library:** filter and search the indexed reference archive.
- **RSS:** [feed.xml](feed.xml), regenerated on every successful collector run. Readers can subscribe using RSS; **there is currently no live email list**.
- **Get in touch:** [Chengyu's academic website](https://chengyufang.org/) and [email](mailto:fangcu@ucmail.uc.edu).

## Weekly automation

The [refresh workflow](.github/workflows/refresh.yml) is scheduled for **Mondays at 12:23 UTC**, which corresponds to **8:23 AM EDT / 7:23 AM EST** in Cincinnati. The workflow can also be run manually with `backfill`. It:

1. Searches OpenAlex, Crossref and news RSS.
2. Normalizes, deduplicates and screens source metadata.
3. For a subset of Europe PMC open-access papers, extracts licensed section text and figure captions to create attributable reading cards.
4. Updates library and weekly summary JSON, generates RSS, runs tests and commits changes.
5. Publishing workflow builds the GitHub Pages site after Pages has been enabled.

**Important:** GitHub Actions cron jobs can run later than the configured minute, be delayed, or be disabled after sustained inactivity; API rate limits and source outages are also possible. Inspect [Actions](https://github.com/chengyu-ucsb/ai-attention-observatory/actions) for a real completed run rather than assuming the clock schedule is proof of success.

### Setup for public website

1. In **Settings → General → Danger Zone**, change repository visibility to **Public** (requires owner/admin action; not performed by the assistant).
2. In **Settings → Pages → Build and deployment**, choose **GitHub Actions**. This is necessary to allow the automatic `publish.yml` deployment.
3. In **Settings → Secrets and variables → Actions**, configure `OPENALEX_API_KEY` if you have an OpenAlex API key. If unavailable, discovery falls back to Crossref and RSS but OpenAlex completeness may suffer.
4. In **Actions**, enable workflows if asked, then manually run **Update research library** with `backfill`. Confirm all steps pass.
5. Check that **Publish observatory website** passes. The intended project URL (once Pages is enabled and deployed) is `https://chengyu-ucsb.github.io/ai-attention-observatory/`. This URL is not a claim that the site is already live.

### Email subscriptions

There is no subscriber database and no automatic email delivery in this version. Visitors can subscribe to RSS immediately after the public website is deployed, or request email availability using the mailto link. Automated opt-in email requires a dedicated mailing-list provider with subscriber consent, unsubscribe controls, and appropriately secured credentials. Do not collect addresses through static GitHub Pages or commit subscriber emails to this public repository.

## Storage strategy

- The public Git repo stores **bibliographic metadata and short attributed notes**, not PDFs or publisher-licensed full texts.
- Records use DOI or normalized titles as deduplication keys; the current JSON index is suitable for a modest library but not intended as a permanent high-volume database.
- Weekly collections are capped for frontend simplicity; for long-term archival integrity, move the canonical catalog to **SQLite** (or managed Postgres when server-side users and subscriptions are needed), and export small static JSON slices for publication.
- As the library grows, use incremental queries, stable IDs, saved fetch timestamps, topic/year shards, and optional compressed NDJSON backups. GitHub releases or object storage can hold large permitted archival derivatives; exclude PDF binaries and secrets from Git.
- A future phase should add DOI-linked provenance with per-claim citations, human review workflows, and true figure rendering only for appropriately licensed articles.

## Limits of the evidence

- Metadata abstracts and algorithmic section extracts are not the same as full manual reading or peer-reviewed critical synthesis.
- The diagrams show mechanisms or conceptual questions, **not demonstrated causal pathways**. Neither bar lengths nor keyword matches reflect effect sizes.
- Opinions and journalism are marked separately from academic research.
- Paper figures are represented by their source captions with an external link, not reconstructed empirical graphs.

## Run locally

```bash
python -m http.server 8000
# visit http://localhost:8000/
```

To update:
```bash
python scripts/update.py
python scripts/enrich.py
python scripts/feed.py
python -m unittest discover -s tests -v
```

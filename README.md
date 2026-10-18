# AI & Attention Observatory

**[Explore the website](https://chengyu-ucsb.github.io/ai-attention-observatory/)** · **[Read the Weekly Edit](https://chengyu-ucsb.github.io/ai-attention-observatory/#issue)** · **[Browse past issues](https://chengyu-ucsb.github.io/ai-attention-observatory/issues/)**

## About

An open research and design project exploring how AI shapes attention, cognitive effort, and everyday thinking—and how technologies might help people focus more deliberately. It brings together research, public commentary, a weekly cross-source editorial, and experimental interactive tools.

Curated by [Chengyu Fang](https://chengyufang.org/). The research readings distinguish full-text extracts from abstract-based notes, and the experimental tools are prototypes rather than validated interventions.

**Live site:** https://chengyu-ucsb.github.io/ai-attention-observatory/


## The Attention Edit: weekly synthesis and newsletter (October 2026)

The weekly homepage now starts with one editorial thesis and three cross-source themes instead of a sequence of article summaries. The full edition lives at \`#issue\` and contains a cross-source opening letter, cited themes, a productive tension, an experimental prompt, and an expandable complete source shelf.

- **Reviewed editorial copy** is versioned in \`data/issue-editorial.json\`. \`scripts/build_issue.py\` resolves each editorial citation against the full source-backed weekly set; missing or ambiguous citations fail the build. A new week without reviewed text displays a clear "editorial in review" state; the system does not invent new scientific conclusions.
- **Shareable email-style edition:** \`scripts/build_newsletter.py\` publishes \`newsletter.html\` and \`issue-feed.xml\`. These can be read in the browser and syndicated by RSS. **No addresses are collected, no newsletter is sent, and no mailing-list provider is connected.** A real email subscription requires opt-in, unsubscribe and delivery/bounce handling before launch.
- **Readable article pages:** \`scripts/condense_readings.py\` cleans extracted section numbers/citation debris and provides short provenance-labelled text. Carefully reviewed readings are explicitly identified; automatically condensed extracts are not described as independently verified. Raw source passages are tucked into expandable details.
- **Graphics:** Article pages show original conceptual artwork describing the topic, plus specific source-grounded visualizations for identified learner profiles and coding-category totals. These graphics are explicitly distinguished from study-provided empirical figures. For figures in full-text papers, \`scripts/enrich_figure_links.py\` tries to verify licensed source-hosted original image files. Only URLs that pass source, licensing and MIME checks can appear, with attribution; otherwise the website links to the original article. Figure captions alone are not evidence sufficient to reconstruct plotted values.

The issue is intentionally compact, conversational and evidence-conscious: tell readers what the sources *add up to*, where they disagree, what remains uncertain, and one small thing to try. Individual papers supply depth, not the newsletter's page structure.

## Continuous full-text catch-up and public evidence policy (October 2026)

The observatory uses **two separate schedules**, rather than waiting for weekly searches to process all newly found research:

- **Weekly discovery:** \`.github/workflows/refresh.yml\` collects new papers, journalism, abstracts and OA links on Mondays. It does not download full-text content.
- **Full-text backlog:** \`.github/workflows/backfill-fulltext.yml\` checks the existing queue four times a day (03:17, 09:17, 15:17 and 21:17 UTC) and can be run manually. It tracks which DOI was attempted, when it can be retried, whether open licensing or machine-readable XML was unavailable, and when provider credits will reset. A normal batch tries up to 24 papers and at most eight OpenAlex full-text downloads. The jobs share a concurrency lock to protect the same data.
- **Rate-limit behavior:** a 429 saves a resume time, instead of starting another full weekly search or repeatedly hammering the API. Missing licenses and missing XML are rechecked after a longer interval. The catch-up job continues checking while eligible work remains; papers behind inaccessible or non-reusable licensing cannot be guaranteed full-text coverage.

**Nothing citation-only appears on the website or RSS.** The internal \`data/library.json\` keeps incomplete bibliographic records for later acquisition, but \`scripts/build_public.py\` creates source-backed \`data/public-library.json\` and \`data/public-weekly.json\` for the site. Scholarly sources require a substantive real abstract or extracted licensed article text; nonacademic items require a meaningful publisher or attributed editorial synopsis. Pages deploys only the public projection, never the raw internal source index. Topic counts, weekly highlights and article recommendations are also computed from the public projection.

**Editorial hierarchy:** The result or research idea is now the main reading headline; the publication title is a smaller citation below it. Labels distinguish reported findings, author interpretation, and research ideas without verified results. Machine extraction is not a substitute for independent scholarly appraisal.

**Progress:** \`data/fulltext-backfill-state.json\` records extraction counts, ready/retry queue sizes, and any provider-budget pause. The homepage displays this as a small coverage graphic. Being "full-text extracted" means some permitted sections were parsed, not that a researcher completed a critical review.

## The playable Lab (October 2026)

The Experimental Lab now provides three interactive, entirely browser-local experiences rather than static form prototypes:

- **Switch Lab:** A 20-trial rule-switching number exercise with left/right mouse or keyboard responses, accuracy feedback, and a simple comparison of correct-response median times for a fixed same-rule and alternating-rule sequence. The exercise is **not** a validated task-switching measurement: order, learning, rule demands and sample size are uncontrolled.
- **Return Point:** A fictional project, brief distraction microtasks and a return-choice exercise that can be replayed with or without a visible checkpoint. The displayed elapsed time measures the local choice delay only. Trial-to-trial differences are not causal evidence for a checkpoint effect.
- **Assistance Dial:** Two short examples about reading empirical evidence, with three deterministic levels of help (reflection, hint, direct answer). It does not connect to an AI model or evaluate individual intelligence.

The homepage links directly to the Lab and previews a number-rule challenge. Research reading pages open with study-approach, reported-result and qualification snapshots, and keep the full excerpt details expandable. Three-line coverage strips on homepage features indicate available source material, not research strength.

**Data handling:** These prototypes do not call network services, log input, use localStorage or submit session scores. Everything resets on page reload. A build-time smoke test (`node tests/validate_playground.cjs`) exercises the tabs, twenty switching trials, interruption modes, and assistance scenarios; it is a lightweight DOM simulation, not a full browser compatibility or accessibility audit.

## October 2026 — Public redesign

The site now combines three complementary directions:

1. **Editorial Observatory:** a crimson, magazine-like public homepage centered on three source-backed weekly readings rather than lists of unverified article titles.
2. **Evidence Atlas:** live visual charts and tables generated from the published index, showing topic coverage, publication years, source types and the depth of accessible material. Counts describe the index, not causal effects or the state of the entire field.
3. **Experimental Lab:** clearly labeled early-stage **interactive design explorations**, including a switching mini-game, interruption re-entry challenge, and graduated assistance simulator. They do not communicate with AI APIs, collect user data or claim measured effectiveness.

The reading pages retain article methods, reported findings, limitations and source attributions when these exist. All other sections distinguish abstract-derived text from full-text extracts and bibliographic records.

**Site:** https://chengyu-ucsb.github.io/ai-attention-observatory/ (project-specific GitHub Pages address).

## October 2026 — fuller source coverage and public commentary

The project has two parallel discovery channels. Scholarly work comes from OpenAlex and Crossref, with abstracts cross-checked against Europe PMC and optional Semantic Scholar. Journalism, independent analysis, and practitioner material come from direct publisher RSS/Atom feeds (The Conversation, Ars Technica, The Verge), narrow Google News publisher searches, and a transparent editorial selection of relevant public essays. The public homepage has a **Beyond the journals** section, and article cards label reporting, opinion and product-oriented material separately from academic research.

**Full-text approach.** The separate backlog workflow retrieves permitted machine-readable Europe PMC XML and extracts methods/results/discussion/limitations. It also discovers legitimate open-access copies through OpenAlex. When the repository owner supplies an \`OPENALEX_API_KEY\` GitHub Actions secret, an optional step can read OpenAlex GROBID-XML text **only for records with explicitly permissive open licenses**. It keeps short attributed section extracts in the public JSON, not whole copyrighted PDFs/XML. Machine-extracted summaries can be wrong or incomplete; the original link remains central.

The repository has an `OPENALEX_API_KEY` GitHub Actions secret configured as of October 18, 2026. Keep it in Actions secrets, never in the public code, and respect the free daily download allowance.

**Copyright:** Readable on the web does not mean licensed for republication. News articles and design essays are represented using a small feed description or original short editorial synopsis; the website links to the source. We do not copy third-party images or redistribute articles as local files. The Conversation's no-derivatives licensing also restricts reworking republished article text; treat RSS text as an indexing aid, not a license to adapt or republish.

**Editorial quality controls:** Automatic matches can be weak. The media collector filters publisher and subject signals, rejects finance/search-result noise, deduplicates links, and distinguishes editorial opinion from empirically supported findings. Users should verify source claims independently. Both collectors can report partial errors even when some sources succeed.

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
python scripts/discover_editorial.py
python scripts/seed_editorial.py
python scripts/enrich_metadata.py
python scripts/open_access_links.py
python scripts/enrich.py
python scripts/enrich_openalex_fulltext.py
python scripts/build_readings.py
python scripts/feed.py
python -m unittest discover -s tests -v
```

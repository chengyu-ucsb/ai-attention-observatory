# AI & Attention Observatory

A private research workspace for tracing how AI influences attention, cognitive offloading, task switching, and sustained cognitive engagement—and which interventions may mitigate adverse effects.

## What it includes

- **Weekly briefing**: highlights new items from the most recent search and outlines emerging topics without claiming an automated systematic review.
- **Source library**: filters scholarly research, journalism/opinion and technology material; distinguishes direct AI-related research from adjacent digital-attention findings.
- **Reading views**: clicking a source opens an in-app research card, an evidence-footprint visual, suggested questions, and a separate link to the original source.
- **Weekly collector**: OpenAlex and Crossref metadata, deduplication and lightweight screening, updated by GitHub Actions. It does *not* claim to have read full papers.
- **Private-first**: no public GitHub Pages deployment. Use local preview or a separately authenticated hosting service if desired.

## Open locally

Serve the repository with `python -m http.server 8000` and open `http://localhost:8000`. The UI reads `data/library.json` and `data/weekly.json`. Alternatively download the repository and run a local static HTTP server.

## Refresh

`python scripts/update.py`

The scheduled workflow runs on Mondays in America/New_York and commits refreshed data. First run may require GitHub Actions enabled and appropriate repository Actions permissions. Sources discovered by machine are marked *metadata screening* and should be checked before quoting empirical findings.

**Research caution:** Cognitive effort, critical thinking, and attention fragmentation are related but distinct constructs. The evidence-footprint visuals display record keywords, not observed effect sizes or research quality scores.

The project is private. Do not enable public Pages or change repository visibility without explicit permission.

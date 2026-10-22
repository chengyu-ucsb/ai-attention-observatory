# Repository maintenance rules for coding assistants

Before creating, copying, or editing GitHub Actions workflows:

1. **Verify current action releases**, runtime requirements, and runner compatibility against each action's official repository. Do not reuse remembered or template action versions blindly.
2. **Do not use actions that still target the deprecated Node.js 20 runtime.** As of October 2026, the verified Node.js 24-capable versions in use are `actions/checkout@v7`, `actions/setup-python@v7`, `actions/setup-node@v7`, `actions/configure-pages@v6`, `actions/upload-pages-artifact@v5`, and `actions/deploy-pages@v5`. Check for newer supported versions before writing workflows.
3. Treat GitHub Actions warnings as maintenance issues, even if a run is green. After changing a workflow, inspect the next actual run for errors, warnings, deployment status, and any unintended triggered jobs.
4. Keep `.github/dependabot.yml` enabled for weekly `github-actions` version-update proposals. Review and verify these updates rather than merging automatically.
5. Don't claim deployment or scheduled collection success based only on code changes; verify completed run status and relevant output artifacts.

This policy is stored in the repository so future assistants working on it can see and follow it. It does not override GitHub's documentation or substitute for checking current versions.

## Full-text-first research integrity

- **Source priority:** For each research paper, first look for a lawful full text (publisher OA, Europe PMC, OpenAlex accessible licensed text). Use abstracts when full text is unavailable or extraction fails, and always label that limitation. An OA *link* does not establish that the paper's results were retrieved or reviewed.
- **Results are not Discussion:** Represent measured or directly stated results from the Results/Findings section. Keep Discussion as the authors' interpretation, and separate future research proposals from observed outcomes. Do not silently convert interpretations into findings.
- **Traceability:** Preserve DOI/source link, section provenance, license, and reading level; never infer sample sizes, effect sizes, figures or statistical claims from titles or topic labels.
- **Rights:** Do not copy full copyrighted papers or images into the public repo. Store only brief excerpts where licensing explicitly permits and link to source originals otherwise.
- **Operations:** Test a full-text retrieval backfill under API credit limits before reporting numerical improvements. Never rerun the entire external search solely to work around a git push race; rebase existing results where possible. Do not trigger full refreshes on every code edit.

## Public citation quarantine and research-first hierarchy (October 2026)

1. **Never publish or cite a citation-only record as substantive content.** Keep such metadata only in the internal acquisition index; do not include it in the Pages payload, RSS, recommendation logic, research visualizations, weekly highlights, or public counts. Enforce this via `scripts/build_public.py` and regression tests.
2. Public scholarly summaries require a real substantive abstract or permitted full-text extraction. Label abstract-derived claims and keep Results separate from Discussion and unverified conceptual interpretations.
3. **The research idea or reported finding is the primary visual headline** on the homepage, library cards, and each reading page. The original publication title is important attribution, but must not visually overpower the contribution.
4. Weekly discovery and full-text backlog processing are separate schedules. Catch up four times daily only when ready, pause after API quotas, and persist per-paper retry status; do not launch all weekly discovery jobs to catch up full texts.
5. Full-text acquisition is limited by actual available licensing, machine-readable access, and provider quotas. Report coverage honestly and do not promise that every citation can be transformed into a full-text review.

## Weekly editorial and visualization standards (October 2026)

- Treat the week's source-backed set as a corpus, not a list of blurbs. Lead the site and the newsletter with a concise cross-source thesis, a few carefully grounded themes, tensions and open questions. Every issue needs a complete linked source shelf so nothing is silently omitted.
- Never manufacture cross-paper consensus or claim source completeness from a search result count. Editorially reviewed issue text lives in `data/issue-editorial.json`. If a new collection week is awaiting review, keep that workflow state backstage and continue displaying the latest published issue.
- Newsletter HTML is a public preview until an email provider and opt-in/unsubscribe workflow have actually been connected. Never claim readers are subscribed or that mail was sent from the static website.
- Raw machine-extracted article sections are provenance-labelled references, not finished summaries. Clean section numbers, table artifacts and citation noise, present compact digest notes up front, and keep long verbatim extracts behind an optional disclosure.
- Prefer original, meaningful charts and diagrams to decorative filler. Show source figures/images only if reuse is permitted and the actual hosted image URL has been verified. Distinguish verified empirical charts, source figures, and illustrative concept graphics. Never reconstruct an effect size, prevalence or figure from a caption alone.
- Always inspect publication workflow logs after changes and keep automated tests for editorial citations, article views, extract cleanup and figure provenance.

## Source discovery scope and long-form processing

- Maintain a reproducible four-theme discovery plan with a **2023+ generative-AI core** and separately labeled adjacent digital-attention and earlier foundation records. The 2008 interruptions paper is historical evidence about interruptions, never AI-specific evidence. Keep early foundations accessible, but exclude them from AI-specific year charts.
- Don't confuse the number of indexed items with publication trends or comprehensive literature coverage. Historical backfill must be distinguishable from genuinely newly published material and must not distort the weekly issue.
- Use DOI and source metadata to check early anchor literature, but never invent an abstract or full-text interpretation when only metadata is available. Bibliographic-only records stay out of the public collection.
- Full-text processing should try Europe PMC and licensed machine-readable OpenAlex articles, retain substantial Methods, Results, Discussion, and Limitations sections when lawfully accessible, and track the extraction version/depth. Keep Results and author interpretation distinct. Never silently treat an OA link, a short diagnostic excerpt, or an abstract as a complete paper analysis.
- After editing a discovery or full-text workflow, inspect the real scheduled/push-triggered run, quota/pause information, resulting year mix, and changes in full-text coverage. Report measured gains, not projected ones.

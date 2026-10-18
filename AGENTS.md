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

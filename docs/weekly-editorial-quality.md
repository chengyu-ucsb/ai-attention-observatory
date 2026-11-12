# Weekly brief: readable claims and visible evidence

## November 8 correction

The November 7 issue had internal evidence anchors but its public paragraphs
called papers "the survey" and "the classroom account." The renderer put links
below them as "Reading 1" and "Reading 2." Generation also demanded the same
preprint and causality disclaimer in every comparison. The result was cautious
but difficult to understand, and the first sentence often said nothing useful.

The corrected edition uses named sources, concrete populations, methods and
outcomes, source links in the relevant sentences, and source-specific limits.
The three pinned arXiv originals and both EFF articles were checked in a separate
AI review. That is not human expert review or replication. For the math study,
the p-value discrepancy is described without falsely claiming that it reverses
the authors' conclusion. The prototype's illustrated sign error is an example,
not an accuracy estimate. The review requested and checked revisions before
publication.

## Future composition

- The evidence packet includes authors and actual source URLs. Per-field budgets
  stop at sentence boundaries instead of severing a result or qualification.
- Prompts ask who did what, what was measured, what was found and why a reader
  should care. Source names and understandable descriptions precede jargon.
- Each theme may use one to three sources. A single-source account is preferable
  to a manufactured cross-paper claim. A full issue uses at least three sources;
  a compact edition after Monday 11:30 a.m. Eastern uses at least two;
  not every source must appear in the final research question.
- Common preprint/review limits appear once in the source note. Material design
  limits stay with the relevant claim; removing repeated boilerplate does not
  relax the overclaim checks.
- Modern issues use `citation_schema_version: 1`. Each signal and tension has
  `citations` with an exact, unique text span and its source title. The compositor
  accepts source keys internally, then resolves them to a stable source title.
  The publication boundary checks source membership, URL safety, span ambiguity,
  overlaps and completeness. Optional PDF pages and section locators identify
  the passage. Older archive formats remain readable without invented links.
- A separate-context AI critique checks fidelity, identifiable sources, concrete
  detail, useful comparisons and plain language against the supplied notes. It
  must cite specific draft passages and matching source evidence, not merely
  say "pass." Each theme gets its own review and at most one correction, with
  attempts and accepted work saved privately across runner restarts. A final
  critique checks the assembled edition; it can request one framing correction
  without rewriting accepted themes. Unresolved or malformed reviews withhold
  publication. The audit keeps the candidate, model, draft hash and reviews.

The writer and automated critic currently use the same local model in separate
contexts. This is an additional check, not independent expertise. Deterministic
regression tests verify orchestration, citation safety and failure behavior;
they do **not** demonstrate reliable editorial judgment. A real unattended
model-generated edition has not yet been evaluated with this new path. Inspect
the next run and its actual prose before claiming improved automatic quality.
Do not use a passing review receipt as proof that an underlying study is valid.

## Citations and terms

The archive, newsletter, RSS and homepage render the same citation spans.
Paragraph breaks remain visible. Source shelf links show recognizable titles.
Optional `glossary: [{term, definition}]` entries create native links and visible
definitions, with hover text as a supplement. Keyboard and touch users do not
need hover. Citations take priority if a glossary term overlaps a source name.
Avoid jargon simply because a definition can be added.

## Correct an already published edition

A current discovery shelf can legitimately differ from a frozen published one.
Use the archived source shelf when correcting that edition, rather than silently
adding or dropping its sources:

```sh
python scripts/build_issue.py --edition-date 2026-11-07 --use-published-sources
python scripts/build_newsletter.py
python scripts/build_issue.py
```

The correction path still revalidates every original-reading approval, source
identity and original publication date. It cannot resurrect revoked readings or
bypass the weekly date gate. The ordinary queue path remains unchanged.

## Tests

```sh
python -m unittest discover -s tests -v
node tests/validate_issue_citations.cjs
node tests/validate_weekly_issue.cjs
node tests/validate_article_ui.cjs
node tests/browser_issue_citations.cjs
```

The last command requires a functioning browser. Local Chromium was blocked by
socket restrictions in the editing environment, so DOM checks passed but real
browser keyboard/touch behavior was not verified there. Inspect it on the
published site or a permitted browser preview before reporting visual QA as done.

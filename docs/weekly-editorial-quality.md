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
  to a manufactured cross-paper claim. An issue uses at least three sources;
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
  say "pass." Rejections cause a rewrite and a fresh critique, up to a bounded
  limit; unresolved or malformed reviews withhold publication. The audit keeps
  the actual candidate, model, draft hash, review and revisions.

The writer and automated critic currently use the same local model in separate
contexts. This is an additional check, not independent expertise. Deterministic
regression tests verify orchestration, citation safety and failure behavior;
they do **not** demonstrate reliable editorial judgment. A successful unattended
model-generated edition has not yet been established with this new path. Inspect
actual generation results and prose before claiming improved automatic quality.
Do not use a passing review receipt as proof that an underlying study is valid.

## Citations and terms

The archive, newsletter, RSS and homepage render the same citation spans.
Paragraph breaks remain visible. Source shelf links show recognizable titles.
Optional `glossary: [{term, definition}]` entries create native links and visible
definitions, with hover text as a supplement. Keyboard and touch users do not
need hover. Citations take priority if a glossary term overlaps a source name.
Avoid jargon simply because a definition can be added.

## November 11 repair diagnostics

The [November 10 generation run](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42922735584)
reached the local model but withheld the draft after three failed theme attempts.
The responses omitted a source, used fifteen-word anchors, or paraphrased an
anchor. Several inline citation labels also did not appear in the prose; those
errors were hidden behind the first anchor failure. No editorial critique or
publication followed.

Theme generation now separates visible author/title links from internal source
quotes. Suggested labels are checked for substring collisions. Repair feedback
reports independently detectable anchor and citation problems together, then
reruns the original publication gates. It never inserts citations, trims quotes,
or substitutes an arbitrary evidence phrase. Synthetic regressions reproduce the
observed failure sequence without committing article extracts or rejected prose.

The source packet also contained incomplete section extracts: two sources lacked
a findings field. A `full_text` extraction label is not a completed independent
reading. Prompts now explicitly forbid converting an aim, title or interpretation
into a measured improvement when findings are unavailable. This guidance and the
repair tests are not a factual-consistency result. The separate-context critique,
all evidence gates and fail-closed publication behavior remain required.

A bounded local replay used the failed run's exact supplied source packet and
fixed theme plan with the same Qwen weights and runtime version. All three
theme attempts still failed anchor or citation checks. The replay never reached
editorial critique and published nothing. Clearer prompting and complete repair
feedback alone therefore did not solve this case. This was a test of supplied
section extracts, not full-article verification or a production run.

A separate private structured-selection experiment required source-local anchor
IDs and explicit source identities, then mapped those selections back to the
unchanged validators. Its first response contained invalid JSON and still made
unsupported outcome and scale claims. It was rejected before further stages.
That experiment is not included in production. Exact source-span selection does
not by itself establish that the surrounding prose is accurate.

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

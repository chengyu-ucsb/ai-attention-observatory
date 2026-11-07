# Original summaries alongside machine excerpts

This adapter fixes a separate integration gap: `verified_full_article_notes.apply`
intentionally skips articles that already contain machine-extracted `analysis`.
Deleting those excerpts, or overwriting them with paraphrases, would lose evidence
and make extraction counts misleading. The new `original_reading` field is
independent. The legacy verified-HTML route remains unchanged.

## Status of this change

`data/original-readings.json` is deliberately empty. No private pilot draft, paper
text, or PDF is included. Merging this code alone does not approve or publish any
new summary, solve unattended model quality, or certify scientific validity.
Tests use fictional source claims and publication receipts.

## Admission and review

Only accepted summaries belong in this public register. Keep pending drafts,
source documents, and unresolved review notes in the private editorial workspace.
The adapter requires:

- Exact indexed article identity and title, exact version-specific source URL,
  format and extracted-text SHA-256. A related working-paper DOI stays distinct
  from the journal DOI. No claim of journal-version equivalence is allowed.
- Six bounded, original prose fields: idea, explanation, approach, finding,
  interpretation, and limitation. A conceptual framework may omit a finding.
- A section locator for every field, with optional positive page/paragraph
  numbers. Figures and supplements must be addressed in the stated review scope;
  source-byte coverage alone cannot establish that their meaning was checked.
- Original paraphrases only, no permission to redistribute source prose, and an
  explicit rights context. A readable PDF is not blanket copying permission.
- A source-specific quality decision of `acceptable`, separate from successful
  acquisition and claim fidelity. Venue/topic screening still runs afterward.
- A `passed` `ai_source_check` by a differently identified reviewer, dated and
  bound to the entire content/source/evidence/rights/quality payload.
- Separate dated publication acceptance, bound to that payload **and** its
  review receipt. This acceptance records an actual authorized decision. It must
  not be fabricated or automatically set merely because tests pass.

The hashes bind attestations to content; they are not signatures, proof of a
review, or independent verification of scientific validity. The code cannot
verify that somebody actually performed an asserted review. Editorial operation
must retain the underlying private check and authorization. AI source checks
are not human review, independent replication, or visual inspection.

Unknown fields, unsafe source URLs, unpinned arXiv URLs, mismatched identities,
duplicate manifest identities, missing/stale checks, holds, and unapproved
publication receipts fail closed. Editing the source version, text, locators,
rights or quality invalidates the check. A changed review invalidates publication
acceptance. Removal or revocation removes cached summary prose on the next build.
Previously public machine excerpts can remain available independently; a held
summary does not erase otherwise eligible source material.

## Projection

`build_public` reconciles the accepted register on every build. It rebuilds
original notes instead of trusting a cached digest. `analysis`, bibliographic
identity, source OA links, and extraction status are not modified.

Original summaries lead the card and detail page. AI-check labels, exact source
version/format, review scope, section/page locators, and separate source/journal
DOIs remain visible. Machine sections are a separate collapsed disclosure. Old
DOI-specific diagrams and machine long-form prose cannot override the versioned
summary. No sample size is inferred by the adapter.

Weekly synthesis receives exact source/version/review metadata, not only the
summary prose. Research RSS carries the AI-check/version label and actual source
link. These downstream paths revalidate cached original-summary snapshots.
Historical published issue archives are not rewritten by this change.

`original_summary_count` and `machine_sections_count` are distinct. A record may
have both, so those counts are not an additive partition. `full_text_count`
remains a reading-depth count, not a machine extraction or comprehensive review
count. No `full_text_extracted` metric is incremented by this adapter.

## Verification and operation

Run offline checks:

```
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
node --check app.js
node tests/validate_article_ui.cjs
node tests/validate_weekly_issue.cjs
node tests/validate_playground.cjs
```

`tests/test_original_readings.py` exercises the actual adapter → public library →
weekly evidence → RSS boundary, including revocation, stale receipts, quality
holds, DOI-less records, working-paper identity, and unchanged source excerpts.
UI tests use synthetic accepted summaries. These tests establish integration
behavior, not the truth of any real reading.

A future accepted reading should be added as a separate, reviewable data change
with its authorization and source-level checks. Existing private pilot drafts
remain private until their individual quality/version questions and publication
decisions are resolved. No new account, model API, credential, workflow schedule,
or automatic publication approval is introduced here.

## Previous-week integration

New weekly shelves use the preceding completed UTC Monday–Sunday week. Accepted
summary prose never supplies or overrides original-publication date evidence.
Date conflicts, missing dates, historical backfill and out-of-window items remain
excluded even when the summary itself is accepted. The general library can keep
an older accepted reading without using it to pad a thin weekly edition.

A weekly summary must check the dated source itself: the source DOI must match
the indexed DOI, so a related older working-paper reading is library-only. arXiv
summaries must use the officially verified v1 identity and pinned source URL,
with `arxiv_preprint_v1` or `preprint_v1` version labels and no conflicting indexed
version. A DOI-less non-arXiv summary needs the exact same source and record URL;
alternate editions need explicit version evidence before weekly admission.
The shared gate is checked again after current-register reconciliation in the
issue builder, before synthesis, and in research RSS. Saved queue receipts keep
publication-date provenance and cannot lose the original-summary marker to skip
validation. Existing published archives remain untouched.

The synthesis preflight reports `awaiting_substantive_sources` when fewer than
four valid source-backed readings are available, before installing inference or
downloading weights. The workflow's existing `needed` output stays false and its
step summary explains the hold. This is a withheld edition, not a successful new
publication. Direct composition still rejects insufficient evidence. The earlier
published edition remains visible. No minimum, quality, or date gate is relaxed.

This adapter admits scholarly summaries. Nonacademic analysis still needs its
separate full-argument review and publication pathway; a feed preview or partial
HTML extraction does not become a reviewed policy, opinion, or news reading.

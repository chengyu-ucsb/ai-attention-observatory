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

A feed preview or partial HTML extraction alone never becomes a reviewed policy,
opinion, or news reading. The following explicit receipt path is required.

## Article-screened preprints and attributed commentary

The same empty accepted register now supports two additional **explicitly
screened** types. No screening draft, source body, or actual publication approval
is included. Code validation is not source review and cannot determine whether
an attestor's prose is true. Publication still requires a separate, content-bound
acceptance after the independent AI source check.

Both types require an `article_screen` object with exactly:
- `record_sha256`: `checked_reading_types.record_digest(record)`, binding current
  kind, DOI, URL, title, venue, publication date and its evidence, research type,
  source version. A changed indexed record requires renewed review.
- `decision`: `acceptable`; `reviewer`; `checked_on` (no earlier than publication,
  no later than the separate source check, no future dates).
- `topic_fit`, `methodological_assessment`, `limitations_assessment`: substantive,
  source-specific assessments, not a venue reputation shortcut.
- `peer_review_claimed` and `strong_causal_evidence_claimed`: both false.

This object is inside both existing receipt hashes. Unreviewed, held, duplicate,
changed or revoked entries remain excluded. Known preprint signals include
repository venues, arXiv URLs/DOIs, first-submission provenance, and manuscript
version labels. Preprint articles retain independent topic screening. Projected
notices and limitations explicitly distinguish article screening from peer
review and strong causal evidence. Weekly synthesis requires those qualifications
in each cited comparison, including its tension section. These lexical checks
are a conservative guard, not semantic proof of every generated claim.

Nonacademic receipts replace scholarly summary/evidence fields with `thesis`,
`reasoning`, `examples`, `tension`, `qualification`. Each is a substantive original
paraphrase with main-argument section and numbered paragraph locators. No study
methods/results slots are populated. A `commentary` object requires:
- `genre`: opinion, policy_analysis, reported_analysis, product_analysis, practical_advice, or product_control_guidance.
- `attributed_to`: the source's author or organization.
- `source_depth`: main_argument_html.
- `html_completeness` and `semantic_completeness`: not_verified.
- `figures_checked`, `supplements_checked`, and
  `linked_claims_independently_verified`: false.

The adapter currently accepts only exact canonical publisher HTML URLs and the
`publisher_article` version, with empty DOIs. This intentionally does not claim
support for alternate republications or a complete machine extraction. The
checked source SHA-256 and paragraph locations identify the read rendition;
without new retrieval this offline adapter cannot detect later live-site changes.
An updated source hash requires renewed source check and publication acceptance.
Commentary is projected as curated, attributed main-argument reading, never as
machine-extracted full text or empirical results. RSS snippets remain ineligible.
Examples, tension and qualifications travel into the synthesis evidence packet.

Previous-week original-publication and exact checked-source gates are unchanged.
Synthetic tests cover library, weekly evidence, revocation and stale metadata.
Existing journal-linked working-manuscript fixtures now also need article screens.

### Queue and display boundaries

Queued extended receipts carry an exact metadata-only `original_record_context`,
separate from display labels. Resolution requires the current internal library,
a unique same-identity row and identical bound metadata. The current row supplies
any abstract needed for topic screening; no abstract/source body is copied into
the queue. Missing, duplicated or changed indexed records require rebuilding and
revalidating the issue. Revoked/changed acceptance still fails afterward.

**Commentary publication remains blocked on typed display support.** The backend
exports all five argument lenses in `reading.digest.longform`, with genre,
attribution, truthful main-argument scope and no methods/results. Current main's
original-summary UI branch does not render those lenses correctly. Existing
Node regression passes are not acceptance of this new commentary presentation.
Do not populate real commentary receipts until a separately reviewed renderer
change exposes these fields without empirical-study labels. No UI code is part
of this backend change.

Commentary additionally requires `commentary.temporal` with exact
`original_published` (matching indexed publication date), `reported_modified`
(a verified date or null for unknown), `checked_on` (matching source-check date),
and `historical_snapshot_verified: false`. Known modification must not precede
publication or follow the source check. Dates and unknowns are projected in a
prominent `temporal_notice`, alongside `quality_note` and “limited reading”
framing. A known modification after the weekly window withholds that current
version from that week's shelf; library inclusion remains possible with the
caveat. Same-week modifications remain eligible. Modified/check dates never
replace original publication dates. Queue reconstruction restores temporal
metadata from the current accepted receipt, so dropping displayed dates cannot
bypass the weekly gate. An unknown modification date remains explicitly unknown,
not an inferred unchanged original-week snapshot.

Normal synthesis, RSS and current public-cache revalidation also require the unique
current library row for extended receipts. The cached context must match current
metadata, and the accepted receipt is checked against current topical evidence.
Missing, duplicate or changed indexed records are quarantined as citation-only;
stale cached abstract/digest prose cannot fall back into synthesis or RSS.

# Article summaries: acquisition, reading, and publication

## Diagnosis from the November 8, 2026 snapshot

The public payload at `7928dda` contains 88 readings. Of these, 64 use automatic
source-sentence condensation. The internal index contains ten recorded complete-
reading attempts and no completed `deep_analysis` objects. These are observations
of this snapshot, not corpus-wide retrieval or model accuracy estimates.

There are three distinct paths, which must not be conflated:

1. `build_readings.py` and `condense_readings.py` expose labeled source excerpts.
   They do not produce independent original article narratives.
2. `comprehensive_readings.py`, used by the scheduled deep-reading workflow,
   processes every retrieved text interval and checks generated claims. It uses
   the 1.5B local model. Its current output concatenates checked claims; a clean
   run or a retrieved document does not demonstrate a useful article summary.
3. `original_readings.py` admits bounded original summaries with exact source
   identity/version, evidence locations, an actual separate AI source check,
   an article-specific quality decision, and separate publication acceptance.
   Existing machine excerpts remain available independently.

The old `enrich_deep_readings.py` two-anchor generator is not the production
entry point. Do not diagnose or change the current workflow by examining only
that earlier implementation. The stronger-model claim benchmark tests prescribed
claims, not generated whole-article summaries. Neither benchmark completion nor
unit-test success authorizes replacing the production verifier.

## A real failure the source-note fix addresses

For *Cognitive ease at a cost* (DOI `10.1016/j.chb.2024.108386`), the prior short
source digest selected lower cognitive load while dropping the immediately
following lower-quality reasoning result and null result for recommendation
variation. Its methods and limitations selection could favor administrative
procedure or an empty introduction to the limitations section.

The source-note selection now:

- Keeps up to two immediately adjacent contrasting or null outcome sentences
  with an explicit reported finding, in original order and within a bounded
  length. It does not generate new prose, clip sentences, use Discussion as
  Results, or convert future/prior-study statements into current findings.
- Compares an explicit abstract design/sample with the retained full-text
  procedural sentence. The selected sentence carries its own source depth;
  an abstract fallback never becomes a full-text method claim.
- Skips generic limitation introductions while retaining a specific constraint.

These are safer excerpts, not a claim that every important outcome or caveat has
been captured. A fuller source reading is still needed. The actual full article,
for example, reports 92 initially participating students and 91 analyzed after
one exclusion; an abstract-only excerpt cannot resolve this distinction itself.

## Practical end-to-end path

Keep acquisition independent from drafting, source-quality screening, and
publication. A useful operation reports separate counts for candidate locators,
identity-verified retrieved documents, drafts, source-check passes, quality holds,
accepted summaries, and verified live publications.

For each original reading:

1. Acquire an exact lawful source version and retain its hash and page/section
   coverage. A free locator, PDF byte count, or extracted HTML body is not a
   completed reading. Keep source bodies outside the public repository.
2. Read the whole substantive argument, methods, results including nulls,
   interpretation and limitations. Inspect essential tables/figures or hold
   claims that depend on them. Record missing supplements and source conflicts.
3. Write a bounded article-level narrative: question, design/population/comparison,
   main and countervailing outcomes, interpretation, and material limits.
   Separate self-report, task performance, independent learning and durable
   cognitive change. For commentary, use attributed thesis, reasoning, examples,
   tension and qualification, not invented study methods or measured effects.
4. Have a distinct source-check pass test every substantive clause against the
   exact retained rendition. Correct denominators and causal inflation, not just
   word overlap. Bind the final text and evidence to the receipt.
5. Apply the existing article-quality and deliberate publication gates. Rebuild
   public library/weekly/RSS through the canonical pipeline, then inspect the
   actual rendered reading and source/version labels. The existing trusted-main
   `Deepen source readings` completion hook in `publish.yml` already rebuilds
   the public shelf and deploys Pages; preserve that hook.

Do not turn unfinished pilot drafts into accepted records automatically. New
prompts, larger local models, claim-list assembly, or alternative synthesis
systems need end-to-end source-reviewed generated-summary evaluation before
unattended publication. Preserve existing holds and the separate unseen claim
holdout; do not tune on it to obtain a passing score.

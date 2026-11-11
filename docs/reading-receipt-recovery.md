# Recover a stale final-reading precheck

## Failure reproduced offline

At repository commit `d5395c6c70419d8c739c48f14c758c45a59540f2`, the
2026-11-02 preparation packet contains 58 items and was observed at
2026-11-10 20:53 UTC. The reading bundle, execution receipt and final receipt
still bind the earlier 26-item packet read at 01:31 UTC. Its packet digest
starts `a62e5a87`; the current packet digest starts `bf55b989`. The acquisition
state digest still matches the reading bundle. These are separately valid
snapshots, but they no longer establish final reading of the current packet.

Previously `edition-check` called strict `validate_reading_inputs` and raised
`reading_inputs_changed`. That stopped the finalizer at its skip precheck,
before the existing bounded recovery stages could run. It also failed the
edition's precheck instead of reporting an explicit publication hold.

## Readiness is not authorization or finalization

The read-only precheck now distinguishes:

- Missing final/execution receipts: `ready=false`, `awaiting_final_reading` or
  `awaiting_final_reading_run`.
- Valid but mismatched packet/acquisition snapshots: `ready=false`,
  `reading_inputs_changed`, with the changed file names.
- Changed canonical library/weekly inputs or a different execution receipt:
  `ready=false`, `final_reading_inputs_changed`.
- Truly absent acquisition/readings files with existing receipts:
  `ready=false`, `awaiting_reading_inputs`.
- Malformed JSON, unexpected fields, null instead of an object, invalid
  checksums, dates/windows, approval flags, or fabricated coverage/status:
  a hard validation error. Missing receipts do not hide invalid files that
  are present.
- Exact unchanged validated final inputs: `ready=true`, without another
  acquisition or model call.

Recoverable holds return `next_action=readings`; they do not write, reseal,
delete or promote any receipt. A current receipt's coverage is recomputed from
its bound inputs and execution outcomes before readiness is reported. These
local integrity records are not proof of independent review or approval.

## Next safe stage

For an already authorized finalizer, under the existing shared writer lock,
the existing workflow proceeds from a recoverable hold through its normal
`readings --phase closed --expected-week <captured-week>` operation:

1. Acquire at most 12 candidates using retained cursors, denials, provider
   pauses, rights and source identity controls.
2. Reconcile against the current packet/acquisition state and attempt at most
   two machine readings. Changed source URL, version, text or bytes invalidates
   old notes and revalidation. Unchanged failures retain their retry rules.
3. Revalidate at most 12 sources and apply only notes that satisfy the existing
   exact-source, date, content and machine-reading checks.
4. Rebuild the existing gated canonical projections, then run strict
   `finalize` against the newly completed execution receipt.
5. The edition checks the new final receipt before its normal source-backed
   composition/publication gates. Missing/failed readings remain explicit gaps.

Do not run `finalize` alone to relabel stale work as current. It still raises
on stale inputs. Do not copy old notes into a changed library, rewrite hashes,
clear denials, repeat discovery, or treat this precheck fix as approval to
retry previously denied source access. The fix does not dispatch production
work or widen any permission. Under the default legacy gate, a library change by another authorized writer
invalidates the old final receipt and requires the normal bounded path again.
The opt-in, read-only equivalence proof below handles only its explicitly
verified canonical no-op exception.

The real packet mismatch was verified only with the local read-only
`edition-check`. Production data, providers, models and workflows were not
changed or executed during this repair. Offline regressions exercise the real
acquire/review/revalidate/apply functions with supplied test sources, a newly
added packet item, source replacements, malformed receipts, missing inputs,
canonical changes, strict finalization refusal, and unchanged-run idempotence.

## Canonical backfill race (November 11, 2026)

The completed finalizer at `235527b03cbce19559a6e767d7541c8afe728d0c`
was followed by backfill commit `dd4ea5b96a24a5997f49a6bd277920c18b732148`.
All prepared files, execution/final receipts and `weekly.json` stayed exact.
Twelve existing library rows changed, causing natural edition run
`42939242988` to hold at `final_reading_inputs_changed` even though the job
finished green. Eleven changed rows were outside the publication-week set.
The remaining November 5 arXiv record (`2611.08188`) gained a
`waiting_for_license` retry and its DOI-derived unversioned landing-page alias.
Its abstract, reading, pinned v1 PDF route and route fingerprint stayed exact.
No new source reading or approval was established by that backfill.

New final receipts use `binding_policy_version: 2`. Their library digest binds
every field of current-week candidates, even held/unapproved candidates, and
their packet/weekly identity dependencies. Raw and locally corrected dates and
identities, plus lineage dependencies, determine inclusion. The complete
correction, source-review, original-reading, lineage, venue and source-hint
registries are also bound. Historical records outside that dependency set can
change without invalidating the receipt. Source URLs, text, rights, versions,
approvals, publication dates and cooldowns on relevant records remain bound.
Packet, acquisition, readings, weekly window and reading-policy checks stay
exact. Existing legacy receipts retain their original whole-library meaning.

The edition precheck explicitly opts into
`edition-check --reconcile-legacy-library`. Only for a legacy receipt whose
sole changed binding is `library.json`, it can prove a no-op using complete
local Git history. A matching reachable historical snapshot must contain the
exact saved final receipt, every input it binds, the exact execution receipt,
and unchanged policy/approval registries. Multiple equivalent complete content
proofs are allowed. Missing, shallow, partial/promisor, truncated, inconsistent or genuinely
ambiguous history holds publication. Git lazy fetching is disabled; this check
never obtains source content or calls a model.

The proof compares both old and new publication-week identity closures. It
allows historical changes outside those closures, plus a narrowly validated
`waiting_for_license` bookkeeping update on an abstract-only scholarly record
without extracted or reviewed source material. It never decreases attempts or
moves cooldowns backward. An OA alias addition is allowed only for the exact
already-known DOI-derived arXiv landing URL, with the same pinned v1 identity
and unchanged acquisition plans in both modes. An arbitrary URL discarded by
the route gate is **not** proof of equivalence. Missing fields, unsupported
retry states, rights/version/approval/text changes or any other relevant
metadata change hold publication. Coverage is recomputed and must stay exact.

The optional check is read-only and does not replace, migrate, reseal or
backdate either receipt. It does not claim successful readings or independent
approval. Default `edition-check` and `finalize` remain strict for legacy
receipts; a new default-policy receipt requires a genuinely new bounded stage
execution. That path retains existing per-record outcomes, denials and retry
controls rather than authorizing source-access retries.

Offline verification against the actual two commits, after obtaining complete
local Git history, returned `ready=true` only with the explicit reconciliation
option and identified baseline `235527b`. Default readiness stayed held. Both
receipts and all data JSON stayed byte-for-byte unchanged; coverage still
reported two failed machine readings and zero completed readings/approvals.
Tests also cover historical additions/deletions, corrected historical rows,
identity dependencies, malformed inputs, unsupported policies, receipt tamper,
missing/ambiguous/shallow Git evidence, exact-equivalent baselines, protected
source/rights/date/approval mutations, wrong arXiv URLs and cooldown rollback.

Production integration changes only the edition precheck flag; its existing
full-history checkout and every publication gate remain intact. Existing
checkout `v7.0.1`, setup-python `v7.1.0`, and upload-artifact `v7.0.2` releases
and Node 24 support were verified against their official repositories before
that one-line workflow edit. No schedule, permission or action version changes
are included. This repair itself does not dispatch, retry, publish or deploy a
workflow; inspect the next authorized natural run before claiming production
publication success.

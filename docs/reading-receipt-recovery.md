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
work or widen any permission. A library change by another authorized writer
invalidates the old final receipt and requires the normal bounded path again.

The real packet mismatch was verified only with the local read-only
`edition-check`. Production data, providers, models and workflows were not
changed or executed during this repair. Offline regressions exercise the real
acquire/review/revalidate/apply functions with supplied test sources, a newly
added packet item, source replacements, malformed receipts, missing inputs,
canonical changes, strict finalization refusal, and unchanged-run idempotence.

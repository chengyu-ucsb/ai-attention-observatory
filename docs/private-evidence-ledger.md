# Private evidence checkpoints

`scripts/evidence_ledger.py` is an optional, private checkpoint library. It has
no retrieval, model-selection, publication or scheduled-run entry point. The
normal public reading pipeline is unchanged.

It preserves completed claim work across an interruption without saving the
paper's text. It does **not** make the current verifier accurate, supply a
cross-section semantic check, or authorize publication of a partial reading.

## Inputs and storage boundary

The caller supplies the same authorized, ephemeral `Document` and complete
`comprehensive_readings.chunk_document` plan on each open. Source text and any
PDF bytes stay in memory. The ledger binds source identity, exact URL/version,
source bytes when present, all text units, ordered character intervals, chunk
text and an explicit policy fingerprint. Hashes of identity, URL and version
are stored rather than their readable values; the caller's source catalog is
needed to interpret them.

The private directory must be explicitly selected outside the Observatory
checkout and detected Git/source-snapshot checkouts. Symlink paths and unsafe
file ownership, permissions and links are refused. New directories/files use
private permissions. Do not place the directory in a publication tree, a
shared folder or an automatically uploaded artifact directory. Path checks
cannot reliably identify markerless exports or every public artifact root.
They do not establish that every possible destination is private, and the files
are not encrypted.

Persisted claims retain intended original paraphrases that passed the applicable
gates, plus field names, source-span identifiers and hashes. The stored schema
omits literal anchors, source chunks, source bytes, raw model-response fields,
arbitrary exception messages and readable provenance URLs. Claim text is also
screened for copying, quotation forms, URLs and credential-like strings. These
are conservative safeguards, not a universal originality, copyright or secret
detector. Access and reuse permission must still be checked before obtaining
or processing a source.

## Policy identity and resumption

`SourceContext(..., policy_sha256=...)` requires a SHA-256 fingerprint of the
actual complete reading policy. The caller must include the model/weight and
template identities, inference settings and limits, prompts, reader code and
all relevant validation code, **including the private ledger's own privacy and
resume validators in `scripts/evidence_ledger.py`**. Changes to these validators
require a different policy fingerprint even if the public reader is unchanged.
A constant label such as a model's display name is not sufficient. The ledger
does not independently discover or attest this policy on the caller's behalf.

With the repository's `scripts` directory on the Python import path, create a
context and open the ledger using the public API:

```python
from evidence_ledger import SourceContext, EvidenceLedger
from comprehensive_readings import chunk_document

context = SourceContext(
    document=authorized_document,
    chunks=chunk_document(authorized_document),
    source_id=verified_source_id,
    policy_sha256=actual_policy_fingerprint,
    kind="scholarly",
    provider="repository",
    license_code="cc-by",
)

with EvidenceLedger.open(explicit_private_directory, context) as ledger:
    progress = ledger.status()  # Counts and controlled statuses, no claim prose.
    # A caller may request one pending chunk through run_chunk(...).
    # Supply an authorized model and title, choose an appropriate deadline,
    # and supervise inference in a bounded worker. The ledger is not a hard
    # runtime limiter.
```

Do not infer a provider or license from the example. Use verified values, or
the supported unknown/unspecified labels. Section roles are optional controlled
annotations; unknown roles must remain unknown rather than be guessed from a
page number.

`run_chunk(context, chunk_id, model=..., title=..., deadline=...)` calls the
existing `read_chunk` unchanged. All applicable original schema, anchor,
numeric, copying and final verifier gates must succeed. A successful empty
claim batch has no claims to verify; it is not proof that nothing important
was present or that every substantive claim was captured. The ledger rechecks
deterministic and privacy constraints before saving the **whole** returned
claim batch. There is no accepted-subset salvage. A completed chunk returns
its saved private claims without another model call; `claims_for(chunk_id)`
explicitly reads those paraphrases when the caller needs them.

Reader failures are recorded with controlled, allowlisted errors when storage
permits; arbitrary exception text is never saved. A rejection is unresolved,
not an invitation to try again until the model approves. An interrupted started
checkpoint is uncertain and likewise has no automatic retry operation.
Completed earlier checkpoints remain available. Changing source, version,
bytes, policy or chunk plan refuses reuse rather than blending old acceptances.
The caller must re-obtain the exact source or deliberately start separate work;
the ledger is not a cache of protected source text. Do not use another
directory to retry a rejected claim into acceptance or publish a successful
subset of unresolved work.

Atomic writes, private permissions, advisory locking and stale-handle checks
protect cooperating POSIX processes. Checksums detect accidental corruption,
not a malicious same-user rewrite or rollback. Durability depends on the
filesystem's `fsync` behavior. An uncertain write requires reopening rather
than continuing with an assumed successful commit.

## Cross-section review is a separate obligation

`retrieved_interval_plan_complete` means the supplied chunk plan covers every
retrieved text character exactly once, without gaps or overlaps. It is checked
before any model work. `all_retrieved_text_processed` means every planned chunk
completed the applicable reader and ledger gates. Neither status verifies that
the model attended to or understood every character, or that its claims are
semantically exhaustive. Neither establishes that the supplied text is the
complete paper, that extraction preserved its meaning, or that figures, tables
and supplements were examined.

The ledger separately records:

- unit examinations for caveats and contradictions;
- explicit later-limitation, contradiction or scope-qualification obligations;
- affected chunks and unresolved or explicitly reviewed dispositions;
- a cross-section review attestation only after the prerequisites are met.

`examine_unit`, `add_obligation`, `resolve_obligation` and
`attest_cross_section_review` are **caller attestations**, not a semantic
detector. Do not mark units examined in a loop merely because their chunks
finished, or resolve a limitation without checking its effect on the claims.
An attestation does not rewrite a claim, independently review it, or certify
truth. All-unit review and all obligations must be addressed, and independent
review remains distinct: `independent_review` stays `pending`, even after a
cross-section attestation. There is no publication-ready state or public
assembly function, even when every checkpoint and attestation is present.

## Offline verification

Focused tests use synthetic sources and controlled model responses:

```bash
python -m unittest discover -s tests -p test_evidence_ledger.py -v
```

They test storage, resumption, validation and privacy boundaries. They do not
establish actual model accuracy, successful source retrieval, whole-article
comprehension or deployment. No production schedule or model is changed by
using this module's tests.

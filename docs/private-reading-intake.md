# Private machine-reading intake

Source retrieval, private machine synthesis, and public editorial approval are
separate gates. `source_quality.private_reading_eligibility` accepts existing
public-screen inclusions, and permits recognized venues/preprint repositories
with explicit human-AI cognition/agency metadata to enter the private reading
queue. It does not accept all uncertain topics or unknown venues. This is a
bounded heuristic intake, not a guarantee of methodological quality or complete
topic recall. Generic model reasoning, KV cache offloading, and clinical ML
classification are not human-AI interaction evidence.

The public `screen` and `topic_class` functions are unchanged. The two November
2026 agency/cognitive-atrophy preprints can now be investigated, but remain
publicly held. In particular the article-approval extension still requires a
public direct/adjacent topic classification: private intake alone does not solve
that later editorial classification step. Neither a successful machine note nor
source revalidation supplies independent approval, verifies peer review, or
permits publishing these preprints. Original source identity, version, date,
rights, coverage, claim validation, and retry cooldown gates remain in place.

Review reports contain fixed-shape `selection` counts: considered, eligible,
deferred by limit, and bounded skip reason counts. Considered equals eligible
plus skipped; eligible equals attempted plus deferred. No source text or arbitrary
per-record metadata is added. Existing reports without this optional object
remain valid. Newly executed reading-run receipts bind reading policy version 2
and require these diagnostics. Older receipts remain parseable but are stale for
current finalization, so the next normal finalizer performs one bounded pass.
Once re-finalized, unchanged inputs do not trigger endless reruns; edition
permission still does not imply an exhausted private queue.

Offline regression coverage includes the actual four acquired PDFs and two EFF
partial documents at the November 10 checkpoint (two human-AI candidates, two
topic skips, two cooldowns), future title/abstract variants, computational and
clinical negatives, unverified venues, public holds after private success,
source nonretention, strict count/schema validation, and stale policy receipts.

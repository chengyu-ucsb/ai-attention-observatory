# Keep display excerpts separate from synthesis evidence

## Failure reproduced

The November 11 source audit recovered the primary Results narrative for
[Davor and colleagues](https://doi.org/10.3389/feduc.2026.1929091). The source
parser had previously missed Results headings nested under Methodology.

Recovering that section alone did not fix the writer input. Display-card
projection cut the Results from 4,188 to 3,000 characters. A further writer
budget retained only the opening statistical setup, without numerical path
findings. Later null and indirect results disappeared. The main study sample
was omitted while the digest selected a pilot sample. A hypothesis heading was
also selected as a finding. These were input-projection defects, not evidence
that the underlying study reported the omitted claims incorrectly.

## Boundaries

- Display cards can remain concise. Their `projection_coverage` records source
  and displayed character counts, including omitted material.
- Synthesis uses complete **retained** Results, Methods, Discussion and
  Limitations fields rather than shortened cards or selected digest headlines.
  This does not reconstruct missing source text or certify a complete article.
- Packet metadata records each supplied field's length and hash, upstream
  truncation, missing sections and omitted tables. Unknown extraction coverage
  remains explicitly unverified.
- Discussion cannot make an empirical source with no Results qualify for
  synthesis. Conceptual proposals remain separate from empirical findings.
  Accepted original readings retain their existing approval and provenance
  checks; raw sections do not replace their approved summaries.
- Hypothesis headings are not observed findings. Preliminary samples cannot
  stand in for the main study, and pilot-only text must not invent a main sample.
- Before every inference request, the complete serialized chat plus requested
  output budget must fit the configured context. Oversized inputs are deferred,
  never shortened to fit. Truncated or interrupted model output cannot pass.

## What the source audit does and does not establish

The repaired private projection preserves all 4,188 retained Results characters
and all 2,982 Limitations characters for the Davor paper. It preserves the null
social-influence result, indirect-association caveats and main sample of 350.
Methods and Discussion remain upstream-bounded excerpts; table cells remain
omitted. The numerical table's separate source review is not silently inserted
into the canonical record or treated as publication approval.

The animation paper's missing Results remain unavailable. Its Discussion must
not be used as verified measured-benefit evidence. No source recovery, approved
reading or new edition follows automatically from a passing projection test.

Offline regressions use synthetic text. Private source-packet audits do not add
raw papers or rejected model prose to this repository. Passing these checks is
not proof of factual consistency, full-article verification or successful
end-to-end generation. A fresh actual packet and its complete output still need
evaluation after source and context checks pass.

The exact Qwen tokenizer measured 12,467 tokens for the three-source payload
alone with its chat template. That already exceeds the old 12,288-token context,
before instructions, the draft or review output. This check made no completion
calls. The same pinned model successfully initialized a supported 24,576-token
context with non-mapped loading under a bounded memory limit. The compositor
uses that setting and still checks the actual full request before each call.
Initialization is not proof of generation-time memory use or successful
generation. Oversized requests remain deferred; removing late evidence is not
an acceptable way to make them fit.

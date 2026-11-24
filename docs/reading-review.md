# Editing an Observatory reading

Run `python scripts/build_public.py` and then `python scripts/build_reader.py`. New weekly items, archive additions, companion pieces and manually checked notes all pass through the same source screening and editorial review. The build uses current source material and recreates the review register on each run. Removed and ineligible sources drop out. Separate publication checks decide whether a reading is ready for the website.

## Write the introduction

Read the checked account and the available source. Ask what someone could explain to a friend after reading two sentences. Lead with what people did, observed or argued. Identify who or what was counted. Preserve the difference between what people reported and what a test measured. A useful second sentence names the detail that changes how the first should be understood. For commentary, attribute the argument and explain an example. Read a headline and introduction together and check the inference they invite against the source.

The source-writing prompts request everyday language. When a new reading has a complete, usable sentence in its editorial notes, the build can select it as a `prepared` introduction. A reading that still needs a rewrite appears in [the review register](../data/reading-review.json) with its reason. A `reviewed` introduction has an individually supplied edit tied to that version of the source account. Revisit entries with `source_changed` against the corrected evidence before renewing them.

To save an edit, use the article's canonical ID in [plain-reading-leads.json](../data/plain-reading-leads.json). Set `lead` and copy the current `summary.basis_sha256` from the register. Add `detail` and `limit` when a reader needs additional context on the article page. Check a number against its unit, denominator and source passage. The reader keeps the full source account and displays an abstract label on introductions based on abstracts.

## Choose a visual

Ask which comparison or sequence the reader would understand more easily by seeing it. Start with the readings in the next issue and continue through the archive. Each register entry records a visual outcome. A pending candidate includes a source or locator to check. An existing accepted adaptation is marked ready. An article with no suitable material can use prose.

Read the identified table, figure or passage. For counts, check the group, unit, denominator and time point. For interviews or argument maps, retain who said what. The Observatory can draw its own clearly attributed table or bar graphic from checked facts. Each chart keeps labels and values in an accessible table and links to its source. A caption by itself can identify a candidate but cannot supply unseen values.

Store accepted comparisons in [reviewed-visuals.json](../data/reviewed-visuals.json). Use an existing entry with the same type of source receipt as a working example. The record binds the labels, rows, chart scale, caption and source locator to their review. If prose explains a candidate better, save a `text_only` entry keyed by canonical ID with its current `source_fingerprint` and a brief `reason`. A change in the supporting evidence reopens that decision. If the numbers or relevant source passage are unavailable, keep the candidate pending.

After rebuilding, inspect both the card and the reading page. Check narrow-screen labels, the table headers, the linked source and the qualification next to the comparison. The weekly composer uses earlier published headlines to consider which question this week's sources can advance. Archived issues retain their publication text.

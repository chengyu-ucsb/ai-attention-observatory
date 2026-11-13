# Observatory interaction design

The Observatory should let a reader understand an idea, inspect its evidence,
and try a related activity without working through a long page of expanding
boxes. This document is the shared interaction contract for the main site,
article reader, permanent editions, and Experimental Lab. The
[typography guide](typography.md) owns fonts and reading sizes; the
[edition calendar](editions.md) owns dates, source windows, and permanent links.

## Three levels of information

| Level | What belongs here | Presentation |
| --- | --- | --- |
| Understand | The main idea, a few takeaways, a meaningful visual, and the limitation needed to interpret the claim | Visible at the start of the selected section |
| Explore | A related theme, method, example, comparison, or activity | A section selector, theme card, or bounded two-sided card |
| Inspect | Full context, source locators, publication history, and how the summary was made | A clearly named dialog or dedicated reading view |

Do not make the reader open a control to discover every substantive statement.
Do not show every level at once. Preserve complete text and source links when
changing its presentation; a shorter page must not become a shorter evidence
record.

## Choose the interaction for its job

| Pattern | Use it for | Contract |
| --- | --- | --- |
| Section selector | Major destinations within a long page | A labeled native select switches the visible section. A short button row can offer the same choices. Both controls stay synchronized. |
| Theme deck | The weekly edition's connected ideas | Show concise source-backed theme cards and one selected analysis at a time. Offer a full reading mode. Do not invent extra themes to fill a layout. |
| Two-sided card | One bounded question and its takeaway, or one concept and its explanation | An explicit button changes sides. The inactive side is unavailable to keyboard and assistive technology. Do not put an entire article or its only citation on a hidden reverse side. |
| Dialog card | Source details, full context, a figure, or methodology | Open on an explicit action, keep a visible close control, support Escape, and restore focus when closed. The background remains inert while modal. |
| Pagination | Long result collections | The research library starts with 12 results per page. Preserve the total matching count, provide previous/next controls and a page indicator, and reset the page when filters change. |
| Inline disclosure | A short, genuinely secondary detail | Use sparingly, especially inside an already layered view. Do not use an accordion as the default structure for every section. |

Native selects are navigation controls, not another way to hide every paragraph.
Changing a major section should replace the active reading area rather than
merely jump several screen lengths down an otherwise unchanged page. Keep the
page title and navigation available so the reader knows where they are.

One control should have one job. A card's main link opens its reading; a separate
control opens its explanation or changes its side. Avoid nested buttons, whole
cards with several competing click handlers, and hover-only information.

## Visual evidence and takeaways

Start with existing, checked text. A takeaway list can present the source's main
finding, method, and limitation as three distinct statements. Keep qualifiers
and attribution with the statement they qualify; do not turn a sentence into a
shorter, stronger claim merely to fit a card.

Use the simplest visual that explains the relationship:

- A reader map connects an edition's central question to its themes. Label it
  as a reading map; connecting lines do not imply a measured causal pathway.
- A sequence diagram can show a process explicitly described by the source.
  Keep a proposed process distinct from an experimentally established one.
- A comparison groups actual alternatives or findings with visible labels.
- A quantitative chart requires available values, units, a denominator where
  relevant, and source attribution. Collection counts describe the saved
  collection, not the whole field or the quality of the evidence.
- A conceptual illustration supports an idea without pretending to be a study
  figure. A source figure requires its existing attribution and reuse basis.

Every visual needs a useful text equivalent. Prefer HTML labels and lists around
SVG or CSS graphics so text can wrap and enlarge. Color must not be the only
encoding. Reuse the red Observatory palette and the shared type roles rather
than adding a new visual identity to each component.

## Brief notices, precise evidence

Use one short general notice on a reading surface, such as:

> AI-generated summary. AI can make mistakes; check the original source.

Put the fuller account of source checking, extraction, and editorial history in
an optional **About this summary** or **Source details** dialog. Do not repeat a
long generic warning on every card or under every paragraph.

Generic AI notices and research limitations have different purposes. Keep
essential distinctions near the relevant claim: abstract-based material,
preprints, a proposed framework, a correlation, a self-report outcome, or a
fictional demonstration. The brief general notice does not replace these facts.
Do not describe an AI check as independent human review.

For the Lab, the default notice is simply **Interactive demonstrations, not
cognitive tests.** A fictional scenario or simulated timeline also needs that
short identification beside its activity. Longer explanations belong in the
activity's background panel, not its main controls.

## A Lab that can grow

The Lab is a catalog with one active workbench. New additions and earlier
activities should be equally reachable without stacking every experiment on
one page. The existing Switch Lab, Return Point, and Assistance Dial remain
available as Classics; a newer activity does not silently replace them.

Each catalog entry needs a stable identifier, title, version, actual release
date, category/status, estimated duration, topic, evidence basis, and activity
implementation. The catalog supplies discovery; the workbench supplies the
selected activity. Use **All**, **New**, and **Classics** as views of the same
registry rather than maintaining separate copies of an activity list.

The catalog mounts in `#lab-catalog` and the selected experience in
`#lab-workbench`. Existing IDs are `switch`, `recovery`, and `assist`. The
November 2026 additions are `evidence-detective` and `notification-studio`.
Use `#lab?experiment=<id>` for an activity and `#lab` for the catalog so direct
links and browser Back/Forward resolve to the same selection. The collection
filter uses `new`, `all`, and `classic`; its default view highlights new work.

A new activity must work with keyboard and touch, explain the next action,
offer reset/replay, and provide a useful debrief. The debrief should explain the
choices or simulation mechanics, not diagnose the visitor or claim a real-world
cognitive benefit from a short browser exercise. Simulated outputs must follow
the stated rules and inputs; do not invent empirical effect sizes.

Keep stable links to an activity. Routine fixes can update its current version;
a substantially different mechanic should become a new version or new entry
while the older experience remains accessible. Mark an archived activity as
archived instead of quietly deleting it. Keep its description, instructions,
evidence basis, and release history with that entry. The
[Lab backlog](lab-backlog.md) records substantive changes and future work.

Activity state is session-only unless a separately implemented and approved
account/sync feature says otherwise. Do not add hidden local storage or imply
that visitor results sync across devices. The published website, catalog,
source code, and release history have their authoritative saved version in
GitHub; a visitor's transient trial is not a saved research record.

When an activity is left, its active timing and keyboard handlers must stop or
pause according to its existing rules. Returning must not count background
time as performance or allow a stale callback to change a different activity.

## Accessibility and navigation

- Use semantic headings, labeled form controls, native buttons, and native
  dialogs. Use a tab pattern only if its arrow-key and focus behavior are fully
  implemented; a group of ordinary labeled buttons is otherwise preferable.
- Only the active section or card face belongs in the reading and tab order.
  Hidden panels must not expose focusable descendants.
- Opening a dialog moves focus into it. Escape and the visible close button
  close it. Closing restores the initiating control when it still exists;
  navigation to another page uses that page's heading instead.
- Keep one modal open at a time. Preserve the actual content and its link
  handlers when it moves into a dialog; do not clone interactive content into
  duplicate IDs or leave a second, inaccessible copy behind.
- Keep direct article, edition, glossary, and source links working. Back and
  Forward must not strand the reader in a hidden pane or an abandoned overlay.
- Prefer a short fade or restrained card turn. Under
  `prefers-reduced-motion: reduce`, change states without rotation, scrolling
  animation, or other nonessential motion. Nothing should auto-flip or advance.
- Reflow at 320px, 390px, tablet, desktop, and 200% zoom. Dialogs fit the viewport
  and scroll internally when needed; close controls remain reachable. Preserve
  the typography guide's body sizes and 44px control targets.
- For generated permanent editions, JavaScript failure must leave a readable
  version of the complete edition and its source links. Print and full reading
  modes must not omit the inactive theme panels.

## Implementation and regression checks

The main site's shared interaction helpers belong with its application code
and shared styles. Article and issue renderers reuse those helpers rather than
creating different modal or navigation rules for each section. The standalone
edition renderer is `scripts/build_newsletter.py`; regenerate its HTML instead
of editing generated pages. Lab catalog behavior belongs in `lab-play.js` and
its styles in `lab-play.css`.

Test the reader's ability to get to the content, not a requirement that the
content use a particular `<details>` tag. Existing article, weekly issue,
newsletter, Lab, and browser tests must retain their source-fidelity checks
while allowing the new presentation patterns.

| Behavior to guard | Observable assertion |
| --- | --- |
| Short page sections | Exactly one major section is active by default; selector and buttons show the same selection; changing it reveals the requested content. |
| Complete research text | Every original paragraph, citation target, numeric result, and substantive limitation remains reachable without altered wording. |
| Reversible layers | Dialog opens, closes by button and Escape, restores focus, and leaves no duplicate IDs or stale background controls. |
| Two-sided cards | The same button can reveal and return; only the active face is exposed; reduced motion removes the turn. |
| Library paging | At most 12 results initially; totals remain accurate; next/previous work; filter changes cannot leave an empty out-of-range page. |
| Visual integrity | Values come from the intended records; conceptual maps do not imply causal findings; visual content has readable labels. |
| Preserved Lab | All three Classics remain launchable; each new registry entry opens its own workbench; leaving stops hidden interactions; reset clears the current trial. |
| Simulated activity | Identical inputs follow the stated rules; changed controls change the appropriate output; no output is mislabeled as measured human performance. |
| Publication continuity | Frozen source data, edition identities, dates, and RSS content stay intact when only the presentation changes. |
| Cross-device layout | Keyboard/touch flows and visible text pass the existing Chromium, Firefox, and WebKit checks at the supported responsive widths. |

Inspect real screenshots after these checks. A passing selector assertion does
not establish that a page is visually calm or that a diagram is legible.
Verify the published files and completed deployment before reporting the new
experience as live. The design stays within the existing static site and free
infrastructure.

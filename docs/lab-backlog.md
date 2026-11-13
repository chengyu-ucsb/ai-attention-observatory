# Experimental Lab improvement plan

The Lab is part of the Attention / AI Observatory. Keep it useful, playful,
accessible and clearly experimental. These activities are demonstrations, not
validated cognitive assessments or evidence that an intervention works.

## Cadence and release rules

- Review this backlog with each new weekly issue. Continue useful work between
  issues; do not wait for the monthly date to fix a defect or ship an improvement.
- Aim for at least one substantive tool update each month. A date change, rotated
  label or replay of unchanged material does not count as an update.
- After the issue is actually published, examine its verified sources for a
  suitable design question. A real study's findings require a direct source link
  and a checked account of the methods, outcomes and limitations. Otherwise use
  an explicitly fictional teaching scenario without attributing it to a study.
- Inspect main and open PRs first. Keep full-text acquisition and weekly issue
  publication independent of Lab development. Do not launch discovery/backfill
  jobs just to publish a Lab change.
- Keep information rich without burying visitors in prose. Use visual hierarchy,
  mechanism sketches, meaningful grouping and progressive disclosure; do not
  achieve a shorter page by silently dropping evidence or access caveats.
- Take the highest-value ready item below, implement it, add regression checks,
  and record the actual changes and checks. Ship small, reviewable changes.
- Leave the current public release date unchanged until substantive changes have
  passed checks and are ready to publish. Record blocked work honestly.

This document is the maintained backlog and acceptance checklist, not a scheduler.
Weekly publication follows the [fixed Monday edition calendar](editions.md), with
a separate coverage deadline. Lab development stays independent of retrieval and
publication so an experiment change cannot delay the newsletter. Verify completed
workflow output rather than assuming that a scheduled run published an issue.

## Collection architecture

The Lab has one catalog and one active workspace. `CATALOG` in `lab-play.js`
records each activity's stable `id`, title, status, version, release date, duration,
topic, and evidence basis. The initial **New experiments** view contains the two
November additions; **All experiments** and **Classic collection** keep the three
older activities discoverable. No activity opens until a visitor chooses it.

- Permanent entry links use `#lab?experiment=<id>`. Returning to `#lab` restores the
  collection. Browser back/forward and invalid IDs have explicit behavior.
- `#lab-catalog` hosts collection cards and the filter. `#lab-workbench` hosts the
  chosen activity's header and new activities. Existing classic panels retain
  their IDs, modes, session state, and keyboard navigation.
- Choosing another activity hides the classic panels and notifies their timing
  controller. Hidden intervals cannot silently enter a response-time result.
- Each activity owns its reset behavior. The existing visit-wide stop/reset also
  clears the new activity states. Results stay in memory; there is no account,
  analytics, backend, browser storage, or automatic export.
- Release a new version when behavior or teaching materials change. Keep stable
  IDs when the same activity improves. Preserve a replaced activity under a
  separate versioned ID if the change removes an experience people may revisit.
- Add new activities through the registry and a renderer. Provide keyboard
  controls, a concise evidence basis, reset/replay, narrow-screen behavior,
  reduced-motion support, a permanent entry link, and meaningful regression tests.
- A real study's numbers need a checked source and faithful mapping. Fictional
  scenarios and model outputs must remain labeled as such. A simulation is not
  an estimate of intervention effectiveness.

## Next work, in priority order

### P1 · Complete browser and accessibility coverage

Status: automated coverage now includes Playwright Chromium, Firefox and WebKit.
Installed Safari/Firefox, native browser zoom and assistive-technology review
remain open; patched automation builds do not replace those checks. See the
[verification PR](https://github.com/chengyu-ucsb/ai-attention-observatory/pull/35)
for run outcomes and the final merged revision.
Priority: correctness and access before new features.

- Run the new Chromium test at desktop and phone widths, then test real Safari
  and Firefox when available. Confirm there is no horizontal overflow and every
  choice remains reachable at 200% zoom and a 320 px viewport.
- Check screen-reader reading order, focus visibility, tab names, task cues and
  result announcements. Specifically check Switch Lab rule/number announcements
  and focus after the next Assistance Dial prompt replaces its button. Avoid
  announcing a fast stream of irrelevant timer data.
- Extend the new browser CI as coverage grows, without coupling it to external
  research fetching. Verify current action versions and runner compatibility
  under AGENTS.md before changing workflows.
- Acceptance: timed and untimed flows can be completed using keyboard alone;
  reduced-motion mode works; all dynamic transitions retain useful focus; no
  console errors. Keep the zero-dependency suite for rapid CI feedback.

### P1 · Give visitors control over a session

Status: implemented. Deterministic and hosted Chromium keyboard regressions pass.
Keep these checks green on future changes.

- Add a clear reset/stop action that cancels pending callbacks and clears only
  in-memory results. Explain what will be cleared before activation.
- Offer an untimed Switch Lab option and a short practice round, clearly separated
  from the 20-trial snapshot. Do not turn the demo into an attention score.
- Acceptance: reset during feedback, tab switching or replay never revives an old
  trial; practice results never enter the snapshot; no persistence or telemetry.

### P2 · Extend the scenario bank with a weekly source-informed question

Status: five scenarios prepared, including the 9 November source-informed
question about expert role-play versus intended-user outcomes. A question picker
makes each scenario directly reachable. The final PR checks and Pages deployment
determine which revision is published. Next: use a genuinely different question
from a later published issue, rather than adding another version of speed versus
learning or expert feedback versus learner outcomes.

- Review the current published issue for a meaningful task-design tension.
- Add one concise scenario with reflection, hint, full answer and feedback, or
  refine an existing one if a new scenario would be repetitive.
- Keep fictional teaching examples visibly distinct from actual research claims.
- Record which scenario changed and why. Do not append unbounded scenario lists.
- Acceptance: answer, hint and feedback agree; every option is defensible or clearly
  distinguishable; no unsupported statistics, causal claims or universal advice.

### P2 · Improve the comparison design and interpretation

Status: guided paired comparisons implemented and verified in hosted Chromium. Each pair presents both conditions once using parallel fictional
materials, with independently randomized starting condition and task variant.
Answer positions are shuffled. These templates are not validated equivalents;
real assistive-technology review and more rigorous material design remain open.

- Explore balanced condition order and matched Return Point materials so visitors
  can compare experiences without predictable answers or unnecessary repetition.
- Consider varying correct option position and offering a short reflection prompt.
- Explain the limits of fixed order, practice, timing precision and tiny samples.
  Do not claim the redesign validates the tool or estimates a treatment effect.
- Acceptance: condition/material/order are explicit; summaries never mix unrelated
  metrics or describe faster responses as better real-world attention.

### P2 · Make design precedents easier to explore

Status: four source-checked mobile cards implemented. Official feature guides
and relevant access limits replace the truncated table. See the
[design-precedent PR](https://github.com/chengyu-ucsb/ai-attention-observatory/pull/36)
for browser checks and publication verification.

- Check current product feature links and distinguish a product's own claims from
  independent evidence. Add a useful mobile comparison layout if needed.
- Acceptance: links reach the named feature; paid/account requirements are clear;
  no implied endorsement or unsupported effectiveness claims.

### P3 · Optional private session export

Status: needs a concrete use case before implementation.

- Consider a visitor-initiated plain-text download of only their current in-memory
  session and reflections, with clear non-diagnostic wording.
- No backend, account, analytics or automatic saving. Do not collect typed personal
  information merely to create a richer demo.

## November 2026 change record

Prepared 5 November 2026. Publication status must be checked in the repository's
Pages deployment; this date alone does not assert a live deployment.

- Fixed Return Point replay: each new task stays visible until the visitor starts
  the interruption. Added two original return tasks, for four in total.
- Fixed Switch Lab timing across activity tabs, browser visibility changes and
  navigation away from the Lab. Interrupted responses retain accuracy but are
  excluded from latency medians. Return Point also omits interrupted timings.
- Prevented tab-navigation arrow keys and held keys from submitting answers.
- Added source-checking and assisted-performance-versus-learning scenarios, for
  four fictional scenarios at all three assistance levels.
- Kept the existing visual design; added a compact, dated change note and useful
  focus targets for dynamic Return Point stages and Switch Lab results.
- Extended deterministic regressions for timing races, visibility, replay, keyboard
  handling, all recovery tasks and all assistance modes. Added an optional
  real-browser test with a clearly scoped fixture.

### Session-control and accessibility follow-up

- Added a visit-wide stop/reset with an explanation before activation. It cancels
  pending Switch callbacks, clears in-memory results across activities and keeps
  selected modes. A generation guard prevents stale callbacks from reviving play.
- Added untimed, visitor-paced 20-turn snapshots and a separate four-turn practice
  introduction. Practice results are discarded; untimed snapshots record no
  response times. No persistence, account, network request or telemetry was added.
- Kept answer focus during timed feedback, scoped arrow shortcuts to answer
  buttons, added Home/End tab navigation and concise rule/number announcements.
  Assistance Dial moves focus to feedback and then the new prompt; symbolic
  Return Point choices have spoken labels. No timer values are announced.
- Clarified fixed order, task identity, answer repetition, device/input timing and
  small-sample limitations. Added reflection questions without making an
  intervention-effectiveness or cognitive-assessment claim.
- Extended deterministic tests for reset races, practice isolation, untimed
  progression and focus. Expanded hosted Chromium coverage to 320, 390 and
  1280 px, plus a 640 px viewport at 2x pixel density to approximate zoom/reflow,
  and keyboard completion. This is not a substitute for checking native browser
  zoom or real screen readers. CSS body zoom was rejected as a proxy because it
  does not update viewport media-query breakpoints.
- Local JavaScript syntax, deterministic regressions and browser-test Python
  compilation pass. Local Chromium launch is blocked by the execution
  environment's socket restriction; use the actual PR CI outcome below before
  calling browser or visual checks passed. No workflow definitions were changed.
- [Hosted Chromium verification](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42113488191)
  passed all four viewport/density configurations, keyboard flows, held-Enter
  protection and full-app navigation/offline fallback. Desktop, 320 px phone and
  reflow screenshots were inspected.
  [Repository checks](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42113488319)
  passed all 216 Python tests and 69 reading-page checks. Final PR checks and
  Pages deployment are authoritative for the published revision.

### 6 November 2026 · Paired Return Point comparisons

Verified in the review branch; the final PR checks and actual Pages deployment
determine publication status, not this date.

- Added an optional guided two-round comparison with two pairs of original,
  parallel fictional tasks. Each pair uses a different task variant in each
  condition. Starting condition and task variant are randomized independently;
  correct answer positions are shuffled in all Return Point rounds.
- Showed the assigned condition, task, pair and round throughout the flow.
  The second task remains readable until the visitor starts its interruption.
- Kept comparison results separate from single-round history. Exit discards only
  the comparison and restores the selected manual mode; stop/reset clears all
  visit results. Replays start a fresh pair rather than adding to an old result.
- Added a chronological two-response debrief with no difference score. It explains
  unvalidated task equivalence, repeated distractions, answer-revealing cues,
  reading/input time and order/practice effects. No causal or diagnostic claim.
- Extended deterministic regressions across all four condition/material order
  combinations, all answer positions, both pairs, interrupted timing, exit and
  mid-comparison reset. Extended hosted keyboard/viewport checks for both pairs.
- Local syntax, deterministic regressions and Python compilation pass.
  [Hosted Chromium checks](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42143224572)
  passed at 1280, 390 and 320 px and the 640 px/2x-density reflow approximation.
  Desktop/phone comparison screenshots were inspected. The focused prompt now
  includes the visible checkpoint in its accessible description; actual screen
  reader testing remains open.
  [Repository checks](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42143224586)
  passed 240 Python tests and 69 reading-page checks with no Actions warnings.

### 6 November 2026 · Cross-engine verification

- Added independent Chromium, Firefox and WebKit jobs with failure isolation
  and separate screenshots. Each runs every Lab flow at desktop/phone widths and
  the effective-viewport/density reflow approximation, including paired rounds.
- Added computed accessible-name/description assertions for activity tabs and the
  Return Point checkpoint. These are browser-level checks, not a screen-reader
  evaluation. Playwright's Firefox and WebKit builds are patched automation
  builds, not installed Firefox or Safari on a real device.
- Verified current official action releases on 6 November: checkout v7.0.1,
  setup-python v7.1.0 and upload-artifact v7.0.2 all use Node 24. Ubuntu 24.04 and
  Python 3.12 meet the current Playwright requirements; recent observed Actions
  runners (2.338.2) exceed checkout's 2.327.1 minimum.
- Updated the test-only Playwright pin to
  [1.64.1](https://github.com/microsoft/playwright-python/releases/tag/v1.64.1),
  the current official release, including its Node 24.22.1 security update.
- Local deterministic regressions, Python compilation and workflow structure
  checks pass. Final hosted engine outcomes are recorded in the verification PR;
  actual run logs, not the presence of a workflow, establish a passed check. No
  research acquisition, external inference or public release-date change.

### 6 November 2026 · Source-linked design precedents

- Replaced truncated, horizontally scrolling product rows with four readable
  cards in the existing cream/red visual style. Mechanism sketches and key
  access limits support a quick scan. Complete access notes, design questions
  and supplementary sources remain in keyboard-operable native disclosures.
  The main official guide stays visible on each card. Official feature guides and
  plan references are ordinary links with distinct labels, visible focus and
  48 px minimum-height targets (checked against a 44 px rendered threshold).
- Kept the cards in the page so unavailable archive data does not remove them.
  Existing research records and their reading pages remain unchanged.
- Checked official documentation on 6 November: one sec Intention Tracking is
  iPhone/iPad-specific, and its plan tier is not stated in the comparison table;
  Freedom has a free account tier for immediate sessions up to two hours, while
  scheduling/longer sessions/Locked Mode require Premium; Apple Focus filters
  narrow supported app content and do not sync across devices; Android Focus
  mode pauses selected apps and notifications, with availability varying by
  device. No effect statistic or product endorsement was added.
- Source and access links are on each card. Apple's canonical guide was
  retrieved through its official redirect after an initial rate limit; later
  requests were again rate-limited. The guide was not treated as unavailable
  or as proof that every Apple device supports the feature.
- Added deterministic card/link/detail-preservation checks plus keyboard
  disclosure opening/closing, control order, target size,
  viewport bounds and offline-archive checks to the browser suite. Local syntax,
  deterministic tests and Python compilation pass. Chromium and WebKit checks
  passed at all four viewport/density configurations on the review branch;
  desktop and 320 px WebKit card screenshots were inspected. The final PR
  checks and actual Pages deployment remain authoritative for the release.

### 9 November 2026 · Whose experience was tested?

- Reviewed the latest actually published issue, [The Attention Brief #04,
  7 November](https://chengyu-ucsb.github.io/ai-attention-observatory/issues/2026-11-07.html).
  The 9 November source packet was not a new published issue at review time.
- Added a fifth original Assistance Dial question: interviews with researchers
  role-playing students can inform design, without establishing students'
  experiences or learning benefits. Reflection, hint and answer levels retain
  that distinction; the main feedback states it before any disclosure is opened.
- Added a native question picker that preserves the help level, keeps keyboard
  focus while announcing the chosen question and clears the previous response. Replay, next and reset
  remain available. No persistence, telemetry or external inference was added.
- An optional source note links the pinned v1 preprint and the published issue.
  Source checked: Lin, Deng, Pan, Yu and Cristea, *Exploring AI Peer in
  Collaborative Mathematics Learning*, 28 October 2026,
  [Methods §4.2, p. 6](https://arxiv.org/pdf/2610.38990v1#page=6) and
  [Limitations §7, p. 11](https://arxiv.org/pdf/2610.38990v1#page=11).
  Seven researchers took a student perspective with one prototype, then gave
  interviews. No student learning test or comparison of teaching conditions was
  reported. This is an exploratory preprint with unverified peer-review status;
  the Lab question is not a replication or a validated assessment.
- Added deterministic checks for every question/help level, direct selection,
  incorrect answers, source-link identity and clearing stale feedback. Browser
  checks now cover the new question, keyboard selection and disclosure opening/closing, link
  focus/target sizes and selection/reset at all existing viewport/engine sizes.
- Preserved pending PR #38's separate layered-debrief work and unrelated open
  reading/source-pipeline changes. No research collection or publication workflow
  was modified or manually dispatched.
- Local JavaScript syntax, deterministic Lab regressions and Python compilation
  pass. Hosted engine checks and final Pages publication must be verified on the
  exact PR revision; this record alone is not a deployment claim.

### 13 November 2026 · A growing experiment collection

Implementation prepared for this release; the completed PR checks and Pages
publication establish the deployed revision.

- Added **Evidence Detective**: three fictional dossiers, reversible evidence
  cards, a case picker, three distinct verdicts, targeted feedback, progression,
  and reset. The activity makes a claim's participants, design, and measured
  outcome inspectable before a visitor judges its scope. It reports no ability
  score and does not present fictional cases as real research.
- Added **Notification Studio**: a fixed stream of twelve invented messages over
  thirty simulated minutes. Visitors choose immediate, ten-minute batches, or
  end-only delivery, with an urgent-message exception. A live timeline and three
  arithmetic summaries show alert moments, average wait, and longest gap. Each
  delivery has an inspectable card. Full calculation rules remain available.
- Added a versioned registry and a compact collection landing page. New and
  classic filters preserve Switch Lab, Return Point, and Assistance Dial. One
  chosen activity occupies the workspace; direct links and browser history keep
  exploration navigable.
- Used evidence-card turns, a live model, and native dialog cards rather than
  stacking more accordion sections. Motion respects the visitor's preference;
  dialogs restore focus and have keyboard dismissal. Controls remain usable
  when the timeline is narrow.
- Added an offline catalog suite for registry integrity, landing and deep links,
  classic preservation, all dossier verdicts, resets/focus, all delivery modes,
  arithmetic invariants, modal restoration, and invalid-route fallback. Existing
  classic activity regressions remain in place.

## Checks for every release

1. `node --check lab-play.js`
2. `node tests/validate_playground.cjs` and `node tests/validate_lab_catalog.cjs`
3. With Playwright and the chosen browser installed:
   `python tests/validate_playground_browser.py --executable-path /usr/bin/chromium`
   (omit the flag when using Playwright's bundled Chromium). Also run with
   `--browser firefox` and `--browser webkit` after installing those engines.
4. Run the repository's existing application and Python tests in a full checkout.
5. Inspect desktop/phone screenshots and complete each new or changed activity, plus the preserved classic flows.
6. Review the diff, then create a draft PR. Do not claim tests passed if the
   environment could not run them. Verify the real Pages build and public Lab
   after publication; inspect logs for warnings as well as errors.

Initial hosted verification on 5 November 2026: [Lab check run 1](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42109717710)
passed Chromium at 1280 px and 390 px, including all activities and scenarios.
Desktop and phone screenshots were inspected; the narrow phone rule layout was
then simplified. [Repository checks](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42109717477)
passed all 216 Python tests and 69 reading-page checks. Local Chromium launch was
unavailable, so browser verification used the repository's hosted test runner.
The current PR's latest checks and the Pages deployment remain the authoritative
release status, not this historical record.




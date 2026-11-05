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
- Take the highest-value ready item below, implement it, add regression checks,
  and record the actual changes and checks. Ship small, reviewable changes.
- Leave the current public release date unchanged until substantive changes have
  passed checks and are ready to publish. Record blocked work honestly.

This document is the maintained backlog and acceptance checklist, not a scheduler.
The weekly edition itself runs after successful full-text backlog processing, with
Monday/Tuesday 14:40 UTC recovery schedules. Review its completed output rather
than assuming a scheduled run published an issue.

## Next work, in priority order

### P1 · Complete browser and accessibility coverage

Status: implemented in this change, pending hosted Chromium checks; real Safari,
Firefox, native browser zoom and assistive-technology review remain open.
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

Status: implemented in this change; deterministic regressions pass. Hosted
keyboard/browser verification is required before publication.

- Add a clear reset/stop action that cancels pending callbacks and clears only
  in-memory results. Explain what will be cleared before activation.
- Offer an untimed Switch Lab option and a short practice round, clearly separated
  from the 20-trial snapshot. Do not turn the demo into an attention score.
- Acceptance: reset during feedback, tab switching or replay never revives an old
  trial; practice results never enter the snapshot; no persistence or telemetry.

### P2 · Extend the scenario bank with a weekly source-informed question

Status: ready after source review. First candidate: performance versus learning.

- Review the current published issue for a meaningful task-design tension.
- Add one concise scenario with reflection, hint, full answer and feedback, or
  refine an existing one if a new scenario would be repetitive.
- Keep fictional teaching examples visibly distinct from actual research claims.
- Record which scenario changed and why. Do not append unbounded scenario lists.
- Acceptance: answer, hint and feedback agree; every option is defensible or clearly
  distinguishable; no unsupported statistics, causal claims or universal advice.

### P2 · Improve the comparison design and interpretation

Status: interpretation improved; balanced order and matched-material redesign
remain open. Current rounds now identify task and round number, explain answer
repetition and order/practice limits, and include reflection prompts.

- Explore balanced condition order and matched Return Point materials so visitors
  can compare experiences without predictable answers or unnecessary repetition.
- Consider varying correct option position and offering a short reflection prompt.
- Explain the limits of fixed order, practice, timing precision and tiny samples.
  Do not claim the redesign validates the tool or estimates a treatment effect.
- Acceptance: condition/material/order are explicit; summaries never mix unrelated
  metrics or describe faster responses as better real-world attention.

### P2 · Make design precedents easier to explore

Status: source verification needed.

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

## Checks for every release

1. `node --check lab-play.js`
2. `node tests/validate_playground.cjs`
3. With Playwright/Chromium installed:
   `python tests/validate_playground_browser.py --executable-path /usr/bin/chromium`
   (omit the flag when using Playwright's bundled Chromium).
4. Run the repository's existing application and Python tests in a full checkout.
5. Inspect desktop/phone screenshots and complete all three activities manually.
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


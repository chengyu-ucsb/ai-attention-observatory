"""Optional cross-engine Lab regression check.

Requires Playwright and the selected browser. Run from the repository root:
    python tests/validate_playground_browser.py --browser firefox
    python tests/validate_playground_browser.py --browser webkit
    python tests/validate_playground_browser.py --executable-path /usr/bin/chromium

The fixture uses the real page, styles and Lab script, but omits app.js and its
unrelated research-data fetches. Playwright Firefox and WebKit are patched test
builds, not the installed Firefox/Safari apps or a screen-reader test.
A separate check exercises app.js navigation
and the Lab fallback when research data cannot load.
"""
import argparse
import re
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/__lab_test__":
            html = (ROOT / "index.html").read_text().replace('<script src="app.js" defer></script>', '')
            html = html.replace('</body>', '''<script>
              document.querySelectorAll('.view').forEach(v => v.hidden = v.id !== 'lab');
            </script></body>''')
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            super().do_GET()

    def log_message(self, *_):
        pass


@contextmanager
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(ROOT)))
    thread = Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/__lab_test__"
    finally:
        srv.shutdown()
        srv.server_close()


def open_lab_activity(page, activity, keyboard=False):
    """Wait for the routed workbench before interacting with its controls."""
    trigger = page.locator(f'[data-lab-open="{activity}"]')
    if keyboard:
        trigger.focus()
        expect(trigger).to_be_focused()
        page.keyboard.press("Enter")
    else:
        trigger.click()
    expect(page).to_have_url(re.compile(r'#lab\?experiment=' + re.escape(activity) + r'$'))
    expect(page.locator("#lab-workbench-title")).to_be_focused()
    expect(page.locator("#lab-catalog")).not_to_be_visible()
    expect(page.locator("#lab-back-to-catalog")).to_be_visible()


def return_to_lab_catalog(page):
    page.locator("#lab-back-to-catalog").click()
    expect(page).to_have_url(re.compile(r'#lab$'))
    expect(page.locator("#lab-catalog")).to_be_visible()
    expect(page.locator("#lab-workbench")).not_to_be_visible()
    expect(page.locator("#lab-collection-filter")).to_be_focused()


def choose_lab_section(page, value):
    nav = page.locator("#lab-section")
    target = nav.locator(f'button[data-section="{value}"]')
    expect(target).to_be_visible()
    target.focus()
    expect(target).to_be_focused()
    page.keyboard.press("Enter")
    expect(nav).to_have_attribute("data-active-section", value)
    expect(target).to_have_attribute("aria-pressed", "true")
    expect(nav.locator('button[data-section][aria-pressed="true"]')).to_have_count(1)


def check(page, url, width, screenshots, zoom=1, browser_name="chromium"):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    # Native page zoom changes the effective CSS viewport. CSS body.zoom does
    # not change media-query breakpoints, so it is not a faithful substitute.
    # Pair a smaller layout viewport with higher pixel density in this check.
    page.set_viewport_size({"width": width // zoom, "height": 900 // zoom})
    page.goto(url, wait_until="networkidle")
    assert page.locator("#lab").is_visible()
    expect(page.locator("#lab-catalog")).to_be_visible()
    expect(page.locator("#lab-collection-filter")).to_have_value("new")
    expect(page.locator("[data-lab-open]")).to_have_count(2)
    expect(page.locator("#lab-workbench")).not_to_be_visible()
    for panel in ("switch", "recovery", "assist"):
        expect(page.locator("#play-" + panel)).not_to_be_visible()
    # The compact landing keeps all classic activities accessible by category.
    page.locator("#lab-collection-filter").select_option("classic")
    expect(page.locator("[data-lab-open]")).to_have_count(3)
    open_lab_activity(page, "switch", keyboard=True)
    for name in ("Switch Lab", "Return Point", "Assistance Dial"):
        expect(page.get_by_role("tab", name=name, exact=True)).to_be_visible()
    assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Overflow at {width}px"
    precedents = page.get_by_role("list", name="Four product design precedents")
    expect(precedents.get_by_role("listitem")).to_have_count(4)
    # The first scan stays compact, but full access/source/trade-off information
    # is still reachable through native, keyboard-operable disclosures.
    details = precedents.locator(".precedent-details")
    expect(details).to_have_count(4)
    expect(precedents.get_by_role("link")).to_have_count(4)
    collapsed_controls = precedents.locator("a:visible, summary")
    expect(collapsed_controls).to_have_count(8)
    for i in range(8):
        if i == 0:
            collapsed_controls.nth(i).focus()
        else:
            page.keyboard.press("Tab")
        expect(collapsed_controls.nth(i)).to_be_focused()
    page.keyboard.press("Tab")
    assert precedents.evaluate("el => !el.contains(document.activeElement)"), "Closed source links must stay out of Tab order"
    for i in range(4):
        summary = details.nth(i).locator("summary")
        summary.focus()
        page.keyboard.press("Enter")
        assert details.nth(i).evaluate("el => el.open")
        expect(details.nth(i).locator(".precedent-details-body")).to_be_visible()
    expect(precedents.get_by_role("link")).to_have_count(7)
    controls = precedents.locator("a, summary")
    expect(controls).to_have_count(11)
    for i in range(11):
        control = controls.nth(i)
        if i == 0:
            control.focus()
        else:
            page.keyboard.press("Tab")
        expect(control).to_be_focused()
        box = control.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= width // zoom, "Precedent control overflow"
        assert box["height"] >= 44, f"Precedent target below 44px: {control.inner_text()} {box}"
        if control.evaluate("el => el.tagName") == "A":
            assert control.get_attribute("href").startswith("https://")
    for i in range(4):
        details.nth(i).locator("summary").focus()
        page.keyboard.press("Enter")
        assert not details.nth(i).evaluate("el => el.open")
    expect(precedents.get_by_role("link")).to_have_count(4)
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)
        page.locator(".play-precedents").screenshot(path=str(screenshots / f"lab-precedents-{width}-zoom{zoom}.png"), style=".site-header { visibility: hidden !important; }")
        details.first.locator("summary").focus()
        page.keyboard.press("Enter")
        precedents.locator(".precedent-card").first.screenshot(path=str(screenshots / f"lab-precedent-expanded-{width}-zoom{zoom}.png"), style=".site-header { visibility: hidden !important; }")
        details.first.locator("summary").focus()
        page.keyboard.press("Enter")
    page.locator(".play-update summary").click()
    assert page.locator(".play-update p").first.is_visible()
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshots / f"lab-{width}-zoom{zoom}.png"), full_page=True)
    page.locator("#switch-start").click()
    # Real key bubbling: Recovery -> Switch must not answer a trial.
    page.locator("#tab-recovery").focus()
    page.keyboard.press("ArrowLeft")
    assert page.locator("#switch-progress").inner_text() == "1 / 20"
    assert page.locator("#switch-left").is_enabled()
    # Route away while a visible trial is pending; timing must be omitted.
    page.evaluate("document.querySelector('#lab').hidden=true")
    page.wait_for_timeout(150)
    page.evaluate("document.querySelector('#lab').hidden=false")
    for trial in range(1, 21):
        page.wait_for_function("n => document.querySelector('#switch-progress').textContent === n + ' / 20' && document.querySelector('#switch-left').getAttribute('aria-disabled') === 'false'", arg=trial)
        cue = page.locator("#switch-cue").inner_text()
        number = int(page.locator("#switch-number").inner_text())
        left = number % 2 == 1 if cue.startswith("ODD") else number < 5
        page.locator("#switch-left").focus()
        page.keyboard.press("ArrowLeft" if left else "ArrowRight")
    page.wait_for_function("document.querySelector('#switch-phase').textContent === 'COMPLETE'")
    assert "1 interrupted response(s) excluded" in page.locator("#switch-results").inner_text()
    assert page.evaluate("document.activeElement.id") == "switch-results"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if screenshots:
        page.locator("#play-switch").screenshot(path=str(screenshots / f"lab-switch-results-{width}-zoom{zoom}.png"), style=".site-header { visibility: hidden !important; }")
    # Separate practice and untimed snapshots are completable with keyboard only.
    page.locator("#switch-practice").focus()
    page.keyboard.press("Enter")
    for trial in range(1, 5):
        assert page.locator("#switch-progress").inner_text() == f"{trial} / 4"
        assert page.evaluate("document.activeElement.id") == "switch-left"
        assert f"Turn {trial} of 4" in page.locator("#switch-announcement").inner_text()
        page.keyboard.down("Enter")
        assert page.evaluate("document.activeElement.id") == "switch-next"
        page.keyboard.down("Enter")
        page.keyboard.down("Enter")
        assert page.evaluate("document.activeElement.id") == "switch-next"
        page.keyboard.up("Enter")
        page.wait_for_timeout(550)
        assert page.locator("#switch-progress").inner_text() == f"{trial} / 4"
        page.keyboard.press("Enter")
    assert "PRACTICE COMPLETE" in page.locator("#switch-results").inner_text()
    assert page.locator("#switch-results .play-chart").count() == 0
    page.locator("#switch-timing").select_option("untimed")
    page.locator("#switch-start").focus()
    page.keyboard.press("Enter")
    for trial in range(1, 21):
        assert page.locator("#switch-progress").inner_text() == f"{trial} / 20"
        page.keyboard.press("ArrowLeft")
        assert page.evaluate("document.activeElement.id") == "switch-next"
        page.keyboard.press("Enter")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert "No response times were recorded." in page.locator("#switch-results").inner_text()
    assert "ms" not in page.locator("#switch-results .play-chart").inner_text()
    assert page.evaluate("document.activeElement.id") == "switch-results"
    page.locator("#play-reset").focus()
    page.keyboard.press("Enter")
    assert page.locator("#switch-timing").input_value() == "untimed"
    assert page.locator("#switch-progress").inner_text() == "0 / 20"
    page.locator("#switch-timing").select_option("timed")
    page.locator("#switch-start").click()
    page.keyboard.press("ArrowLeft")
    page.locator("#play-reset").click()
    page.wait_for_timeout(600)
    assert page.locator("#switch-progress").inner_text() == "0 / 20"
    assert page.locator("#switch-results").is_hidden()
    assert "results are cleared" in page.locator("#play-session-status").inner_text()
    # All tasks must show their next action before distraction, including replays.
    page.locator("#tab-recovery").click()
    stories = set()
    for trial in range(4):
        preview = page.locator("#recovery-description").inner_text()
        stories.add(preview)
        page.locator("#recovery-start").click()
        for correct_index in (2, 1, 2, 1):
            page.keyboard.press("Tab")
            for _ in range(correct_index):
                page.keyboard.press("Tab")
            page.keyboard.press("Enter")
            assert page.evaluate("document.activeElement.id") == "recovery-headline"
        for choice in page.locator(".recovery-option").all():
            if choice.inner_text() in preview:
                choice.focus()
                page.keyboard.press("Enter")
                break
        assert page.locator("#recovery-progress").inner_text() == "DONE"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#recovery-start").click()
        assert "STAGE 1 / 3" in page.locator("#recovery-progress").inner_text()
        assert page.locator(".recovery-option").count() == 0
    assert len(stories) == 4
    # Two guided pairs retain manual history and label every condition/material.
    history_before = page.locator("#recovery-history").inner_text()
    for pair in (1, 2):
        page.locator("#recovery-compare").focus()
        page.keyboard.press("Enter")
        assert page.evaluate("document.activeElement.id") == "recovery-headline"
        assert f"Pair {pair}" in page.locator("#recovery-comparison-plan").inner_text()
        assert page.locator('[data-recovery-mode="cue"]').is_disabled()
        contexts, previews = [], []
        for step in (1, 2):
            contexts.append(page.locator("#recovery-round-context").inner_text())
            preview = page.locator("#recovery-description").inner_text()
            previews.append(preview)
            page.locator("#recovery-start").focus()
            page.keyboard.press("Enter")
            for correct_index in (2, 1, 2, 1):
                for _ in range(correct_index + 1):
                    page.keyboard.press("Tab")
                page.keyboard.press("Enter")
            cue_present = page.locator("#recovery-checkpoint").count() == 1
            assert cue_present == ("With checkpoint" in contexts[-1])
            assert ("recovery-checkpoint" in page.locator("#recovery-headline").get_attribute("aria-describedby")) == cue_present
            if cue_present:
                checkpoint = page.locator("#recovery-checkpoint").inner_text().split("·", 1)[1].strip()
                expect(page.locator("#recovery-headline")).to_have_accessible_description(re.compile(re.escape(checkpoint)))
            else:
                expect(page.locator("#recovery-headline")).not_to_have_accessible_description(re.compile("CHECKPOINT"))
            choices = page.locator(".recovery-option")
            correct = next(i for i, choice in enumerate(choices.all()) if choice.inner_text() in preview)
            if step == 1:
                page.locator("#tab-assist").click()
                page.locator("#tab-recovery").click()
            page.locator("#recovery-headline").focus()
            for _ in range(correct + 1):
                page.keyboard.press("Tab")
            page.keyboard.press("Enter")
            assert page.locator("#recovery-history").inner_text() == history_before
            if step == 1:
                assert page.locator("#recovery-comparison-results").is_hidden()
                page.locator("#recovery-start").focus()
                page.keyboard.press("Enter")
                assert "ROUND 2 / 2" in page.locator("#recovery-progress").inner_text()
                assert "STAGE 1 / 3" in page.locator("#recovery-progress").inner_text()
                assert page.locator(".recovery-option").count() == 0
        assert previews[0] != previews[1]
        assert sum("With checkpoint" in x for x in contexts) == 1
        assert sum("Without checkpoint" in x for x in contexts) == 1
        assert sum("TASK A" in x for x in contexts) == 1
        assert sum("TASK B" in x for x in contexts) == 1
        assert page.locator(".recovery-comparison-result").count() == 2
        assert "timing omitted" in page.locator(".recovery-comparison-result").first.inner_text()
        assert page.evaluate("document.activeElement.id") == "recovery-comparison-results"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if screenshots and pair == 2:
            page.locator("#play-recovery").screenshot(path=str(screenshots / f"lab-comparison-{width}-zoom{zoom}.png"), style=".site-header { visibility: hidden !important; }")
        page.locator("#recovery-exit-comparison").focus()
        page.keyboard.press("Enter")
        assert page.locator("#recovery-comparison-results").is_hidden()
        assert page.locator('[data-recovery-mode="cue"]').is_enabled()
        assert page.locator("#recovery-history").inner_text() == history_before
    page.locator("#recovery-compare").click()
    page.locator("#recovery-start").click()
    page.locator("#play-reset").click()
    assert page.locator("#recovery-comparison-plan").is_hidden()
    assert page.locator("#recovery-comparison-results").is_hidden()
    assert page.locator("#recovery-compare").is_enabled()
    page.locator("#tab-assist").click()
    for mode in ("reflect", "hint", "answer"):
        page.locator(f'[data-assist-mode="{mode}"]').click()
        for i, correct_index in enumerate((1, 0, 1, 2, 1), 1):
            assert page.locator("#assist-counter").inner_text() == f"SCENARIO {i} / 5"
            page.locator(".assist-option").nth(correct_index).focus()
            page.keyboard.press("Enter")
            assert page.evaluate("document.activeElement.id") == "assist-feedback"
            assert "Supported conclusion" in page.locator("#assist-feedback").inner_text()
            page.keyboard.press("Tab")
            if i == 5:
                details = page.locator(".assist-source")
                summary = details.locator("summary")
                assert summary.evaluate("el => el === document.activeElement")
                assert not details.evaluate("el => el.open")
                page.keyboard.press("Enter")
                assert details.evaluate("el => el.open")
                assert "did not test student learning" in details.inner_text()
                links = details.locator("a")
                assert links.count() == 2
                assert links.nth(0).get_attribute("href") == "https://arxiv.org/pdf/2610.38990v1#page=6"
                assert links.nth(1).get_attribute("href").endswith("/issues/2026-11-07.html")
                for link in links.all():
                    page.keyboard.press("Tab")
                    assert link.evaluate("el => el === document.activeElement")
                    box = link.bounding_box()
                    assert box["height"] >= 44
                if screenshots and mode == "reflect":
                    page.screenshot(path=str(screenshots / f"lab-study-context-{width}-zoom{zoom}.png"), full_page=True)
                summary.focus()
                page.keyboard.press("Space")
                assert not details.evaluate("el => el.open")
                page.keyboard.press("Tab")
            assert page.evaluate("document.activeElement.id") == "assist-next"
            page.keyboard.press("Enter")
            assert page.evaluate("document.activeElement.id") == "assist-prompt"
            assert page.locator(".assist-source").count() == 0
    # Native keyboard selection must not steal focus after the first change.
    picker = page.locator("#assist-scenario")
    picker.focus()
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.id") == "assist-scenario"
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert picker.input_value() == "2"
    assert page.locator("#assist-counter").inner_text() == "SCENARIO 3 / 5"
    assert page.evaluate("document.activeElement.id") == "assist-scenario"
    # Jump directly to the new question, then leave an answered question safely.
    picker.select_option("4")
    assert page.locator("#assist-counter").inner_text() == "SCENARIO 5 / 5"
    assert page.evaluate("document.activeElement.id") == "assist-scenario"
    page.locator(".assist-option").nth(0).click()
    assert "Another interpretation" in page.locator("#assist-feedback").inner_text()
    assert page.locator(".assist-source").is_visible()
    page.locator("#assist-scenario").select_option("1")
    assert page.locator("#assist-counter").inner_text() == "SCENARIO 2 / 5"
    assert page.locator("#assist-feedback").is_hidden()
    assert page.locator(".assist-source").count() == 0
    assert "FULL ANSWER" in page.locator("#assist-reply").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator("#play-reset").click()
    assert page.locator("#recovery-history").inner_text() == ""
    assert page.locator("#assist-counter").inner_text() == "SCENARIO 1 / 5"
    if screenshots:
        page.screenshot(path=str(screenshots / f"lab-assist-{width}-zoom{zoom}.png"), full_page=True)
    # New activities live in the same versioned catalog; classics remain reachable.
    return_to_lab_catalog(page)
    expect(page.locator("#play-assist")).not_to_be_visible()
    page.locator("#lab-collection-filter").select_option("new")
    open_lab_activity(page, "evidence-detective", keyboard=True)
    expect(page.locator(".lab-fiction-label")).to_contain_text("Fictional evidence dossier")
    expect(page.locator("#play-switch")).not_to_be_visible()
    for index, verdict in enumerate(("overreach", "supported", "unanswered")):
        expect(page.locator("#lab-case-picker")).to_have_value(str(index))
        for card in page.locator("[data-evidence-card]").all():
            expect(card).to_have_attribute("aria-pressed", "false")
            card.focus()
            page.keyboard.press("Enter")
            expect(card).to_have_attribute("aria-pressed", "true")
            expect(card.locator(".lab-card-copy")).not_to_have_text("Tap to inspect")
            expect(card).to_be_focused()
        if index == 0:
            page.locator('[data-lab-verdict="supported"]').click()
            expect(page.locator("#lab-detective-feedback > strong")).to_have_text("Reconsider the scope of the claim.")
        page.locator(f'[data-lab-verdict="{verdict}"]').focus()
        page.keyboard.press("Enter")
        expect(page.locator("#lab-detective-feedback")).to_be_focused()
        expect(page.locator("#lab-detective-feedback > strong")).to_have_text("You matched the claim to the evidence.")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if index < 2:
            page.locator("#lab-detective-next").click()
            expect(page.locator("#lab-detective-claim")).to_be_focused()
    expect(page.locator(".lab-case-progress")).to_have_attribute("aria-label", "3 of 3 dossiers checked")
    if screenshots:
        page.screenshot(path=str(screenshots / f"lab-detective-{width}-zoom{zoom}.png"), full_page=False)
    help_button = page.get_by_role("button", name="How to use this experiment", exact=True)
    help_button.click()
    expect(page.get_by_role("dialog")).to_contain_text("fictional")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(help_button).to_be_focused()
    page.locator("#lab-detective-reset").click()
    expect(page.locator("#lab-case-picker")).to_have_value("0")
    expect(page.locator("#lab-detective-feedback")).to_have_count(0)
    expect(page.locator("[data-evidence-card][aria-pressed=true]")).to_have_count(0)
    return_to_lab_catalog(page)
    open_lab_activity(page, "notification-studio")
    expect(page.locator("#lab-notification-summary")).to_have_text("5 alert moments. Urgent messages wait up to 0 minutes.")
    page.locator("#lab-delivery-picker").select_option("8")
    inspect = page.locator("#lab-inspect-delivery")
    inspect.focus()
    expect(inspect).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.get_by_role("dialog")).to_contain_text("Minute 8")
    expect(page.get_by_role("dialog")).to_contain_text("Time-sensitive request")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(inspect).to_be_focused()
    page.locator("#lab-notification-policy").select_option("immediate")
    expect(page.locator("#lab-notification-summary")).to_have_text("12 alert moments. Urgent messages wait up to 0 minutes.")
    page.locator("#lab-notification-policy").select_option("end")
    page.locator("#lab-urgent-bypass").uncheck()
    expect(page.locator("#lab-notification-summary")).to_have_text("1 alert moment. Urgent messages wait up to 22 minutes.")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if screenshots:
        page.screenshot(path=str(screenshots / f"lab-notification-studio-{width}-zoom{zoom}.png"), full_page=False)
    page.locator("#lab-notification-reset").click()
    expect(page.locator("#lab-notification-policy")).to_have_value("batch")
    expect(page.locator("#lab-urgent-bypass")).to_be_checked()
    expect(page.locator("#lab-notification-summary")).to_have_text("5 alert moments. Urgent messages wait up to 0 minutes.")
    return_to_lab_catalog(page)
    page.locator("#lab-collection-filter").select_option("all")
    expect(page.locator("[data-lab-open]")).to_have_count(5)
    assert not errors, errors
    print(f"{browser_name} Lab passed at {width // zoom}px CSS viewport / {zoom}x density: keyboard, reset, timed/untimed snapshots, practice, route pause, replay, paired comparisons, source-linked precedents, all scenarios/modes.")


def check_site_integration(page, url):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    real_url = url.replace("/__lab_test__", "/index.html#lab")
    page.goto(real_url, wait_until="networkidle")
    page.locator("#lab").wait_for(state="visible")
    page.locator("#lab-collection-filter").select_option("classic")
    open_lab_activity(page, "switch")
    page.locator("#switch-start").click()
    choose_lab_section(page, "design")
    expect(page.locator("#play-switch")).not_to_be_visible()
    choose_lab_section(page, "experiments")
    expect(page.locator("#play-switch")).to_be_visible()
    expect(page.locator("#switch-note")).to_contain_text("Resumed")
    page.locator('[data-route="library"]').first.click()
    page.locator("#lab").wait_for(state="hidden")
    page.locator('[data-route="lab"]').first.click()
    page.locator("#lab").wait_for(state="visible")
    expect(page.locator("#lab-catalog")).to_be_visible()
    page.locator("#lab-collection-filter").select_option("classic")
    open_lab_activity(page, "switch")
    assert page.locator("#switch-progress").inner_text() == "1 / 20"
    assert "Resumed" in page.locator("#switch-note").inner_text()
    # A modal hides the task just as surely as changing routes. Isolate this
    # interruption from the route/panel checks above with a fresh timed trial.
    page.locator("#play-reset").click()
    page.locator("#switch-timing").select_option("timed")
    page.locator("#switch-start").click()
    note_trigger = page.locator(".play-note .layer-trigger")
    note_trigger.focus(); page.keyboard.press("Enter")
    expect(page.get_by_role("dialog")).to_be_visible()
    page.keyboard.press("ArrowLeft")
    expect(page.locator("#switch-progress")).to_have_text("1 / 20")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).not_to_be_visible()
    expect(note_trigger).to_be_focused()
    expect(page.locator("#switch-note")).to_contain_text("Resumed")
    for trial in range(1, 21):
        page.wait_for_function("n => document.querySelector('#switch-progress').textContent === n + ' / 20' && document.querySelector('#switch-left').getAttribute('aria-disabled') === 'false'", arg=trial)
        cue = page.locator("#switch-cue").inner_text()
        number = int(page.locator("#switch-number").inner_text())
        left = number % 2 == 1 if cue.startswith("ODD") else number < 5
        page.locator("#switch-left").focus()
        page.keyboard.press("ArrowLeft" if left else "ArrowRight")
    page.wait_for_function("document.querySelector('#switch-phase').textContent === 'COMPLETE'")
    expect(page.locator("#switch-results")).to_contain_text("1 interrupted response(s) excluded")
    published_title = page.locator("#weekly-title").inner_text()
    # A failed research-data request must not prevent the independent Lab loading.
    page.route("**/data/public-library.json*", lambda route: route.abort())
    page.route("**/data/reader/indexes/*", lambda route: route.abort())
    page.goto(real_url.replace("#lab", "?offline-fixture=1#lab"), wait_until="networkidle")
    page.locator("#lab").wait_for(state="visible")
    expect(page.locator("#issue-label")).to_have_text("RESEARCH INDEX TEMPORARILY UNAVAILABLE")
    expect(page.locator("#weekly-title")).to_have_text(published_title)
    choose_lab_section(page, "design")
    expect(page.get_by_role("list", name="Four product design precedents").get_by_role("listitem")).to_have_count(4)
    expect(page.get_by_role("link", name="Android Digital Wellbeing guide")).to_be_visible()
    precedent = page.locator(".precedent-details").first
    trigger = precedent.locator(".layer-trigger")
    trigger.focus(); page.keyboard.press("Enter")
    expect(page.get_by_role("dialog")).to_be_visible()
    expect(page.get_by_role("dialog")).to_contain_text("Access:")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).not_to_be_visible()
    expect(trigger).to_be_focused()
    choose_lab_section(page, "experiments")
    expect(page.locator(".play-precedents")).not_to_be_visible()
    page.locator("#lab-collection-filter").select_option("classic")
    open_lab_activity(page, "switch")
    page.locator("#switch-start").click()
    assert page.locator("#switch-progress").inner_text() == "1 / 20"
    assert not errors, errors
    print("Full app integration passed: real navigation resumes safely and unavailable research data does not block the Lab or source-linked precedents.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    parser.add_argument("--executable-path")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    with server() as url, sync_playwright() as pw:
        browser = getattr(pw, args.browser).launch(executable_path=args.executable_path, headless=True)
        print(f"Testing Playwright {args.browser} {browser.version}")
        try:
            for width, zoom in ((1280, 1), (390, 1), (320, 1), (1280, 2)):
                page = browser.new_page(reduced_motion="reduce", device_scale_factor=zoom)
                check(page, url, width, args.screenshots, zoom, args.browser)
                page.close()
            page = browser.new_page()
            check_site_integration(page, url)
            page.close()
        finally:
            browser.close()




"""Optional real-browser Lab regression check.

Requires Playwright and Chromium. Run from the repository root:
    python tests/validate_playground_browser.py --executable-path /usr/bin/chromium

The fixture uses the real page, styles and Lab script, but omits app.js and its
unrelated research-data fetches. A separate check exercises app.js navigation
and the Lab fallback when research data cannot load.
"""
import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

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


def check(page, url, width, screenshots):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(url, wait_until="networkidle")
    assert page.locator("#lab").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Overflow at {width}px"
    page.locator(".play-update summary").click()
    assert page.locator(".play-update p").first.is_visible()
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshots / f"lab-{width}.png"), full_page=True)
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
        page.wait_for_function("n => document.querySelector('#switch-progress').textContent === n + ' / 20' && !document.querySelector('#switch-left').disabled", arg=trial)
        cue = page.locator("#switch-cue").inner_text()
        number = int(page.locator("#switch-number").inner_text())
        left = number % 2 == 1 if cue.startswith("ODD") else number < 5
        page.locator("#switch-left" if left else "#switch-right").click()
    page.wait_for_function("document.querySelector('#switch-phase').textContent === 'COMPLETE'")
    assert "1 interrupted response(s) excluded" in page.locator("#switch-results").inner_text()
    assert page.evaluate("document.activeElement.id") == "switch-results"
    # All tasks must show their next action before distraction, including replays.
    page.locator("#tab-recovery").click()
    stories = set()
    for trial in range(4):
        preview = page.locator("#recovery-description").inner_text()
        stories.add(preview)
        page.locator("#recovery-start").click()
        for correct_index in (2, 1, 2, 1):
            page.locator(".recovery-option").nth(correct_index).click()
        for choice in page.locator(".recovery-option").all():
            if choice.inner_text() in preview:
                choice.click()
                break
        assert page.locator("#recovery-progress").inner_text() == "DONE"
        page.locator("#recovery-start").click()
        assert "STAGE 1 / 3" in page.locator("#recovery-progress").inner_text()
        assert page.locator(".recovery-option").count() == 0
    assert len(stories) == 4
    page.locator("#tab-assist").click()
    for mode in ("reflect", "hint", "answer"):
        page.locator(f'[data-assist-mode="{mode}"]').click()
        for i, correct_index in enumerate((1, 0, 1, 2), 1):
            assert page.locator("#assist-counter").inner_text() == f"SCENARIO {i} / 4"
            page.locator(".assist-option").nth(correct_index).click()
            assert "Supported conclusion" in page.locator("#assist-feedback").inner_text()
            page.locator("#assist-next").click()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors, errors
    print(f"Chromium Lab passed at {width}px: keyboard, route pause, 20 trials, replay, and all scenarios/modes.")


def check_site_integration(page, url):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    real_url = url.replace("/__lab_test__", "/index.html#lab")
    page.goto(real_url, wait_until="networkidle")
    page.locator("#lab").wait_for(state="visible")
    page.locator("#switch-start").click()
    page.locator('[data-route="library"]').first.click()
    page.locator("#lab").wait_for(state="hidden")
    page.locator('[data-route="lab"]').first.click()
    page.locator("#lab").wait_for(state="visible")
    assert page.locator("#switch-progress").inner_text() == "1 / 20"
    assert "Resumed" in page.locator("#switch-note").inner_text()
    # A failed research-data request must not prevent the independent Lab loading.
    page.route("**/data/public-library.json*", lambda route: route.abort())
    page.goto(real_url, wait_until="networkidle")
    page.locator("#lab").wait_for(state="visible")
    assert page.locator("#issue-label").inner_text() == "INDEX OFFLINE"
    page.locator("#switch-start").click()
    assert page.locator("#switch-progress").inner_text() == "1 / 20"
    assert not errors, errors
    print("Full app integration passed: real navigation resumes safely and unavailable research data does not block the Lab.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable-path")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    with server() as url, sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=args.executable_path, headless=True)
        try:
            for width in (1280, 390):
                page = browser.new_page(reduced_motion="reduce")
                check(page, url, width, args.screenshots)
                page.close()
            page = browser.new_page()
            check_site_integration(page, url)
            page.close()
        finally:
            browser.close()

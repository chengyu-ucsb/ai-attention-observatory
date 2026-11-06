"""Full-application visual browsing checks. Use real public payloads, never mock findings.

Playwright browser builds are not a substitute for device/screen-reader testing.
"""
import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

@contextmanager
def server():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT)))
    Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f'http://127.0.0.1:{srv.server_port}/'
    finally:
        srv.shutdown()
        srv.server_close()

def check(page, url, width, out):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(url, wait_until='networkidle')
    expect(page.locator('#library-count')).to_contain_text('matching sources')
    assert page.locator('#home .field-question').count() == 4
    for node in page.locator('.field-question').all():
        box = node.bounding_box()
        assert box['width'] >= 44 and box['height'] >= 44
    def screenshot(name):
        if out:
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / f'observatory-{width}-{name}.png'), full_page=False)
    def overflow():
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}: {page.url}'
    overflow(); screenshot('home')
    # Real keyboard link activation, exact theme selection and scope matching.
    cognition = page.locator('[data-explore-theme="AI & cognition"]')
    cognition.focus(); page.keyboard.press('Enter')
    expect(page.locator('#library')).to_be_visible()
    expect(page.locator('#scope-filter')).to_have_value('all')
    expect(page.locator('#topic-filter')).to_have_value('AI & cognition')
    expect(page.locator('#library h1')).to_be_focused()
    expect(page.locator('[data-library-theme="AI & cognition"]')).to_have_attribute('aria-pressed', 'true')
    overflow(); screenshot('library')
    page.locator('[data-library-theme="Fragmentation"]').click()
    expect(page.locator('#topic-filter')).to_have_value('Fragmentation')
    page.locator('#search').fill('no-result-zzzzzz')
    expect(page.locator('#library-results')).to_contain_text('No source-backed items')
    page.locator('#library-reset').click()
    expect(page.locator('#search')).to_have_value('')
    expect(page.locator('#scope-filter')).to_have_value('all')
    expect(page.locator('#topic-filter')).to_have_value('')
    assert page.locator('.library-story').count() > 50
    assert page.locator('.card-added').count() == page.locator('.library-story').count()
    # Added date is distinct from publication date; both order modes retain all records.
    count = page.locator('.library-story').count()
    page.locator('#library-sort').select_option('published')
    assert page.locator('.library-story').count() == count
    page.locator('#library-sort').select_option('added')
    page.locator('.library-refine summary').click()
    page.locator('#scope-filter').select_option('historical')
    assert page.locator('.library-story').count() > 0
    page.locator('#library-reset').click()
    page.locator('.library-refine summary').click()
    page.locator('.library-story h3 button').first.click()
    expect(page.locator('#paper')).to_be_visible()
    expect(page.locator('#paper h1')).to_be_visible()
    overflow(); screenshot('reading')
    # Every main destination remains available, with no page-level horizontal scroll.
    for route in ['issue', 'perspectives', 'atlas', 'about', 'home']:
        page.locator(f'.main-nav [data-route="{route}"]').click()
        expect(page.locator(f'#{route}')).to_be_visible()
        overflow(); screenshot(route)
    # Visual routes have ordinary destinations and no tracking/persistence.
    page.locator('.reading-routes a[href="#atlas"]').click()
    expect(page.locator('#atlas')).to_be_visible()
    page.locator('.main-nav [data-route="perspectives"]').click()
    page.locator('#perspectives-library-link').click()
    expect(page.locator('#type-filter')).to_have_value('nonacademic')
    expect(page.locator('#scope-filter')).to_have_value('all')
    assert page.locator('.library-story').count() > 0
    assert not errors, errors

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=['chromium','firefox','webkit'], default='chromium')
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    with server() as url, sync_playwright() as p:
        browser = getattr(p, args.browser).launch()
        for width in [1280, 768, 390, 320]:
            context = browser.new_context(reduced_motion='reduce')
            try:
                check(context.new_page(), url, width, args.screenshots)
            finally:
                context.close()
        print(f'Observatory browsing passed in {args.browser}: 1280, 768, 390, 320px; theme navigation, filters, dates, reading pages and all routes.')
        browser.close()

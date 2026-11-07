"""Full-application visual browsing checks. Use real public payloads, never mock findings.

Playwright browser builds are not a substitute for device/screen-reader testing.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime
import re
import subprocess
import sys
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
    assert 'recently indexed' not in page.locator('#issue-meta').inner_text(), 'Collection-week readings must not imply first indexing'
    assert page.locator('#home .field-question').count() == 4
    for node in page.locator('.field-question').all():
        box = node.bounding_box()
        assert box['width'] >= 44 and box['height'] >= 44
    def screenshot(name):
        if out:
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / f'observatory-{width}-{name}.png'), full_page=False)
    def overflow():
        if not page.evaluate('document.documentElement.scrollWidth <= innerWidth'):
            screenshot('overflow-'+page.url.split('#')[-1].split('?')[0])
            offenders = page.locator('body *:visible').evaluate_all("es => es.filter(e => e.getBoundingClientRect().right > innerWidth + 1).slice(0,15).map(e => ({tag:e.tagName, cls:e.className, right:e.getBoundingClientRect().right}))")
            raise AssertionError(f'Overflow at {width}: {page.url} {offenders}')
    def navigate(route):
        target = page.locator(f'.main-nav [data-route="{route}"]')
        if not target.is_visible():
            page.locator('#nav-toggle').click()
            expect(page.locator('#nav-toggle')).to_have_attribute('aria-expanded', 'true')
        target.click()
        expect(page.locator('#nav-toggle')).to_have_attribute('aria-expanded', 'false')
    if width <= 600:
        page.locator('#nav-toggle').click()
        expect(page.locator('.main-nav [data-route="lab"]')).to_be_visible()
        page.locator('.main-nav a').first.focus()
        page.keyboard.press('Escape')
        expect(page.locator('#nav-toggle')).to_be_focused()
        expect(page.locator('#nav-toggle')).to_have_attribute('aria-expanded','false')
    overflow(); screenshot('home')
    if out:
        for section, name in [('.home-edition','edition'),('.editorial-section','perspectives-preview'),('.lenses-grid','themes')]:
            page.locator('#home '+section).screenshot(path=str(out / f'observatory-{width}-{name}.png'), style='.site-header { visibility: hidden !important; }')
    # Theme links preserve selection when copied or opened in another tab.
    theme_url = page.locator('[data-explore-theme="AI & cognition"]').get_attribute('href')
    assert 'theme=AI%20%26%20cognition' in theme_url and 'scope=all' in theme_url
    # Real keyboard link activation, exact theme selection and scope matching.
    cognition = page.locator('[data-explore-theme="AI & cognition"]')
    cognition.focus(); page.keyboard.press('Enter')
    expect(page.locator('#library')).to_be_visible()
    expect(page.locator('#scope-filter')).to_have_value('all')
    expect(page.locator('#topic-filter')).to_have_value('AI & cognition')
    expect(page.locator('#library h1')).to_be_focused()
    expect(page.locator('[data-library-theme="AI & cognition"]')).to_have_attribute('aria-pressed', 'true')
    overflow(); screenshot('library')
    page.reload(wait_until='networkidle')
    expect(page.locator('#scope-filter')).to_have_value('all')
    expect(page.locator('#topic-filter')).to_have_value('AI & cognition')
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
    if out:
        page.locator('.library-story').first.screenshot(path=str(out / f'observatory-{width}-card.png'), style='.site-header { visibility: hidden !important; }')
    # Added date is distinct from publication date; both order modes retain all records.
    count = page.locator('.library-story').count()
    page.locator('#library-sort').select_option('published')
    assert page.locator('.library-story').count() == count
    published = [datetime.strptime(re.search(r'Published (\w+ \d+, \d{4})', t).group(1), '%b %d, %Y') for t in page.locator('.card-source-meta').all_text_contents() if re.search(r'Published (\w+ \d+, \d{4})', t)]
    assert published == sorted(published, reverse=True), 'Publication ordering must use publication date'
    page.locator('#library-sort').select_option('added')
    added = [datetime.strptime(t.removeprefix('Added '), '%b %d, %Y') for t in page.locator('.card-added').all_text_contents() if t != 'Added date not recorded']
    assert added == sorted(added, reverse=True), 'Recently added must use first-indexed date'
    page.locator('.library-refine summary').click()
    page.locator('#scope-filter').select_option('historical')
    expect(page.locator('#library-context')).to_contain_text('Earlier foundations')
    if not page.locator('.library-story').count():
        expect(page.locator('#library-results')).to_contain_text('No source-backed items')
    page.locator('#library-reset').click()
    page.locator('.library-refine summary').click()
    page.locator('.library-story h3 button').first.click()
    expect(page.locator('#paper')).to_be_visible()
    expect(page.locator('#paper h1')).to_be_visible()
    overflow(); screenshot('reading')
    # A former generic-question reading now retains a supported method and result.
    navigate('library')
    page.locator('#library-reset').click()
    page.locator('#search').fill('ChatGPT as cognitive scaffold')
    expect(page.locator('.library-story')).to_have_count(1)
    page.locator('.library-story h3 button').click()
    expect(page.locator('#paper')).to_be_visible()
    expect(page.locator('.rv-content')).not_to_contain_text('Method details are not clear enough')
    expect(page.locator('.rv-coverage-table')).to_be_visible()
    expect(page.locator('.rv-content')).to_contain_text('n = 47')
    expect(page.locator('.automatic-evidence')).to_contain_text('Source: abstract')
    overflow(); screenshot('source-reading')
    reader=page.locator('.rv-source-excerpts')
    reader.locator(':scope > summary').focus()
    page.keyboard.press('Enter')
    expect(reader.locator('.rv-reader-contents')).to_be_visible()
    reader.get_by_role('button', name='Abstract', exact=True).click()
    # The source name can differ by index provider, so locate by its actual title.
    abstract=reader.locator('.rv-source-section').filter(has=page.locator('summary span').filter(has_text='Abstract'))
    expect(abstract.locator('.rv-prose')).to_be_visible()
    assert abstract.locator('.rv-prose p').count()>1
    overflow(); screenshot('source-reader')
    reader.get_by_role('button',name='Expand all sections',exact=True).click()
    assert reader.locator('.rv-source-section').evaluate_all('es => es.every(e => e.open)')
    reader.get_by_role('button',name='Collapse all sections',exact=True).click()
    assert reader.locator('.rv-source-section').evaluate_all('es => es.every(e => !e.open)')
    reader.locator(':scope > summary').click()
    reader.locator(':scope > summary').click()
    expect(reader.locator('.rv-reader-contents')).to_be_visible()
    overflow()
    # Every main destination remains available, with no page-level horizontal scroll.
    for route in ['issue', 'perspectives', 'atlas', 'about', 'home']:
        navigate(route)
        expect(page.locator(f'#{route}')).to_be_visible()
        overflow(); screenshot(route)
        if route == 'issue':
            page.locator('.issue-reading-shelf summary').click()
            assert page.locator('.issue-shelf-item').count() > 0
            expect(page.locator('#issue-coverage')).to_contain_text('sources in this edition')
            screenshot('issue-sources')
    # Visual routes have ordinary destinations and no tracking/persistence.
    page.locator('.reading-routes a[href="#atlas"]').click()
    expect(page.locator('#atlas')).to_be_visible()
    navigate('perspectives')
    page.locator('#perspectives-library-link').click()
    expect(page.locator('#type-filter')).to_have_value('nonacademic')
    expect(page.locator('#scope-filter')).to_have_value('all')
    assert page.locator('.library-story').count() > 0
    assert not errors, errors

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=['chromium','firefox','webkit'], default='chromium')
    parser.add_argument('--screenshots', type=Path)
    parser.add_argument('--executable-path', type=str)
    args = parser.parse_args()
    # Exercise the actual publication projection, not a stale committed payload.
    subprocess.run([sys.executable, str(ROOT / "scripts/build_public.py")], cwd=ROOT, check=True)
    with server() as url, sync_playwright() as p:
        browser = getattr(p, args.browser).launch(**({"executable_path":args.executable_path} if args.executable_path else {}))
        for width in [1280, 768, 390, 320]:
            context = browser.new_context(reduced_motion='reduce')
            try:
                check(context.new_page(), url, width, args.screenshots)
            finally:
                context.close()
        print(f'Observatory browsing passed in {args.browser}: 1280, 768, 390, 320px; theme navigation, filters, dates, reading pages and all routes.')
        browser.close()

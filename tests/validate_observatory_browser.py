"""Full-application browsing checks plus explicitly synthetic typed-receipt regressions.

Playwright browser builds are not a substitute for device/screen-reader testing.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime
import re
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

def typed_reading_payloads():
    """Build only synthetic receipts through the production publication boundary."""
    import sys
    from copy import deepcopy
    sys.path.insert(0, str(ROOT / 'scripts'))
    sys.path.insert(0, str(ROOT / 'tests'))
    from test_checked_reading_types import commentary
    from test_original_readings import record, accepted, approve, article_screen
    from original_readings import public_record
    from condense_readings import annotate
    from build_public import readable
    from build_issue import checked_source_metadata

    row, receipt = commentary()
    receipt['commentary']['temporal'].update(reported_modified='2026-11-05', checked_on='2026-11-07')
    receipt['review']['checked_on'] = '2026-11-07'
    approve(receipt)
    row['original_reading'] = receipt
    checked = public_record(annotate(row))
    assert readable(checked)
    # These are intentionally stale indexed visuals, not newly approved evidence.
    checked['visual'] = {'kind': 'evidence_snapshot', 'basis': 'full_text',
                         'blocks': [{'label': 'Old graphic', 'text': 'Stale visual sentinel'}]}
    rejected = []
    for mode in ('revoked', 'stale'):
        candidate = deepcopy(row)
        note = candidate['original_reading']
        if mode == 'revoked':
            note['publication']['decision'] = 'revoked'
        else:
            note['summary']['thesis'] = 'Changed synthetic thesis without a new receipt.'
        projected = public_record(annotate(candidate))
        assert not projected['reading'].get('original_summary')
        assert not readable(projected), mode
        rejected.append(projected)

    preprint = record()
    preprint.update(venue='arXiv', title='Synthetic screened preprint about generative AI and attention',
                    url='https://example.org/synthetic-preprint', doi='10.9999/synthetic-preprint')
    note = accepted()
    note.update(title=preprint['title'], record_url=preprint['url'], doi=preprint['doi'])
    note['source'].update(version='preprint_v1', source_doi=preprint['doi'],
                          url='https://example.org/synthetic-preprint-v1.pdf')
    article_screen(note, preprint)
    approve(note)
    preprint['original_reading'] = note
    preprint = public_record(annotate(preprint))
    assert readable(preprint) and preprint['reading'].get('original_summary')
    assert 'not verified peer-reviewed evidence' in preprint['reading']['notice']
    library = [x for x in [checked, preprint, *rejected] if readable(x)]
    assert len(library) == 2
    for item in library:
        item['source_group'] = 'AI-specific'
    shelf = [{'id': x.get('doi') or x['url'], 'title': x['title'], 'url': x['url'],
              'venue': x['venue'], **checked_source_metadata(x)} for x in library]
    return library, {'status': 'awaiting_publication', 'sources': shelf}, rejected


def check_typed_readings(page, url, width, out):
    """Real DOM/navigation coverage, isolated from the live original register."""
    import json
    library, issue, rejected = typed_reading_payloads()
    commentary, preprint = library
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_viewport_size({'width': width, 'height': 900})
    payloads = {'public-library.json': library, 'public-weekly.json': {'run': {}, 'items': []},
                'runs.json': [], 'fulltext-backfill-state.json': {},
                'public-featured-issue.json': issue, 'public-pending-sources.json': []}
    # Fulfill only app JSON requests; HTML, CSS, JS and local artwork are real.
    def fulfill(route):
        name = route.request.url.split('/')[-1].split('?')[0]
        if name in payloads:
            route.fulfill(status=200, content_type='application/json', body=json.dumps(payloads[name]))
        else:
            route.continue_()
    page.route('**/data/*.json*', fulfill)
    page.goto(url + '#library', wait_until='networkidle')
    expect(page.locator('.library-story')).to_have_count(2)
    card = page.locator('.library-story').filter(has_text=commentary['reading']['digest']['idea'])
    temporal = commentary['reading']['temporal_notice']
    for value in (temporal, 'policy analysis', 'Synthetic policy author', 'not human review'):
        expect(card).to_contain_text(value)
    expect(card.get_by_text(temporal, exact=False).last).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Typed card overflow at {width}px'
    card.locator('h3 button').click()
    expect(page.locator('#paper')).to_be_visible()
    paper = page.locator('#paper-content')
    expect(paper.locator('.rv-head')).to_contain_text(temporal)
    expect(paper.locator('.rv-head .rv-reading-notice')).to_be_visible()
    for key in ('thesis', 'reasoning', 'examples', 'tension', 'qualification'):
        expect(paper).to_contain_text(commentary['reading']['digest']['longform'][key])
    for forbidden in ('How it was studied', 'Study approach', 'Reported finding', 'REPORTED FINDING', 'Stale visual sentinel'):
        expect(paper).not_to_contain_text(forbidden)
    expect(paper.locator('.automatic-evidence, .rv-original-figure, .rv-context-grid')).to_have_count(0)
    expect(paper.locator('.rv-primary-link')).to_have_attribute('href', commentary['reading']['source_url'])
    evidence = paper.locator('.rv-evidence')
    expect(evidence).not_to_have_attribute('open', '')
    evidence.locator('summary').click()
    expect(evidence.locator('.rv-source-locator')).to_have_count(5)
    expect(evidence.locator('.rv-source-locator').first).to_be_visible()
    expect(evidence).to_contain_text('extracted block 1')
    evidence.locator('summary').click()
    expect(evidence.locator('.rv-source-locator').first).not_to_be_visible()
    evidence.locator('summary').click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Typed reading overflow at {width}px'
    if out:
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / f'observatory-{width}-synthetic-commentary.png'), full_page=True)
    paper.locator('.rv-back').click()
    expect(page.locator('#library')).to_be_visible()
    page.locator('.library-story').filter(has_text=preprint['title']).locator('h3 button').click()
    expect(paper).to_contain_text('Limited reading.')
    expect(paper).to_contain_text('not verified peer-reviewed evidence')
    expect(paper).to_contain_text('How it was studied')
    expect(paper.locator('.rv-primary-link')).to_have_attribute('href', preprint['reading']['source_url'])
    paper.locator('.rv-evidence summary').click()
    expect(paper.locator('.rv-evidence')).to_contain_text('page 2')
    expect(paper.locator('.rv-evidence')).not_to_contain_text('extracted block')
    page.goto(url + '#issue', wait_until='networkidle')
    issue_view = page.locator('#issue')
    expect(issue_view).to_be_visible()
    issue_view.locator('.issue-reading-shelf > details > summary').click()
    shelf = issue_view.locator('.issue-shelf-item').first
    expect(shelf).to_contain_text(temporal)
    expect(shelf).to_contain_text('Synthetic policy author')
    shelf.locator('.rv-evidence summary').click()
    expect(shelf.locator('.rv-source-locator').first).to_be_visible()
    expect(shelf).to_contain_text('extracted block 1')
    expect(issue_view.locator('.issue-shelf-item').nth(1)).to_contain_text('not verified peer-reviewed evidence')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Typed shelf overflow at {width}px'
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
                check_typed_readings(context.new_page(), url, width, args.screenshots)
            finally:
                context.close()
        print(f'Observatory browsing passed in {args.browser}: 1280, 768, 390, 320px; theme navigation, filters, dates, reading pages and all routes.')
        browser.close()

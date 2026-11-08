"""Full-application browsing checks plus explicitly synthetic typed-receipt regressions.

Playwright browser builds are not a substitute for device/screen-reader testing.
"""
import argparse
import base64
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
        name = re.sub(r'[^a-zA-Z0-9_-]', '-', name)
        if out:
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / f'observatory-{width}-{name}.png'), full_page=False)
        # Compact, public-page review frames remain inspectable alongside the PNG artifacts.
        if args.browser == 'chromium' and ((width in (1280, 390) and name in ('home', 'issue', 'reading-head', 'library')) or name.startswith('overflow')):
            frame = page.screenshot(type='jpeg', quality=55, full_page=False)
            print(f'DESIGN_REVIEW_IMAGE:{width}:{name}:' + base64.b64encode(frame).decode('ascii'), flush=True)
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
    # Publication hierarchy stays issue-led, with four compact subject links below it.
    assert page.locator('.home-edition').evaluate("(e) => e.compareDocumentPosition(document.querySelector('.field-guide')) & Node.DOCUMENT_POSITION_FOLLOWING")
    expect(page.locator('.publication-masthead h1')).to_contain_text('AI')
    expect(page.locator('.observation-art title')).to_have_text('The attention lens')
    assert page.locator('body').evaluate("(e) => getComputedStyle(e).getPropertyValue('--red').trim().toLowerCase()") == '#e00122'
    assert page.locator('.weekly-cover-art').evaluate('(e) => getComputedStyle(e).position') == 'static'
    overflow(); screenshot('home')
    if out:
        for section, name in [('.home-edition','edition'),('.editorial-section','perspectives-preview'),('.field-guide','themes')]:
            page.locator('#home '+section).screenshot(path=str(out / f'observatory-{width}-{name}.png'), style='.site-header { visibility: hidden !important; }')
            if args.browser == 'chromium' and ((width == 1280 and name == 'perspectives-preview') or (width == 390 and name == 'themes')):
                frame = page.locator('#home '+section).screenshot(type='jpeg', quality=55, style='.site-header { visibility: hidden !important; }')
                print(f'DESIGN_REVIEW_IMAGE:{width}:{name}:' + base64.b64encode(frame).decode('ascii'), flush=True)
    # Fixed-size artwork must never cover adjacent editorial headlines.
    for card in page.locator('#home .editorial-card').all():
        artwork = card.locator('.story-visual-editorial')
        if artwork.count():
            art_box, title_box = artwork.bounding_box(), card.locator('h3').bounding_box()
            assert art_box['x'] + art_box['width'] <= title_box['x'] - 8, 'Editorial thumbnail overlaps its headline'
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
        if args.browser == 'chromium' and width in (1280, 390):
            frame = page.locator('.library-story').first.screenshot(type='jpeg', quality=55, style='.site-header { visibility: hidden !important; }')
            print(f'DESIGN_REVIEW_IMAGE:{width}:library-card:' + base64.b64encode(frame).decode('ascii'), flush=True)
    # Added date is distinct from publication date; both order modes retain all records.
    count = page.locator('.library-story').count()
    page.locator('#library-sort').select_option('published')
    assert page.locator('.library-story').count() == count
    published = [datetime.strptime(re.search(r'Published (\w+ \d+, \d{4})', t).group(1), '%b %d, %Y') for t in page.locator('.card-source-meta').all_text_contents() if re.search(r'Published (\w+ \d+, \d{4})', t)]
    assert published == sorted(published, reverse=True), 'Publication ordering must use publication date'
    page.locator('#library-sort').select_option('added')
    added = [datetime.strptime(t.removeprefix('Added '), '%b %d, %Y') for t in page.locator('.card-added').all_text_contents() if t != 'Added date not recorded']
    assert added == sorted(added, reverse=True), 'Recently added must use first-indexed date'
    page.locator('.library-refine > summary').click()
    page.locator('#scope-filter').select_option('historical')
    expect(page.locator('#library-context')).to_contain_text('Earlier foundations')
    if not page.locator('.library-story').count():
        expect(page.locator('#library-results')).to_contain_text('No source-backed items')
    page.locator('#library-reset').click()
    page.locator('.library-refine > summary').click()
    page.locator('.library-story h3 button').first.click()
    expect(page.locator('#paper')).to_be_visible()
    expect(page.locator('#paper h1')).to_be_visible()
    assert page.locator('.rv-head').evaluate('(e) => getComputedStyle(e).display') == 'block'
    overflow(); screenshot('reading-head')
    expect(page.locator('.rv-head .story-visual-reading')).to_have_count(1)
    expect(page.locator('.rv-head .story-image')).to_have_attribute('alt', re.compile(r'.{10,}'))
    assert page.locator('.rv-head .story-image').evaluate('(e) => e.complete && e.naturalWidth > 0'), 'Editorial art failed to load'
    assert page.locator('.rv-head .story-visual-reading').evaluate('(e) => e.lastElementChild.getBoundingClientRect().bottom <= e.getBoundingClientRect().bottom + 1'), 'Illustration caption was cropped'
    expect(page.locator('.rv-head .story-visual-caption')).to_have_text('Editorial illustration')
    provenance = page.locator('.rv-provenance')
    expect(provenance).not_to_have_attribute('open', '')
    provenance.locator(':scope > summary').focus()
    page.keyboard.press('Enter')
    expect(provenance.locator('.rv-status')).to_be_visible()
    provenance.locator(':scope > summary').click()
    expect(provenance.locator('.rv-status')).not_to_be_visible()
    for card in page.locator('.rv-context:visible').all():
        assert card.evaluate("el => parseFloat(getComputedStyle(el).paddingLeft) >= 16 && parseFloat(getComputedStyle(el).paddingRight) >= 16"), 'Reading context card lost its text inset'
    overflow(); screenshot('reading')
    # A former generic-question reading now retains a supported method and result.
    navigate('library')
    page.locator('#library-reset').click()
    page.locator('#search').fill('ChatGPT as cognitive scaffold')
    expect(page.locator('.library-story')).to_have_count(1)
    page.locator('.library-story h3 button').click()
    expect(page.locator('#paper')).to_be_visible()
    expect(page.locator('.rv-content')).not_to_contain_text('Method details are not clear enough')
    coverage = page.locator('details.rv-coverage')
    expect(coverage).not_to_have_attribute('open', '')
    expect(coverage.locator('.rv-coverage-table')).not_to_be_visible()
    coverage.locator(':scope > summary').focus()
    page.keyboard.press('Enter')
    expect(coverage.locator('.rv-coverage-table')).to_be_visible()
    coverage.locator(':scope > summary').click()
    expect(coverage.locator('.rv-coverage-table')).not_to_be_visible()
    coverage.locator(':scope > summary').click()
    expect(coverage.locator('.rv-coverage-table')).to_be_visible()
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
            source_shelf = page.locator('.issue-reading-shelf > details')
            expect(source_shelf).to_have_count(1)
            expect(source_shelf).not_to_have_attribute('open', '')
            source_shelf.locator(':scope > summary').click()
            expect(source_shelf).to_have_attribute('open', '')
            assert page.locator('.issue-shelf-item').count() > 0
            expect(source_shelf.locator('.issue-shelf-item').first).to_be_visible()
            shelf_count = page.locator('.issue-shelf-item').count()
            expect(page.locator('#issue-coverage')).to_contain_text(re.compile(r'^' + str(shelf_count) + r' sources (?:originally published|in this edition)'))
            screenshot('issue-sources')
    # Visual routes have ordinary destinations and no tracking/persistence.
    navigate('atlas')
    expect(page.locator('#atlas')).to_be_visible()
    navigate('perspectives')
    page.locator('#perspectives-library-link').click()
    expect(page.locator('#type-filter')).to_have_value('nonacademic')
    expect(page.locator('#scope-filter')).to_have_value('all')
    assert page.locator('.library-story').count() > 0
    assert not errors, errors


def check_standalone_brief(page, url, width, out):
    """Exercise generated weekly prose and the RSS landing page at every width."""
    import json
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_viewport_size({'width': width, 'height': 900})
    published = [json.loads(path.read_text()) for path in
                 sorted((ROOT / 'data/approved-issues').glob('????-??-??.json'), reverse=True)]
    latest = next(issue for issue in published if issue.get('status') == 'published')
    base = 'https://chengyu-ucsb.github.io/ai-attention-observatory/'
    for name in ('newsletter', 'subscribe'):
        page.goto(url + name + '.html', wait_until='networkidle')
        expect(page.locator('h1')).to_have_count(1)
        expect(page.locator('h1')).to_be_visible()
        if name == 'newsletter':
            expect(page.locator('h1')).to_have_text(latest['headline'])
            expect(page.locator('header a[href="' + base + '"]')).to_be_visible()
            expect(page.locator('header a[href="' + base + 'issues/"]')).to_be_visible()
            expect(page.locator('a[href="' + base + 'issue-feed.xml"]')).to_have_count(1)
        else:
            expect(page.locator('h1')).to_contain_text('One good idea a week.')
            expect(page.locator('header a[href="./"]')).to_be_visible()
            expect(page.locator('header a[href="./#issue"]')).to_be_visible()
            expect(page.locator('#feed-url')).to_have_value(base + 'issue-feed.xml')
            expect(page.locator('.actions a[href="newsletter.html"]')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'{name} overflow at {width}px'
        if out:
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / f'observatory-{width}-{name}.png'), full_page=True)
        if args.browser == 'chromium' and width in (1280, 390):
            frame = page.screenshot(type='jpeg', quality=55, full_page=False)
            print(f'DESIGN_REVIEW_IMAGE:{width}:{name}:' + base64.b64encode(frame).decode('ascii'), flush=True)
        if name == 'newsletter':
            opening = page.locator('main details').first
            expect(opening).not_to_have_attribute('open', '')
            expect(opening.locator(':scope > p').first).not_to_be_visible()
            opening.locator(':scope > summary').focus()
            page.keyboard.press('Enter')
            expect(opening).to_have_attribute('open', '')
            expect(opening.locator(':scope > p').first).to_be_visible()
            expect(opening.locator(':scope > p').first).not_to_be_empty()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Expanded newsletter overflow at {width}px'
            if out:
                page.screenshot(path=str(out / f'observatory-{width}-newsletter-expanded.png'), full_page=True)
            opening.locator(':scope > summary').focus()
            page.keyboard.press('Enter')
            expect(opening.locator(':scope > p').first).not_to_be_visible()
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
    card_details = card.locator('.card-reading-details')
    expect(card_details).not_to_have_attribute('open', '')
    card_details.locator(':scope > summary').click()
    expect(card.get_by_text(temporal, exact=False).last).to_be_visible()
    card_details.locator(':scope > summary').click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Typed card overflow at {width}px'
    card.locator('h3 button').click()
    expect(page.locator('#paper')).to_be_visible()
    paper = page.locator('#paper-content')
    expect(paper.locator('.rv-head')).to_contain_text(temporal)
    dates = paper.locator('.rv-source-dates')
    expect(dates).not_to_have_attribute('open', '')
    dates.locator(':scope > summary').click()
    expect(dates.locator('.rv-reading-notice')).to_be_visible()
    dates.locator(':scope > summary').click()
    for key in ('thesis', 'reasoning', 'examples', 'tension', 'qualification'):
        expect(paper).to_contain_text(commentary['reading']['digest']['longform'][key])
    for forbidden in ('How it was studied', 'Study approach', 'Reported finding', 'REPORTED FINDING', 'Stale visual sentinel'):
        expect(paper).not_to_contain_text(forbidden)
    expect(paper.locator('.automatic-evidence, .rv-original-figure, .rv-context-grid')).to_have_count(0)
    expect(paper.locator('.rv-primary-link')).to_have_attribute('href', commentary['reading']['source_url'])
    evidence = paper.locator('.rv-evidence')
    expect(evidence).not_to_have_attribute('open', '')
    evidence.locator(':scope > summary').click()
    expect(evidence.locator('.rv-source-locator')).to_have_count(5)
    expect(evidence.locator('.rv-source-locator').first).to_be_visible()
    expect(evidence).to_contain_text('extracted block 1')
    evidence.locator(':scope > summary').click()
    expect(evidence.locator('.rv-source-locator').first).not_to_be_visible()
    evidence.locator(':scope > summary').click()
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
    paper.locator('.rv-evidence > summary').click()
    expect(paper.locator('.rv-evidence')).to_contain_text('page 2')
    expect(paper.locator('.rv-evidence')).not_to_contain_text('extracted block')
    page.goto(url + '#issue', wait_until='networkidle')
    issue_view = page.locator('#issue')
    expect(issue_view).to_be_visible()
    source_shelf = issue_view.locator('.issue-reading-shelf > details')
    expect(source_shelf).to_have_count(1)
    source_shelf.locator(':scope > summary').click()
    expect(source_shelf).to_have_attribute('open', '')
    expect(source_shelf.locator('.issue-shelf-item').first).to_be_visible()
    shelf = issue_view.locator('.issue-shelf-item').first
    expect(shelf).to_contain_text(temporal)
    expect(shelf).to_contain_text('Synthetic policy author')
    shelf.locator('.rv-evidence > summary').click()
    expect(shelf.locator('.rv-source-locator').first).to_be_visible()
    expect(shelf).to_contain_text('extracted block 1')
    expect(issue_view.locator('.issue-shelf-item').nth(1)).to_contain_text('not verified peer-reviewed evidence')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Typed shelf overflow at {width}px'
    assert not errors, errors


def registered_reading_payloads():
    """Run the real publication builder without changing checked-in data/receipts."""
    import json
    import shutil
    import sys
    import tempfile
    from unittest.mock import patch
    sys.path.insert(0, str(ROOT / 'scripts'))
    import build_public
    import original_readings
    from collection_window import previous_week, weekly_eligible
    with tempfile.TemporaryDirectory(prefix='registered-reading-browser-') as tmp:
        data = Path(tmp) / 'data'
        shutil.copytree(ROOT / 'data', data)
        # A registered-reading fixture retains curated-art references. Copy the
        # matching local assets as well, then let its isolated build make SVGs.
        shutil.copytree(ROOT / 'assets' / 'editorial-covers', Path(tmp) / 'assets' / 'editorial-covers')
        with patch.object(build_public, 'DATA', data), patch.object(original_readings, 'MANIFEST', data / 'original-readings.json'):
            library, weekly = build_public.build()
        pending = json.loads((data / 'public-pending-sources.json').read_text())
    originals = [row for row in library if row.get('reading', {}).get('original_summary')]
    if weekly.get('run', {}).get('publication_window'):
        start, end = previous_week(weekly['run']['date'])
        weekly_ids = {build_public.record_id(row) for row in weekly['items']}
        for row in originals:
            if not weekly_eligible(row, start, end):
                assert build_public.record_id(row) not in weekly_ids, 'An out-of-window original leaked into weekly publication'
    print(f'Registered-reading browser input: {len(originals)} admitted originals' +
          ('; actual original-reading DOM coverage skipped because none were admitted.' if not originals else '.'))
    return library, weekly, pending, originals


def check_registered_readings(page, url, width, out, payloads):
    """Validate every actually admitted original, never create an approval."""
    import hashlib
    import json
    from urllib.parse import quote
    library, weekly, pending, originals = payloads
    if not originals:
        return
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_viewport_size({'width': width, 'height': 900})
    data = {'public-library.json': library, 'public-weekly.json': weekly,
            'public-pending-sources.json': pending}
    def fulfill(route):
        name = route.request.url.split('/')[-1].split('?')[0]
        if name in data:
            route.fulfill(status=200, content_type='application/json', body=json.dumps(data[name]))
        else:
            route.continue_()
    page.route('**/data/*.json*', fulfill)
    for row in originals:
        reading = row['reading']
        commentary = reading.get('research_type') == 'attributed_commentary'
        identifier = row.get('doi') or row['url']
        page.goto(url + '#paper/' + quote(identifier, safe=''), wait_until='networkidle')
        paper = page.locator('#paper-content')
        expect(page.locator('#paper')).to_be_visible()
        expect(paper.locator('.rv-primary-link')).to_have_attribute('href', reading['source_url'])
        expect(paper).to_contain_text(reading['source_version'])
        expect(paper).to_contain_text(reading['review_scope'])
        expect(paper).to_contain_text(reading['notice'])
        expect(paper).to_contain_text('not human review')
        if reading.get('quality_note'):
            expect(paper).to_contain_text(reading['quality_note'])
        if reading.get('temporal_notice'):
            expect(paper.locator('.rv-head')).to_contain_text(reading['temporal_notice'])
            expect(paper.locator('.rv-head')).to_contain_text(reading['temporal_notice'])
        # Compare against the approved source fields, not legacy extracted prose.
        for field, value in row['original_reading']['summary'].items():
            if value:
                # textContent includes the optional overview/interpretation drawers.
                # Normalize only whitespace: every approved word must survive.
                actual = paper.evaluate("el => { const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); const parts = []; while (walk.nextNode()) parts.push(walk.currentNode.textContent); return parts.join(' ').replace(/\\s+/g, ' ').trim(); }")
                assert re.sub(r'\s+', ' ', value).strip() in actual, field
        if commentary:
            for label in ('How it was studied', 'Study approach', 'REPORTED FINDING', 'Methods as indexed', 'Results as indexed'):
                expect(paper).not_to_contain_text(label)
            expect(paper.locator('.rv-context-grid')).to_have_count(0)
        if 'Preprint, not verified peer-reviewed evidence' in reading['notice']:
            expect(paper).to_contain_text('Limited reading.')
            expect(paper).to_contain_text('Article screening is not peer review')
        expect(paper.locator('.automatic-evidence, .rv-artwork, .rv-original-figure')).to_have_count(0)
        evidence = paper.locator('.rv-evidence')
        expect(evidence).to_have_count(1)
        evidence.locator(':scope > summary').click()
        locators = [locator for values in reading['evidence'].values() for locator in values]
        expect(evidence.locator('.rv-source-locator')).to_have_count(len(locators))
        for locator in locators:
            expect(evidence).to_contain_text('Section: ' + locator['section'])
            if locator.get('page'):
                expect(evidence).to_contain_text('page ' + str(locator['page']))
            if locator.get('paragraph'):
                label = 'extracted block ' if commentary and reading['source_format'] == 'html' else 'paragraph '
                expect(evidence).to_contain_text(label + str(locator['paragraph']))
        expect(evidence.locator('.rv-source-locator').first).to_be_visible()
        evidence.locator(':scope > summary').click()
        expect(evidence.locator('.rv-source-locator').first).not_to_be_visible()
        evidence.locator(':scope > summary').click()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Registered reading overflow: {identifier} at {width}px'
        if out:
            out.mkdir(parents=True, exist_ok=True)
            key = hashlib.sha256(identifier.encode()).hexdigest()[:12]
            page.screenshot(path=str(out / f'observatory-{width}-registered-{key}.png'), full_page=True)
    assert not errors, errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=['chromium','firefox','webkit'], default='chromium')
    parser.add_argument('--screenshots', type=Path)
    parser.add_argument('--executable-path', type=str)
    args = parser.parse_args()
    # Exercise the actual publication projection, not a stale committed payload.
    subprocess.run([sys.executable, str(ROOT / "scripts/build_public.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/build_newsletter.py")], cwd=ROOT, check=True)
    registered = registered_reading_payloads()
    with server() as url, sync_playwright() as p:
        browser = getattr(p, args.browser).launch(**({"executable_path":args.executable_path} if args.executable_path else {}))
        for width in [1280, 768, 390, 320]:
            context = browser.new_context(reduced_motion='reduce')
            try:
                check(context.new_page(), url, width, args.screenshots)
                check_standalone_brief(context.new_page(), url, width, args.screenshots)
                check_typed_readings(context.new_page(), url, width, args.screenshots)
                check_registered_readings(context.new_page(), url, width, args.screenshots, registered)
            finally:
                context.close()
        print(f'Observatory browsing passed in {args.browser}: 1280, 768, 390, 320px; theme navigation, filters, dates, reading pages, all routes, generated newsletter and RSS subscription pages.')
        browser.close()

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


def check_typography(page, samples):
    """Test real downloaded font faces, rather than accepting fallback family names."""
    import json
    manifest = json.loads((ROOT / 'assets/fonts/manifest.json').read_text())
    checks = [{'family': item['family'], 'style': item['style'],
               'weight': item['weight'].split()[0]} for item in manifest]
    loaded = page.evaluate("""async (checks) => {
      const results = await Promise.all(checks.map(async item => {
        const query = `${item.style} ${item.weight} 16px "${item.family}"`;
        const faces = await document.fonts.load(query, 'Attention evidence 0123');
        return {query, loaded: faces.length > 0 && faces.every(face => face.status === 'loaded')};
      }));
      await document.fonts.ready;
      return results;
    }""", checks)
    assert all(item['loaded'] for item in loaded), loaded
    remote_fonts = page.evaluate(r"""() => performance.getEntriesByType('resource')
      .filter(item => /fonts\.(googleapis|gstatic)\.com/.test(item.name)).map(item => item.name)""")
    assert not remote_fonts, f'Typography must be self-hosted: {remote_fonts}'
    assert page.locator('body').evaluate('(e) => parseFloat(getComputedStyle(e).fontSize)') >= 16
    for selector, family, minimum in samples:
        node = page.locator(selector).first
        expect(node).to_be_visible()
        rendered = node.evaluate("""e => ({family: getComputedStyle(e).fontFamily,
          size: parseFloat(getComputedStyle(e).fontSize)})""")
        assert family in rendered['family'], (selector, rendered)
        assert rendered['size'] >= minimum, (selector, rendered)

def open_reading_card(page, scope):
    """Exercise the shared live-DOM card with real keyboard focus."""
    trigger = scope.locator(':scope > .layer-trigger')
    expect(trigger).to_have_attribute('aria-haspopup', 'dialog')
    trigger.focus()
    page.keyboard.press('Enter')
    dialog = page.get_by_role('dialog')
    expect(dialog).to_be_visible()
    assert dialog.evaluate('(el) => el.contains(document.activeElement)')
    return dialog, trigger


def close_reading_card(page, dialog, trigger):
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    expect(trigger).to_be_focused()


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
    check_typography(page, [
        ('#weekly-title', 'Gentium Book Plus', 32),
        ('.weekly-cover-copy>p:not(.eyebrow):not(.weekly-scope)', 'Open Sans', 16),
        ('.weekly-scope', 'Open Sans', 13),
        ('.identity-text small', 'Jost', 13),
    ])
    expect(page.locator('#home-section')).to_have_value('overview')
    expect(page.locator('#home .field-guide')).to_be_visible()
    expect(page.locator('#beyond-journals')).not_to_be_visible()
    expect(page.locator('#home .glance-section')).not_to_be_visible()
    overflow(); screenshot('home')
    if out:
        for section, name in [('.home-edition','edition'),('.editorial-section','perspectives-preview'),('.field-guide','themes')]:
            page.locator('#home-section').select_option('ideas' if section == '.editorial-section' else 'overview')
            page.locator('#home '+section).screenshot(path=str(out / f'observatory-{width}-{name}.png'), style='.site-header { visibility: hidden !important; }')
            if args.browser == 'chromium' and ((width == 1280 and name == 'perspectives-preview') or (width == 390 and name == 'themes')):
                frame = page.locator('#home '+section).screenshot(type='jpeg', quality=55, style='.site-header { visibility: hidden !important; }')
                print(f'DESIGN_REVIEW_IMAGE:{width}:{name}:' + base64.b64encode(frame).decode('ascii'), flush=True)
    page.locator('#home-section').select_option('ideas')
    expect(page.locator('#beyond-journals')).to_be_visible()
    expect(page.locator('#home .field-guide')).not_to_be_visible()
    # Fixed-size artwork must never cover adjacent editorial headlines.
    for card in page.locator('#home .editorial-card').all():
        artwork = card.locator('.story-visual-editorial')
        if artwork.count():
            art_box, title_box = artwork.bounding_box(), card.locator('h3').bounding_box()
            assert art_box['x'] + art_box['width'] <= title_box['x'] - 8, 'Editorial thumbnail overlaps its headline'
    page.locator('#home-section').select_option('overview')
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
    assert 0 < page.locator('.library-story').count() <= 12
    assert int(re.search(r'(\d+) in the complete archive', page.locator('#library-count').inner_text()).group(1)) > 50
    assert page.locator('.card-added').count() == page.locator('.library-story').count()
    expect(page.locator('#library-previous')).to_be_disabled()
    first_page_titles = page.locator('.library-story h3').all_text_contents()
    page.locator('#library-next').click()
    expect(page.locator('#library-page-status')).to_contain_text('Page 2 of')
    expect(page.locator('#library-page-status')).to_be_focused()
    assert page.locator('.library-story h3').all_text_contents() != first_page_titles
    page.locator('#library-page-size').select_option('24')
    expect(page.locator('#library-page-status')).to_contain_text('Page 1 of')
    expect(page.locator('.library-story')).to_have_count(24)
    page.locator('#library-page-size').select_option('12')
    page.locator('#library-next').click()
    page.locator('#search').fill('ChatGPT as cognitive scaffold')
    expect(page.locator('#library-page-status')).to_contain_text('Page 1 of')
    expect(page.locator('.library-story')).to_have_count(1)
    page.locator('#library-reset').click()
    expect(page.locator('#library-page-status')).to_contain_text('Page 1 of')
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
    filter_dialog, filter_trigger = open_reading_card(page, page.locator('.library-refine'))
    page.locator('#scope-filter').select_option('historical')
    close_reading_card(page, filter_dialog, filter_trigger)
    expect(page.locator('#library-context')).to_contain_text('Earlier foundations')
    if not page.locator('.library-story').count():
        expect(page.locator('#library-results')).to_contain_text('No source-backed items')
    page.locator('#library-reset').click()
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
    expect(page.locator('#article-section')).to_have_value('overview')
    expect(page.locator('#article-overview')).to_be_visible()
    expect(page.locator('#article-source')).not_to_be_visible()
    page.locator('#article-section').select_option('source')
    expect(page.locator('#article-source')).to_be_visible()
    expect(page.locator('#article-overview')).not_to_be_visible()
    provenance = page.locator('.rv-provenance')
    expect(provenance.locator('.rv-status')).not_to_be_visible()
    dialog, trigger = open_reading_card(page, provenance)
    expect(dialog.locator('.rv-status')).to_be_visible()
    close_reading_card(page, dialog, trigger)
    expect(provenance.locator('.rv-status')).not_to_be_visible()
    page.locator('#article-section').select_option('overview')
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
    coverage = page.locator('.rv-coverage')
    expect(coverage.locator('.rv-coverage-table')).not_to_be_visible()
    page.locator('#article-section').select_option('source')
    expect(coverage.locator('.rv-coverage-table')).to_be_visible()
    expect(page.locator('.rv-content')).to_contain_text('n = 47')
    expect(page.locator('.automatic-evidence')).to_contain_text('Source: abstract')
    overflow(); screenshot('source-reading')
    page.locator('#article-section').select_option('evidence')
    reader = page.locator('.rv-source-excerpts')
    expect(reader.locator('.rv-reader-contents')).to_be_visible()
    reader.get_by_role('button', name='Abstract', exact=True).click()
    abstract = reader.locator('.rv-source-section').filter(has=page.locator('.rv-source-section-title span').filter(has_text='Abstract'))
    expect(abstract.locator('.rv-prose')).to_be_visible()
    assert abstract.locator('.rv-prose p').count() > 1
    expect(reader.locator('.rv-source-section:visible')).to_have_count(1)
    overflow(); screenshot('source-reader')
    reader.get_by_role('button', name='Read all source sections', exact=True).click()
    expect(reader.locator('.rv-source-section:visible')).to_have_count(reader.locator('.rv-source-section').count())
    reader.get_by_role('button', name='One section at a time', exact=True).click()
    expect(reader.locator('.rv-source-section:visible')).to_have_count(1)
    page.locator('#article-section').select_option('overview')
    expect(reader).not_to_be_visible()
    page.locator('#article-section').select_option('evidence')
    expect(reader.locator('.rv-reader-contents')).to_be_visible()
    overflow()
    # Every main destination remains available, with no page-level horizontal scroll.
    for route in ['issue', 'perspectives', 'atlas', 'about', 'home']:
        navigate(route)
        expect(page.locator(f'#{route}')).to_be_visible()
        overflow(); screenshot(route)
        if route == 'issue':
            expect(page.locator('#issue-section')).to_have_value('overview')
            cards = page.locator('#issue-takeaways .takeaway-card')
            assert cards.count() > 0
            turn = cards.first.locator('.flip-toggle')
            turn.focus(); page.keyboard.press('Enter')
            expect(turn).to_have_attribute('aria-pressed', 'true')
            expect(cards.first.locator('.takeaway-back')).to_be_visible()
            expect(cards.first.locator('.takeaway-back li')).not_to_be_empty()
            page.keyboard.press('Enter')
            expect(turn).to_have_attribute('aria-pressed', 'false')
            expect(cards.first.locator('.takeaway-back')).not_to_be_visible()
            cards.first.get_by_role('button', name='Explore the evidence').click()
            expect(page.locator('#issue-section')).to_have_value('themes')
            expect(page.locator('#issue-theme')).to_have_value('0')
            expect(page.locator('#issue-signals .issue-signal:visible')).to_have_count(1)
            page.locator('#issue-section').select_option('sources')
            source_shelf = page.locator('.issue-reading-shelf')
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



def check_weekly_citations(page, url, width, out):
    """Exercise citations/glossary with a frozen, real published edition.

    The current edition is tested separately on the main routes and standalone
    pages. It need not include glossary terms. This regression uses the immutable
    November 7 edition so later valid issues cannot accidentally remove coverage
    of source spans, term focus, and history navigation.
    """
    import json
    from hashlib import sha256
    from urllib.parse import parse_qs, urlsplit, urlunsplit
    current = json.loads((ROOT / 'data/public-featured-issue.json').read_text())
    archived = json.loads((ROOT / 'data/approved-issues' / (current['edition_date'] + '.json')).read_text())
    assert current == archived, 'Featured edition must remain its exact published snapshot'
    fixture_path = ROOT / 'data/edition-revisions/2026-11-07.json'
    issue = json.loads(fixture_path.read_text())
    assert issue['status'] == 'published' and issue['edition_date'] == '2026-11-07'
    assert issue.get('citation_schema_version') == 1 and issue.get('glossary'), 'Archived citation fixture lacks definitions'
    assert all(section.get('citations') for section in [*issue['signals'], issue['tension']]), 'Archived citation fixture must exercise every source span section'
    # Override only this page's edition projection. Keep the actual production
    # index/assets, app rendering, and untouched archived HTML. No content is
    # written to disk and the latest edition remains the public default.
    manifest = json.loads((ROOT / 'data/reader-manifest.json').read_text())
    manifest.update(issue=issue, edition_id=issue['edition_date'],
                    edition_sha256=sha256((json.dumps(issue, ensure_ascii=False,
                        sort_keys=True, separators=(',', ':')) + '\n').encode()).hexdigest())
    page.route('**/data/reader-manifest.json', lambda route: route.fulfill(
        status=200, content_type='application/json', body=json.dumps(manifest)))
    page.route('**/data/public-featured-issue.json', lambda route: route.fulfill(
        status=200, content_type='application/json', body=json.dumps(issue)))
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(url + '#issue', wait_until='networkidle')
    expect(page.locator('#issue')).to_be_visible()
    expect(page.locator('#issue-headline')).to_have_text(issue['headline'])
    expect(page.locator('#issue-section')).to_have_value('overview')
    sources = {source['id']: source for source in issue['sources']}

    def verify_citations(scope, section, css):
        for citation in section['citations']:
            source = sources[citation['source_id']]
            href = source.get('source_url') or source['url']
            parsed = urlsplit(href)
            if citation.get('page') and (parsed.path.endswith('.pdf') or '/pdf/' in parsed.path):
                href = urlunsplit(parsed._replace(fragment='page=' + str(citation['page'])))
            anchors = scope.locator(css).filter(has_text=re.compile('^' + re.escape(citation['text']) + '$'))
            assert anchors.count() > 0, 'Missing rendered citation: ' + citation['text']
            for anchor in anchors.all():
                expect(anchor).to_have_text(citation['text'])
                expect(anchor).to_have_attribute('href', href)
                expect(anchor).to_have_attribute('title', re.compile(re.escape(source['title'])))
                if citation.get('locator'):
                    expect(anchor).to_have_attribute('title', re.compile(re.escape(citation['locator'])))
    page.locator('#issue-section').select_option('themes')
    for index, section in enumerate(issue['signals']):
        page.locator('#issue-theme').select_option(str(index))
        panel = page.locator('#issue-signals .issue-signal').nth(index)
        expect(panel).to_be_visible()
        verify_citations(panel, section, 'a.issue-inline-citation')
        dialog, trigger = open_reading_card(page, panel.locator('.reading-expansion'))
        verify_citations(dialog, section, 'a.issue-inline-citation')
        expect(dialog.locator('a.issue-inline-citation').first).to_be_visible()
        close_reading_card(page, dialog, trigger)
        verify_citations(panel, section, 'a.issue-inline-citation')
    page.locator('#issue-section').select_option('question')
    verify_citations(page.locator('#issue-tension-text'), issue['tension'], 'a.issue-inline-citation')
    dialog, trigger = open_reading_card(page, page.locator('#issue-tension-text .reading-expansion'))
    verify_citations(dialog, issue['tension'], 'a.issue-inline-citation')
    close_reading_card(page, dialog, trigger)
    # Native links also work from an open card, across touch and keyboard input.
    page.locator('#issue-section').select_option('themes')
    page.locator('#issue-theme').select_option('2')
    dialog, trigger = open_reading_card(page, page.locator('#issue-signals .issue-signal').nth(2).locator('.reading-expansion'))
    term = dialog.locator('a.issue-glossary-term:visible').first
    target_id = parse_qs(urlsplit(term.get_attribute('href')[1:]).query)['term'][0]
    if width <= 600:
        term.tap()
    else:
        term.focus()
        page.keyboard.press('Enter')
    definition = page.locator('#' + target_id)
    expect(definition).to_be_focused()
    expect(page.locator('#issue')).to_be_visible()
    expect(definition.locator('xpath=following-sibling::dd[1]')).to_be_visible()
    assert definition.evaluate('(e) => { const r=e.getBoundingClientRect(); return r.top>=0 && r.bottom<=innerHeight; }')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Weekly glossary overflow at {width}px'
    if out:
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / f'observatory-{width}-weekly-glossary.png'))
    page.go_back()
    expect(page).to_have_url(url + '#issue')
    expect(page.locator('#issue')).to_be_visible()
    # Repeated navigation must not strand the reader on Home or a stale target.
    page.go_forward()
    expect(definition).to_be_focused()
    expect(page.locator('#issue')).to_be_visible()

    archive_url = url + 'issues/history/' + issue['edition_date'] + '.html'
    page.goto(archive_url, wait_until='networkidle')
    check_typography(page, [('h1', 'Gentium Book Plus', 32), ('.scope', 'Open Sans', 13)])
    expect(page.locator('h1')).to_have_text(issue['headline'])
    page.locator('#edition-read-all').click()
    expect(page.locator('#edition-read-all')).to_have_attribute('aria-pressed', 'true')
    for index, section in enumerate(issue['signals']):
        verify_citations(page.locator('#signal-' + str(index + 1)), section, 'a.inline-citation')
    archive_term = page.locator('a.glossary-term:visible').first
    fragment = archive_term.get_attribute('href')
    assert fragment.startswith('#term-'), 'Archive glossary link must target a real definition'
    if width <= 600:
        archive_term.tap()
    else:
        archive_term.focus()
        page.keyboard.press('Enter')
    expect(page).to_have_url(archive_url + fragment)
    target = page.locator(fragment)
    definition = target.locator('xpath=following-sibling::dd[1]')
    expect(target).to_be_focused()
    # Native fragment scrolling can settle after the URL changes, and fractional
    # CSS pixels can round across zero. Retry actual viewport checks, not merely
    # DOM visibility; retain precise geometry if a browser still misses its target.
    try:
        expect(target).to_be_in_viewport()
        expect(definition).to_be_in_viewport()
        page.wait_for_function('''id => {
            const term = document.getElementById(id), definition = term.nextElementSibling;
            return [term, definition].every(e => {
                const r = e.getBoundingClientRect();
                return r.top >= -1 && r.bottom <= innerHeight + 1 && r.height > 0;
            });
        }''', arg=fragment[1:])
    except Exception as error:
        geometry = target.evaluate('''e => ({
            term: e.getBoundingClientRect().toJSON(),
            definition: e.nextElementSibling.getBoundingClientRect().toJSON(),
            viewport: {width: innerWidth, height: innerHeight}, scrollY
        })''')
        raise AssertionError(f'Archive glossary scroll/focus failed at {width}px: {geometry}') from error
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Archive glossary overflow at {width}px'
    page.go_back()
    expect(page).to_have_url(archive_url)
    assert not errors, errors
    print(f'Archived 2026-11-07 citation regression passed at {width}px: exact source/page links, keyboard/touch, focus, Back/Forward, archive definitions.')


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
        samples = [('h1', 'Gentium Book Plus', 32)]
        samples += ([('.scope', 'Open Sans', 13)] if name == 'newsletter' else
                    [('#feed-url', 'Open Sans', 16), ('.feed-row button', 'Jost', 16)])
        check_typography(page, samples)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'{name} overflow at {width}px'
        if out:
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / f'observatory-{width}-{name}.png'), full_page=True)
        if args.browser == 'chromium' and width in (1280, 390):
            frame = page.screenshot(type='jpeg', quality=55, full_page=False)
            print(f'DESIGN_REVIEW_IMAGE:{width}:{name}:' + base64.b64encode(frame).decode('ascii'), flush=True)
        if name == 'newsletter':
            panels = page.locator('[data-edition-panel]')
            assert panels.count() >= len(latest['signals'])
            expect(page.locator('[data-edition-panel]:visible')).to_have_count(1)
            expect(page.locator('#edition-section')).to_have_value('signal-1')
            # Keyboard section selection changes the reading panel, not the page height.
            if len(latest['signals']) > 1:
                page.locator('#edition-section').select_option('signal-2')
                expect(page.locator('#signal-2')).to_be_visible()
                expect(page.locator('#signal-1')).not_to_be_visible()
            opening = page.locator('[data-open-layer="opening"]')
            expect(opening).to_be_visible()
            opening.focus()
            page.keyboard.press('Enter')
            dialog = page.get_by_role('dialog')
            expect(dialog).to_be_visible()
            expect(dialog.locator('.dialog-body')).to_contain_text(latest['letter'])
            assert dialog.evaluate('(el) => el.contains(document.activeElement)'), 'Modal must receive focus'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Newsletter card overflow at {width}px'
            if out:
                page.screenshot(path=str(out / f'observatory-{width}-newsletter-opening.png'), full_page=False)
            page.keyboard.press('Escape')
            expect(dialog).not_to_be_visible()
            expect(opening).to_be_focused()
            page.locator('#edition-read-all').click()
            expect(page.locator('#edition-read-all')).to_have_attribute('aria-pressed', 'true')
            expect(page.locator('[data-edition-panel]:visible')).to_have_count(panels.count())
            for index, signal in enumerate(latest['signals'], 1):
                expect(page.locator('#signal-' + str(index))).to_contain_text(signal['text'])
            page.locator('#edition-read-all').click()
            expect(page.locator('[data-edition-panel]:visible')).to_have_count(1)
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
    # These controlled full-record fixtures also exercise the legacy fallback.
    # Ordinary browsing above exercises the production versioned reader export.
    page.route('**/data/reader-manifest.json', lambda route: route.fulfill(status=404, body=''))
    page.goto(url + '#library', wait_until='networkidle')
    expect(page.locator('.library-story')).to_have_count(2)
    card = page.locator('.library-story').filter(has_text=commentary['reading']['digest']['idea'])
    temporal = commentary['reading']['temporal_notice']
    for value in (temporal, 'policy analysis', 'Synthetic policy author', 'not human review'):
        expect(card).to_contain_text(value)
    card_details = card.locator('.card-reading-details')
    dialog, trigger = open_reading_card(page, card_details)
    expect(dialog.get_by_text(temporal, exact=False).last).to_be_visible()
    close_reading_card(page, dialog, trigger)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Typed card overflow at {width}px'
    card.locator('h3 button').click()
    expect(page.locator('#paper')).to_be_visible()
    paper = page.locator('#paper-content')
    expect(paper.locator('.rv-head')).to_contain_text(temporal)
    dates = paper.locator('.rv-source-dates')
    dialog, trigger = open_reading_card(page, dates)
    expect(dialog.locator('.rv-reading-notice')).to_be_visible()
    close_reading_card(page, dialog, trigger)
    for key in ('thesis', 'reasoning', 'examples', 'tension', 'qualification'):
        expect(paper).to_contain_text(commentary['reading']['digest']['longform'][key])
    for forbidden in ('How it was studied', 'Study approach', 'Reported finding', 'Main finding', 'Stale visual sentinel'):
        expect(paper).not_to_contain_text(forbidden)
    expect(paper.locator('.automatic-evidence, .rv-original-figure, .rv-context-grid')).to_have_count(0)
    expect(paper.locator('.rv-primary-link')).to_have_attribute('href', commentary['reading']['source_url'])
    evidence = paper.locator('.rv-evidence')
    expect(evidence).not_to_be_visible()
    page.locator('#article-section').select_option('evidence')
    expect(evidence.locator('.rv-source-locator')).to_have_count(5)
    expect(evidence.locator('.rv-source-locator').first).to_be_visible()
    expect(evidence).to_contain_text('extracted block 1')
    page.locator('#article-section').select_option('overview')
    expect(evidence.locator('.rv-source-locator').first).not_to_be_visible()
    page.locator('#article-section').select_option('evidence')
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
    page.locator('#article-section').select_option('evidence')
    expect(paper.locator('.rv-evidence')).to_contain_text('page 2')
    expect(paper.locator('.rv-evidence')).not_to_contain_text('extracted block')
    page.goto(url + '#issue', wait_until='networkidle')
    issue_view = page.locator('#issue')
    expect(issue_view).to_be_visible()
    issue_view.locator('#issue-section').select_option('sources')
    source_shelf = issue_view.locator('.issue-reading-shelf')
    expect(source_shelf.locator('.issue-shelf-item').first).to_be_visible()
    shelf = issue_view.locator('.issue-shelf-item').first
    expect(shelf).to_contain_text(temporal)
    expect(shelf).to_contain_text('Synthetic policy author')
    expect(shelf.locator('.rv-source-locator').first).not_to_be_visible()
    dialog, trigger = open_reading_card(page, shelf.locator('.issue-source-evidence'))
    expect(dialog.locator('.rv-source-locator').first).to_be_visible()
    expect(dialog).to_contain_text('extracted block 1')
    close_reading_card(page, dialog, trigger)
    expect(shelf.locator('.rv-source-locator').first).not_to_be_visible()
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
    # This accepted historical journal reading must reach the actual DOM,
    # not silently fall back to its older benefit-only automatic excerpt.
    cognitive_ease = [row for row in originals if row.get('doi') == '10.1016/j.chb.2024.108386']
    assert len(cognitive_ease) == 1, 'Accepted Cognitive Ease reading was not admitted'
    assert cognitive_ease[0]['reading']['source_version'] == 'publishedVersion'
    # Exercise the restored commentary through the real builder and DOM rather
    # than letting timestamp churn quietly reduce the set being tested.
    admitted_ids = {row['reading']['original_summary_id'] for row in originals}
    for note_id in ('checked-eff-moderation-2026-10-27',
                    'checked-eff-parenting-2026-10-29',
                    'checked-eff-siri-controls-2026-10-28'):
        assert note_id in admitted_ids, 'Accepted EFF reading was not admitted: ' + note_id
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
    page.route('**/data/reader-manifest.json', lambda route: route.fulfill(status=404, body=''))
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
        if identifier == '10.1016/j.chb.2024.108386':
            expect(paper).to_contain_text('91 university students were analyzed after one exclusion')
            expect(paper).to_contain_text('1.20 versus 1.87 out of seven possible')
            expect(paper).to_contain_text('did not differ significantly')
            expect(paper).to_contain_text('does not establish equivalence')
            expect(paper).to_contain_text('The load and quality comparisons adjusted')
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
            for label in ('How it was studied', 'Study approach', 'Main finding', 'Methods as indexed', 'Results as indexed'):
                expect(paper).not_to_contain_text(label)
            expect(paper.locator('.rv-context-grid')).to_have_count(0)
        if 'Preprint, not verified peer-reviewed evidence' in reading['notice']:
            expect(paper).to_contain_text('Limited reading.')
            expect(paper).to_contain_text('Article screening is not peer review')
        expect(paper.locator('.automatic-evidence, .rv-artwork, .rv-original-figure')).to_have_count(0)
        evidence = paper.locator('.rv-evidence')
        expect(evidence).to_have_count(1)
        page.locator('#article-section').select_option('evidence')
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
        page.locator('#article-section').select_option('overview')
        expect(evidence.locator('.rv-source-locator').first).not_to_be_visible()
        page.locator('#article-section').select_option('evidence')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Registered reading overflow: {identifier} at {width}px'
        if out:
            out.mkdir(parents=True, exist_ok=True)
            key = hashlib.sha256(identifier.encode()).hexdigest()[:12]
            page.screenshot(path=str(out / f'observatory-{width}-registered-{key}.png'), full_page=True)
    assert not errors, errors


def check_artwork_uniqueness(page, url):
    """Decode the served images, not their filenames or geometry metadata.

    Conservative visual-twin tripwires catch tiny redraws. Passing them does not
    establish conceptual quality; contact-sheet review remains required.
    """
    page.goto(url, wait_until='networkidle')
    audit = page.evaluate("""async () => {
      const records = await (await fetch('data/public-library.json')).json();
      const frames = [];
      for (const r of records) {
        const art=r.editorial_art;
        if(!art || art.status==='needs_review') {
          if(art?.src || art?.thumbnail_src) throw new Error('Review-required art retained a served image');
          continue;
        }
        const img=new Image(); img.src=art.thumbnail_src||art.src;
        await img.decode();
        for(const [w,h] of [[120,76],[76,58]]) {
          const canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;
          const ctx=canvas.getContext('2d',{willReadFrequently:true});
          ctx.fillStyle='#f4f0e8';ctx.fillRect(0,0,w,h);
          const scale=Math.min(w/img.naturalWidth,h/img.naturalHeight);
          const dw=img.naturalWidth*scale,dh=img.naturalHeight*scale;
          ctx.drawImage(img,(w-dw)/2,(h-dh)/2,dw,dh);
          frames.push({id:r.doi||r.url,title:r.title,width:w,pixels:Array.from(ctx.getImageData(0,0,w,h).data)});
        }
      }
      const close=[];let closest=1;
      for(let i=0;i<frames.length;i++)for(let j=i+1;j<frames.length;j++) {
        const a=frames[i],b=frames[j];if(a.width!==b.width || a.id===b.id)continue;
        let total=0,foreground=0,count=0;
        for(let p=0;p<a.pixels.length;p+=4) {
          const d=(Math.abs(a.pixels[p]-b.pixels[p])+Math.abs(a.pixels[p+1]-b.pixels[p+1])+Math.abs(a.pixels[p+2]-b.pixels[p+2]))/3;
          total+=d;
          const ink=[0,1,2].some(k=>Math.abs(a.pixels[p+k]-[244,240,232][k])>30 || Math.abs(b.pixels[p+k]-[244,240,232][k])>30);
          if(ink){foreground+=d;count++;}
        }
        const mean=total/(a.pixels.length/4)/255,fg=foreground/Math.max(count,1)/255;
        closest=Math.min(closest,mean);
        if(mean<0.025 && fg<0.12)close.push({left:a.title,right:b.title,width:a.width,mean,foreground:fg});
      }
      return {images:frames.length/2,closest,close};
    }""")
    assert audit['images'] > 50, 'Artwork audit did not inspect the real corpus'
    assert not audit['close'], f"Near-duplicate served thumbnails require redesign/review: {audit['close']}"
    print(f"Decoded artwork audit: {audit['images']} covers at 120×76 and 76×58; no visual-twin tripwire; closest full RGB difference {audit['closest']:.4f}")
    page.close()


def check_reader_headings(page, url, width):
    """Headings and metadata work for live-shaped records, at every supported width."""
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(url, wait_until='networkidle')
    expect(page.locator('#library-count')).to_contain_text('matching sources')
    audit = page.evaluate("""() => S.records.map(x => ({
      title: readingHeadline(x), source: readableSourceTitle(x),
      automatic: x.reading?.digest?.status === 'automatically_condensed_source_text',
      type: readingKind(x), basis: readingBasisName(x)
    }))""")
    assert len(audit) > 50
    for row in audit:
        assert row['type'] in ('Research', 'Commentary', 'Conceptual framework', 'Product guide')
        assert not re.search(r'\b(?:p|r|b|se|sd)\s*[=<>]|β\s*=', row['title'], re.I)
        if row['automatic']:
            assert row['title'] == row['source']
    page.evaluate("goto('library')")
    expect(page.locator('#library')).to_be_visible()
    for label in page.locator('.card-type').all_text_contents():
        assert '/' not in label and 'RESULT' not in label
    sample = page.evaluate("""async () => {
      const x = S.records.find(x => x.doi === '10.3389/fpsyg.2026.1971672');
      const full = x.article_payload ? await jsonPayload(readerPath(x.article_payload), true) : x;
      goto('paper', id(x));
      return {title:readableSourceTitle(x), finding:full.reading.digest.finding};
    }""")
    expect(page.locator('.rv-headline')).to_have_text(sample['title'])
    assert page.locator('.rv-headline').evaluate('(el) => document.activeElement === el'), 'Navigation must focus the complete heading'
    expect(page.locator('.rv-content')).to_contain_text(sample['finding'])
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    # Full-text availability cannot relabel a finding taken from the abstract.
    page.evaluate("""() => {
      const x={kind:'scholarly',doi:'10.0000/browser-label-regression',
        title:'A study of AI literacy and cognitive load',
        reading:{level:'full_text',digest:{status:'automatically_condensed_source_text',
          idea:'In contrast, cognitive load was negatively correlated with AI literacy (r = −0.361, p < 0.01).',
          finding:'Cognitive load was negatively correlated with AI literacy (r = −0.361, p < 0.01).',finding_source:'abstract'}}};
      S.records.push(x);goto('paper',id(x));
    }""")
    expect(page.locator('.rv-headline')).to_have_text('A study of AI literacy and cognitive load')
    expect(page.locator('.rv-source-row')).to_contain_text('Based on the abstract')
    expect(page.locator('.rv-claim')).to_contain_text('r = −0.361, p < 0.01')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=['chromium','firefox','webkit'], default='chromium')
    parser.add_argument('--screenshots', type=Path)
    parser.add_argument('--executable-path', type=str)
    args = parser.parse_args()
    # Exercise the actual publication projection, not a stale committed payload.
    subprocess.run([sys.executable, str(ROOT / "scripts/build_public.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/build_newsletter.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/build_reader.py")], cwd=ROOT, check=True)
    registered = registered_reading_payloads()
    with server() as url, sync_playwright() as p:
        browser = getattr(p, args.browser).launch(**({"executable_path":args.executable_path} if args.executable_path else {}))
        art_context=browser.new_context()
        try:
            check_artwork_uniqueness(art_context.new_page(),url)
        finally:
            art_context.close()
        for width in [1280, 768, 390, 320]:
            context = browser.new_context(reduced_motion='reduce', has_touch=width <= 600)
            try:
                check(context.new_page(), url, width, args.screenshots)
                check_weekly_citations(context.new_page(), url, width, args.screenshots)
                check_standalone_brief(context.new_page(), url, width, args.screenshots)
                check_typed_readings(context.new_page(), url, width, args.screenshots)
                check_registered_readings(context.new_page(), url, width, args.screenshots, registered)
                check_reader_headings(context.new_page(), url, width)
            finally:
                context.close()
        print(f'Observatory browsing passed in {args.browser}: 1280, 768, 390, 320px; theme navigation, filters, dates, reading pages, all routes, generated newsletter and RSS subscription pages.')
        browser.close()

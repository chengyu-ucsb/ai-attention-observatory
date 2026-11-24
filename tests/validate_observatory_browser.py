"""Full-application browsing checks plus explicitly synthetic typed-receipt regressions.

Playwright browser builds are not a substitute for device/screen-reader testing.
"""
import argparse
import base64
from contextlib import contextmanager
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
    expect(trigger).to_be_focused()
    page.keyboard.press('Enter')
    dialog = page.get_by_role('dialog')
    expect(dialog).to_be_visible()
    assert dialog.evaluate('(el) => el.contains(document.activeElement)')
    return dialog, trigger


def close_reading_card(page, dialog, trigger):
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    expect(trigger).to_be_focused()


def section_buttons(page, identifier):
    attribute = {'article-section': 'data-reading-view',
                 'edition-section': 'data-edition-target'}.get(identifier, 'data-section')
    return page.locator('#' + identifier), attribute


def choose_section(page, identifier, value, keyboard=False):
    nav, attribute = section_buttons(page, identifier)
    target = nav.locator(f'button[{attribute}="{value}"]')
    expect(target).to_be_visible()
    if keyboard:
        target.focus()
        expect(target).to_be_focused()
        page.keyboard.press('Enter')
    else:
        target.click()
    expect(nav).to_have_attribute('data-active-section', value)
    expect(target).to_have_attribute('aria-pressed', 'true')
    expect(nav.locator(f'button[{attribute}][aria-pressed="true"]')).to_have_count(1)


def check_section_navigation(page, identifier, values=None):
    """Every chapter remains directly visible and usable without a dropdown."""
    nav, attribute = section_buttons(page, identifier)
    expect(nav).to_be_visible()
    assert nav.evaluate('(el) => el.tagName') == 'NAV'
    expect(nav.locator('select')).to_have_count(0)
    buttons = nav.locator(f'button[{attribute}]')
    assert buttons.count() > 0, identifier
    if values is not None:
        assert buttons.evaluate_all('(els, key) => els.map(el => el.getAttribute(key))', attribute) == values
    for button in buttons.all():
        expect(button).to_be_visible()
        geometry = button.evaluate('''el => {
            const rect = el.getBoundingClientRect();
            return {x: rect.x, right: rect.right, width: rect.width, height: rect.height,
                    clientWidth: el.clientWidth, scrollWidth: el.scrollWidth,
                    clientHeight: el.clientHeight, scrollHeight: el.scrollHeight,
                    viewport: innerWidth};
        }''')
        assert geometry['width'] >= 44 and geometry['height'] >= 44, (identifier, geometry)
        assert geometry['x'] >= -1 and geometry['right'] <= geometry['viewport'] + 1, (identifier, geometry)
        assert geometry['scrollWidth'] <= geometry['clientWidth'] + 1, (identifier, geometry)
        assert geometry['scrollHeight'] <= geometry['clientHeight'] + 1, (identifier, geometry)
    assert nav.evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'), identifier


def check_chapter_layout(page, navigation, content, desktop_from):
    """At desktop width, chapters form a vertical rail beside the reading."""
    rail, reading = page.locator(navigation), page.locator(content)
    expect(rail).to_be_visible()
    expect(reading).to_be_visible()
    rail_box, reading_box = rail.bounding_box(), reading.bounding_box()
    if page.viewport_size['width'] >= desktop_from:
        assert rail_box['x'] + rail_box['width'] <= reading_box['x'] + 1, (rail_box, reading_box)
        buttons = rail.locator('button[data-section], button[data-reading-view], button[data-edition-target]')
        boxes = [button.bounding_box() for button in buttons.all()]
        for previous, current in zip(boxes, boxes[1:]):
            assert previous['y'] + previous['height'] <= current['y'] + 1, (previous, current)


def check_nested_cards(page):
    """Synthetic UI-only fixture: nested cards must restore parent nodes/focus."""
    page.evaluate("""() => {
      const fixture = document.createElement('section'); fixture.id='nested-card-fixture';
      fixture.setAttribute('aria-label','Synthetic interface fixture');
      const outer = document.createElement('div'); outer.id='fixture-parent-content';
      const label = document.createElement('p'); label.textContent='Parent interface context';
      const inner = document.createElement('div'); inner.id='fixture-child-content';
      const text = document.createElement('p'); text.textContent='Nested interface context';
      const leave = document.createElement('a'); leave.href='#home'; leave.textContent='Leave fixture';
      inner.append(text,leave);
      outer.append(label,layerButton('Open child fixture','Child fixture',inner));
      fixture.append(layerButton('Open parent fixture','Parent fixture',outer));
      document.body.append(fixture);
    }""")
    fixture = page.locator('#nested-card-fixture')
    parent_trigger = fixture.get_by_role('button', name='Open parent fixture', exact=True)
    parent_trigger.focus()
    expect(parent_trigger).to_be_focused()
    page.keyboard.press('Enter')
    parent = page.locator('#fixture-parent-content')
    expect(parent).to_be_visible()
    child_trigger = parent.get_by_role('button', name='Open child fixture', exact=True)
    child_trigger.focus()
    expect(child_trigger).to_be_focused()
    page.keyboard.press('Enter')
    child = page.locator('#fixture-child-content')
    expect(child).to_be_visible()
    page.keyboard.press('Escape')
    expect(child).not_to_be_visible()
    expect(parent).to_be_visible()
    expect(child_trigger).to_be_focused()
    page.keyboard.press('Escape')
    expect(page.locator('dialog[open]')).to_have_count(0)
    expect(parent_trigger).to_be_focused()
    expect(fixture.locator('#fixture-parent-content')).to_have_count(1)
    expect(fixture.locator('#fixture-child-content')).to_have_count(1)
    # Navigation from the child closes the whole stack and returns both live
    # nodes to their original owners, rather than leaving an orphan overlay.
    parent_trigger.click()
    child_trigger.click()
    child.get_by_role('link', name='Leave fixture', exact=True).click()
    expect(page.locator('#home')).to_be_visible()
    expect(page.locator('dialog[open]')).to_have_count(0)
    expect(fixture.locator('#fixture-parent-content')).to_have_count(1)
    expect(fixture.locator('#fixture-child-content')).to_have_count(1)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    fixture.evaluate('(el) => el.remove()')


# Audit hidden chapters and dialog content as well as the initially visible page.
# Publication dates and claims about research limitations remain legitimate.
INTERNAL_COPY = re.compile(
    r'Qualifications and unresolved issues|Source locators for this summary|'
    r'Locators refer to:|Limited reading of current publisher HTML|'
    r'No historical snapshot of the original publication was verified|'
    r'extraction and semantic completeness are not verified|source version identifier:|'
    r'extracted block [0-9]+|AI source-check scope:|'
    r'How hard a task feels, how many problems someone starts', re.I)


def check_reader_copy(scope):
    match = INTERNAL_COPY.search(scope.text_content())
    assert not match, f'Editorial process text reached the reader: {match.group()}'


def readable_words(scope):
    return scope.evaluate("""el => {
        const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        const text = [];
        while (walk.nextNode()) text.push(walk.currentNode.textContent);
        return text.join(' ').replace(/\\s+/g, ' ').trim();
    }""")


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
        if args.browser == 'chromium' and ((width in (1280, 390) and name in ('home', 'issue', 'reading-head', 'library', 'reading-navigation', 'issue-navigation')) or name.startswith('overflow')):
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
    expect(page.locator('#home-section')).to_have_attribute('data-active-section', 'overview')
    check_section_navigation(page, 'home-section', ['overview', 'ideas', 'landscape', 'recent', 'follow'])
    expect(page.locator('#home .field-guide')).to_be_visible()
    expect(page.locator('#beyond-journals')).not_to_be_visible()
    expect(page.locator('#home .glance-section')).not_to_be_visible()
    overflow(); screenshot('home')
    if out:
        for section, name in [('.home-edition','edition'),('.editorial-section','perspectives-preview'),('.field-guide','themes')]:
            choose_section(page, 'home-section', 'ideas' if section == '.editorial-section' else 'overview')
            page.locator('#home '+section).screenshot(path=str(out / f'observatory-{width}-{name}.png'), style='.site-header { visibility: hidden !important; }')
            if args.browser == 'chromium' and ((width == 1280 and name == 'perspectives-preview') or (width == 390 and name == 'themes')):
                frame = page.locator('#home '+section).screenshot(type='jpeg', quality=55, style='.site-header { visibility: hidden !important; }')
                print(f'DESIGN_REVIEW_IMAGE:{width}:{name}:' + base64.b64encode(frame).decode('ascii'), flush=True)
    choose_section(page, 'home-section', 'ideas', keyboard=True)
    expect(page.locator('#beyond-journals')).to_be_visible()
    expect(page.locator('#home .field-guide')).not_to_be_visible()
    # Fixed-size artwork must never cover adjacent editorial headlines.
    for card in page.locator('#home .editorial-card').all():
        artwork = card.locator('.story-visual-editorial')
        if artwork.count():
            art_box, title_box = artwork.bounding_box(), card.locator('h3').bounding_box()
            assert art_box['x'] + art_box['width'] <= title_box['x'] - 8, 'Editorial thumbnail overlaps its headline'
    choose_section(page, 'home-section', 'overview')
    # A free text question travels independently of the starting lenses.
    page.locator('#field-query').fill('notification')
    page.locator('#field-query').press('Enter')
    expect(page.locator('#library')).to_be_visible()
    expect(page.locator('#search')).to_have_value('notification')
    expect(page.locator('#scope-filter')).to_have_value('all')
    expect(page.locator('.library-story').first).to_be_visible()
    page.reload(wait_until='networkidle')
    expect(page.locator('#search')).to_have_value('notification')
    # Skip keeps the active route; a hash-only skip used to send readers home.
    page.locator('.skip').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#main')).to_be_focused()
    expect(page.locator('#library')).to_be_visible()
    page.goto(url + '#home', wait_until='networkidle')
    page.locator('.home-source-drawer > .layer-trigger').click()
    page.locator('.feature-go').first.click()
    expect(page.locator('#issue-section')).to_have_attribute('data-active-section', 'sources')
    expect(page.locator('#edition-source-0')).to_be_focused()
    page.goto(url + '#home', wait_until='networkidle')
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
    assert page.locator('.library-story .card-type').count() == page.locator('.library-story').count()
    expect(page.locator('#library-previous')).to_be_disabled()
    first_page_titles = page.locator('.library-story h3').all_text_contents()
    page.locator('#library-next').click()
    expect(page.locator('#library-page-status')).to_contain_text('Page 2 of')
    expect(page.locator('#library-page-status')).to_be_focused()
    assert page.locator('.library-story h3').all_text_contents() != first_page_titles
    page.reload(wait_until='networkidle')
    expect(page.locator('#library-page-status')).to_contain_text('Page 2 of')
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
    # Sorting by the catalog arrival date must stay distinct from publication.
    dates = page.evaluate("""() => Object.fromEntries(S.records.map(x =>
      [readingHeadline(x), {published:x.published || '', added:x.first_seen || ''}]))""")
    count = page.locator('.library-story').count()
    for order in ('published', 'added'):
        page.locator('#library-sort').select_option(order)
        headings = page.locator('.library-story h3').all_text_contents()
        assert len(headings) == count
        card_dates = [dates[heading][order] for heading in headings]
        assert card_dates == sorted(card_dates, reverse=True), (order, card_dates)
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
    expect(page.locator('#article-section')).to_have_attribute('data-active-section', 'overview')
    check_section_navigation(page, 'article-section')
    check_chapter_layout(page, '#article-section', '.rv-reading-workspace > .rv-layout', 1000)
    page.locator('.rv-reading-workspace').evaluate("el => el.scrollIntoView({block:'start',behavior:'instant'})")
    screenshot('reading-navigation')
    expect(page.locator('#article-overview')).to_be_visible()
    expect(page.locator('#article-source')).not_to_be_visible()
    choose_section(page, 'article-section', 'source', keyboard=True)
    expect(page.locator('#article-source')).to_be_visible()
    expect(page.locator('#article-overview')).not_to_be_visible()
    expect(page.locator('.rv-source-title')).to_be_visible()
    expect(page.locator('.rv-primary-link')).to_have_attribute('href', re.compile(r'^https://'))
    check_reader_copy(page.locator('#paper-content'))
    page.locator('.rv-read-all').click()
    expect(page.locator('#article-section')).to_have_attribute('data-active-section', 'all')
    expect(page.locator('.rv-read-all')).to_have_attribute('aria-pressed', 'true')
    for panel_id in page.locator('#article-section [data-reading-view]').evaluate_all('(els) => els.map(el => el.getAttribute("aria-controls"))'):
        expect(page.locator('#' + panel_id)).to_be_visible()
    choose_section(page, 'article-section', 'overview')
    expect(page.locator('.rv-read-all')).to_have_attribute('aria-pressed', 'false')
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
    choose_section(page, 'article-section', 'source')
    expect(page.locator('.rv-source-title')).to_be_visible()
    expect(page.locator('.rv-coverage-table')).to_have_count(0)
    expect(page.locator('.rv-content')).to_contain_text('n = 47')
    expect(page.locator('.rv-abstract-account')).to_have_count(1)
    expect(page.locator('.rv-source-row')).to_contain_text('Abstract excerpt')
    overflow(); screenshot('source-reading')
    choose_section(page, 'article-section', 'overview')
    # A full-width long card must not leave other paragraphs in a narrow,
    # mostly empty multi-column grid (the tutoring reading exposed this bug).
    board = page.locator('.auto-evidence-board')
    if board.count():
        measurements = board.evaluate('''el => ({width:el.getBoundingClientRect().width,
          cards:Array.from(el.children).map(card=>({width:card.getBoundingClientRect().width,
            font:parseFloat(getComputedStyle(card.querySelector(".auto-evidence-text")).fontSize)}))})''')
        for card in measurements['cards']:
            assert card['width'] >= min(280, measurements['width']) - 2, measurements
            assert card['font'] >= 16, measurements
    choose_section(page, 'article-section', 'evidence')
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
    choose_section(page, 'article-section', 'overview')
    expect(reader).not_to_be_visible()
    choose_section(page, 'article-section', 'evidence')
    expect(reader.locator('.rv-reader-contents')).to_be_visible()
    overflow()
    # Every main destination remains available, with no page-level horizontal scroll.
    for route in ['issue', 'perspectives', 'atlas', 'lab', 'about', 'home']:
        navigate(route)
        expect(page.locator(f'#{route}')).to_be_visible()
        overflow(); screenshot(route)
        if route == 'issue':
            expect(page.locator('#issue-section')).to_have_attribute('data-active-section', 'overview')
            check_section_navigation(page, 'issue-section', ['overview', 'themes', 'question', 'sources', 'about'])
            check_chapter_layout(page, '#issue-navigation', '.issue-content', 1000)
            page.locator('.issue-layout').evaluate("el => el.scrollIntoView({block:'start',behavior:'instant'})")
            screenshot('issue-navigation')
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
            cards.first.get_by_role('button', name='Read the discussion').click()
            expect(page.locator('#issue-section')).to_have_attribute('data-active-section', 'themes')
            expect(page.locator('#issue-theme')).to_have_attribute('data-active-section', '0')
            check_section_navigation(page, 'issue-theme')
            expect(page.locator('#issue-signals .issue-signal:visible')).to_have_count(1)
            choose_section(page, 'issue-section', 'sources')
            source_shelf = page.locator('.issue-reading-shelf')
            assert page.locator('.issue-shelf-item').count() > 0
            expect(source_shelf.locator('.issue-shelf-item').first).to_be_visible()
            shelf_count = page.locator('.issue-shelf-item').count()
            expect(page.locator('#issue-coverage')).to_contain_text(re.compile(r'^' + str(shelf_count) + r' sources(?:\b|$)'))
            screenshot('issue-sources')
        elif route == 'perspectives':
            check_section_navigation(page, 'perspectives-section', ['news', 'essays', 'products'])
            choose_section(page, 'perspectives-section', 'news')
            expect(page.locator('#perspectives-news')).to_be_visible()
            expect(page.locator('#perspectives-essays')).not_to_be_visible()
            choose_section(page, 'perspectives-section', 'essays')
            expect(page.locator('#perspectives-essays')).to_be_visible()
            expect(page.locator('#perspectives-news')).not_to_be_visible()
            choose_section(page, 'perspectives-section', 'products', keyboard=True)
            expect(page.locator('#perspectives-products')).to_be_visible()
            expect(page.locator('#perspectives-essays')).not_to_be_visible()
            choose_section(page, 'perspectives-section', 'essays')
        elif route == 'atlas':
            check_section_navigation(page, 'atlas-section', ['themes', 'years', 'material'])
            choose_section(page, 'atlas-section', 'years', keyboard=True)
            expect(page.locator('.atlas-years')).to_be_visible()
            expect(page.locator('.atlas-topic')).not_to_be_visible()
            choose_section(page, 'atlas-section', 'material')
            expect(page.locator('.atlas-coverage')).to_be_visible()
            expect(page.locator('.atlas-matrix')).to_be_visible()
            choose_section(page, 'atlas-section', 'themes')
        elif route == 'lab':
            check_section_navigation(page, 'lab-section', ['experiments', 'design'])
            choose_section(page, 'lab-section', 'design', keyboard=True)
            expect(page.locator('.play-precedents')).to_be_visible()
            expect(page.locator('#lab-activities')).not_to_be_visible()
            choose_section(page, 'lab-section', 'experiments')
            expect(page.locator('#lab-catalog')).to_be_visible()
            expect(page.locator('.play-precedents')).not_to_be_visible()
        overflow()
    # Visual routes have ordinary destinations and no tracking/persistence.
    navigate('atlas')
    expect(page.locator('#atlas')).to_be_visible()
    navigate('perspectives')
    page.locator('#perspectives-library-link').click()
    # Filters change in the link handler before the hash route runs. Wait for
    # that route's visible/focused destination before opening a new card.
    expect(page.locator('#library')).to_be_visible()
    expect(page.locator('#library h1')).to_be_focused()
    expect(page.locator('#type-filter')).to_have_value('nonacademic')
    expect(page.locator('#scope-filter')).to_have_value('all')
    assert page.locator('.library-story').count() > 0
    # A new source topic can be browsed directly from the atlas on first load.
    page.evaluate("""() => {
      S.records.push({...S.records.find(row => row.kind === 'scholarly' && readingKind(row) === 'Research'), lane:'Joint attention fixture'});
      extendTopicChoices();goto('atlas');
    }""")
    choose_section(page, 'atlas-section', 'themes')
    page.get_by_role('link', name=re.compile('Joint attention fixture')).click()
    expect(page.locator('#topic-filter')).to_have_value('Joint attention fixture')
    expect(page.locator('.library-story')).to_have_count(1)
    check_nested_cards(page)
    navigate('library')
    page.get_by_role('link', name='How articles are added').click()
    process = page.locator('.process-map')
    expect(page.locator('#article-process')).to_be_focused()
    expect(process).to_be_visible()
    expect(process.locator('.process-stage')).to_have_count(3)
    expect(process.locator('.process-example img')).to_have_attribute('alt', re.compile('timer'))
    expect(process.locator('.process-weekly a')).to_have_attribute('href', '#issue')
    overflow()
    screenshot('article-process')
    process.locator('.process-example').click()
    expect(page.locator('#paper-content .rv-headline')).to_have_text('Who finishes an AI practice exam?')
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
    expect(page.locator('#issue-section')).to_have_attribute('data-active-section', 'overview')
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
    choose_section(page, 'issue-section', 'themes', keyboard=True)
    for index, section in enumerate(issue['signals']):
        choose_section(page, 'issue-theme', str(index))
        panel = page.locator('#issue-signals .issue-signal').nth(index)
        expect(panel).to_be_visible()
        verify_citations(panel, section, 'a.issue-inline-citation')
        dialog, trigger = open_reading_card(page, panel.locator('.reading-expansion'))
        verify_citations(dialog, section, 'a.issue-inline-citation')
        expect(dialog.locator('a.issue-inline-citation').first).to_be_visible()
        close_reading_card(page, dialog, trigger)
        verify_citations(panel, section, 'a.issue-inline-citation')
    choose_section(page, 'issue-section', 'question')
    verify_citations(page.locator('#issue-tension-text'), issue['tension'], 'a.issue-inline-citation')
    dialog, trigger = open_reading_card(page, page.locator('#issue-tension-text .reading-expansion'))
    verify_citations(dialog, issue['tension'], 'a.issue-inline-citation')
    close_reading_card(page, dialog, trigger)
    # Native links also work from an open card, across touch and keyboard input.
    choose_section(page, 'issue-section', 'themes')
    choose_section(page, 'issue-theme', '2')
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
            expect(page.locator('h1')).to_contain_text('Follow The Attention Brief')
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
            expect(page.locator('#edition-section')).to_have_attribute('data-active-section', 'signal-1')
            check_section_navigation(page, 'edition-section')
            check_chapter_layout(page, '.edition-controls', '.edition-reading', 1000)
            if args.browser == 'chromium' and width in (1280, 390):
                page.locator('.edition-layout').evaluate("el => el.scrollIntoView({block:'start',behavior:'instant'})")
                frame = page.screenshot(type='jpeg', quality=55, full_page=False)
                print(f'DESIGN_REVIEW_IMAGE:{width}:newsletter-navigation:' + base64.b64encode(frame).decode('ascii'), flush=True)
            # Keyboard section selection changes the reading panel, not the page height.
            if len(latest['signals']) > 1:
                choose_section(page, 'edition-section', 'signal-2', keyboard=True)
                expect(page.locator('#signal-2')).to_be_visible()
                expect(page.locator('#signal-1')).not_to_be_visible()
                choose_section(page, 'edition-section', 'edition-question', keyboard=True)
                expect(page.locator('#edition-question a[href="' + base + '#lab"]')).to_be_visible()
                page.go_back()
                expect(page.locator('#signal-2')).to_be_visible()
                page.go_back()
                expect(page.locator('#signal-1')).to_be_visible()
                page.go_forward()
                expect(page.locator('#signal-2')).to_be_visible()
            opening = page.locator('[data-open-layer="opening"]')
            expect(opening).to_be_visible()
            opening.focus()
            # Let pending paint callbacks run, then verify that history
            # navigation hasn't taken the keyboard back from this control.
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            expect(opening).to_be_focused()
            page.keyboard.press('Enter')
            dialog = page.get_by_role('dialog')
            expect(dialog).to_be_visible()
            opening_paragraphs = dialog.locator('.dialog-body .long-copy:visible').all_text_contents()
            assert opening_paragraphs, 'Opening argument must remain readable'
            assert re.sub(r'\s+', ' ', ' '.join(opening_paragraphs)).strip() == re.sub(r'\s+', ' ', latest['letter']).strip(), 'Opening argument changed'
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
                paragraphs = page.locator('#signal-' + str(index) + ' > .long-copy:visible').all_text_contents()
                assert paragraphs, 'Full theme text must remain readable'
                assert re.sub(r'\s+', ' ', ' '.join(paragraphs)).strip() == re.sub(r'\s+', ' ', signal['text']).strip(), 'Theme prose changed: ' + str(index)
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
    # The display heading is separate from both the bibliographic title and
    # approved summary prose. Exercise that distinction in navigation fixtures.
    checked['display_headline'] = 'Human oversight in AI decisions'
    preprint['display_headline'] = 'Easier tasks and lasting learning'
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
    card = page.locator('.library-story').filter(
        has=page.get_by_role('button', name=commentary['display_headline'], exact=True))
    expect(card.locator('h3 button')).to_have_text(commentary['display_headline'])
    expect(card.locator('h3 button')).to_be_visible()
    check_reader_copy(card)
    expect(card).to_contain_text(commentary['venue'])
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Typed card overflow at {width}px'
    card.locator('h3 button').click()
    expect(page.locator('#paper')).to_be_visible()
    paper = page.locator('#paper-content')
    expect(paper.locator('.rv-headline')).to_have_text(commentary['display_headline'])
    choose_section(page, 'article-section', 'source')
    expect(paper.locator('.rv-source-title')).to_have_text(commentary['title'])
    expect(paper.locator('.rv-source-title')).to_be_visible()
    choose_section(page, 'article-section', 'overview')
    check_reader_copy(paper)
    expect(paper.locator('.rv-ai-notice')).to_have_count(1)
    for key in ('thesis', 'reasoning', 'examples', 'tension'):
        expected = commentary['original_reading']['summary'][key]
        assert ' '.join(expected.split()) in readable_words(paper), 'Missing commentary content: ' + key
    for forbidden in ('How it was studied', 'Study approach', 'Reported finding', 'Main finding', 'Stale visual sentinel'):
        expect(paper).not_to_contain_text(forbidden)
    expect(paper.locator('.automatic-evidence, .rv-original-figure, .rv-context-grid')).to_have_count(0)
    expect(paper.locator('.rv-primary-link')).to_have_attribute('href', commentary['reading']['source_url'])
    expect(paper.locator('.rv-source-locator')).to_have_count(0)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Typed reading overflow at {width}px'
    if out:
        out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / f'observatory-{width}-synthetic-commentary.png'), full_page=True)
    paper.locator('.rv-back').click()
    expect(page.locator('#library')).to_be_visible()
    preprint_card = page.locator('.library-story').filter(
        has=page.get_by_role('button', name=preprint['display_headline'], exact=True))
    expect(preprint_card.locator('h3 button')).to_have_text(preprint['display_headline'])
    expect(preprint_card.locator('h3 button')).to_be_visible()
    preprint_card.locator('h3 button').click()
    expect(paper.locator('.rv-headline')).to_have_text(preprint['display_headline'])
    choose_section(page, 'article-section', 'source')
    expect(paper.locator('.rv-source-title')).to_have_text(preprint['title'])
    expect(paper.locator('.rv-source-title')).to_be_visible()
    choose_section(page, 'article-section', 'overview')
    expect(paper).to_contain_text(re.compile('preprint', re.I))
    expect(paper).to_contain_text(preprint['original_reading']['summary']['finding'])
    expect(paper).to_contain_text(preprint['original_reading']['summary']['limitation'])
    expect(paper.locator('.rv-primary-link')).to_have_attribute('href', preprint['reading']['source_url'])
    check_reader_copy(paper)
    page.goto(url + '#issue', wait_until='networkidle')
    issue_view = page.locator('#issue')
    expect(issue_view).to_be_visible()
    choose_section(page, 'issue-section', 'sources')
    source_shelf = issue_view.locator('.issue-reading-shelf')
    expect(source_shelf.locator('.issue-shelf-item').first).to_be_visible()
    expect(source_shelf.locator('.issue-shelf-item')).to_have_count(2)
    expect(source_shelf).to_contain_text(commentary['venue'])
    expect(source_shelf).to_contain_text(re.compile('preprint', re.I))
    check_reader_copy(source_shelf)
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
    assert any(row.get('companion_to') == '10.26300/80wn-ca81' and row['venue'] == 'Education Week'
               for row in originals), 'Education Week coverage must retain its own reading'
    # Exercise the restored commentary through the real builder and DOM rather
    # than letting timestamp churn quietly reduce the set being tested.
    admitted_ids = {row['reading']['original_summary_id'] for row in originals}
    for note_id in ('checked-eff-moderation-2026-10-27',
                    'checked-eff-siri-controls-2026-10-28'):
        assert note_id in admitted_ids, 'Accepted EFF reading was not admitted: ' + note_id
    assert 'checked-eff-parenting-2026-10-29' not in admitted_ids, 'Off-topic parenting advice reached the reader'
    if weekly.get('run', {}).get('publication_window'):
        start, end = previous_week(weekly['run']['date'])
        weekly_ids = {build_public.record_id(row) for row in weekly['items']}
        for row in originals:
            if not weekly_eligible(row, start, end):
                assert build_public.record_id(row) not in weekly_ids, 'An out-of-window original leaked into weekly publication'
    print(f'Registered-reading browser input: {len(originals)} admitted originals' +
          ('; actual original-reading DOM coverage skipped because none were admitted.' if not originals else '.'))
    return library, weekly, pending, originals


def check_registered_readings(page, url, width, out, payloads, *, fallback=False):
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
    if fallback:
        page.route('**/data/*.json*', fulfill)
        page.route('**/data/reader-manifest.json', lambda route: route.fulfill(status=404, body=''))
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    by_identifier = {row.get('doi') or row['url']: row for row in library}
    for row in originals:
        identifier = row.get('doi') or row['url']
        reading = row['reading']
        commentary = reading.get('research_type') == 'attributed_commentary'
        page.goto(url + '#paper/' + quote(identifier, safe=''), wait_until='networkidle')
        paper = page.locator('#paper-content')
        expect(page.locator('#paper')).to_be_visible()
        expect(paper.locator('.rv-headline')).to_have_text(row['display_headline'])
        choose_section(page, 'article-section', 'source')
        expect(paper.locator('.rv-source-title')).to_have_text(row['title'].strip())
        expect(paper.locator('.rv-source-title')).to_be_visible()
        if row.get('companion_to'):
            parent_id = row['companion_to']
            parent = by_identifier[parent_id]
            parent_link = paper.locator('.rv-paired-publication a')
            expect(parent_link).to_have_text(parent['display_headline'])
            expect(parent_link).to_have_attribute('href', '#paper/' + quote(parent_id, safe=''))
            expect(parent_link).to_be_visible()
        for companion in (item for item in library if item.get('companion_to') == identifier):
            companion_path = '#paper/' + quote(companion.get('doi') or companion['url'], safe='')
            coverage = paper.locator('.rv-paired-coverage .rv-excerpt').filter(
                has=page.get_by_role('link', name=companion['display_headline'], exact=True))
            expect(coverage.get_by_role('link', name=companion['display_headline'], exact=True)).to_have_attribute('href', companion_path)
            expect(coverage.get_by_role('link', name='Read the original story')).to_have_attribute(
                'href', companion['reading'].get('source_url') or companion['url'])
        expect(paper.locator('.rv-primary-link')).to_have_attribute('href', reading['source_url'])
        expect(paper.locator('.rv-source')).to_contain_text(row['venue'])
        choose_section(page, 'article-section', 'overview')
        expect(paper.locator('.rv-source-row')).to_be_visible()
        expect(paper.locator('.rv-ai-notice')).to_have_count(1)
        check_reader_copy(paper)
        if identifier == '10.1016/j.chb.2024.108386':
            expect(paper).to_contain_text('91 university students were analyzed after one exclusion')
            expect(paper).to_contain_text('1.20 versus 1.87 out of seven possible')
            expect(paper).to_contain_text('did not differ significantly')
            expect(paper).to_contain_text('does not establish equivalence')
            expect(paper).to_contain_text('The load and quality comparisons adjusted')
        # The page can reorder the approved summary. Check the substance rather
        # than requiring ingestion notices and internal receipts in its DOM.
        summary = row['original_reading']['summary']
        fields = ('thesis', 'examples') if commentary else ('approach', 'finding')
        words = readable_words(paper)
        for field in fields:
            if summary.get(field):
                assert ' '.join(summary[field].split()) in words, (identifier, field)
        if commentary:
            for label in ('How it was studied', 'Study approach', 'Main finding', 'Methods as indexed', 'Results as indexed'):
                expect(paper).not_to_contain_text(label)
            expect(paper.locator('.rv-context-grid')).to_have_count(0)
        if 'preprint' in reading['source_version']:
            expect(paper.locator('.rv-source-row')).to_contain_text(re.compile('preprint', re.I))
        expect(paper.locator('.automatic-evidence, .rv-original-figure')).to_have_count(0)
        if row.get('visual', {}).get('kind') == 'reviewed_comparison':
            expect(paper.locator('.reviewed-evidence')).to_have_count(1)
            table = paper.locator('.reviewed-comparison-table')
            expect(table).to_have_attribute('aria-label', row['visual']['description'])
            for comparison in row['visual']['rows']:
                for cell in comparison:
                    expect(table).to_contain_text(cell)
            expect(paper.locator('.reviewed-evidence a')).to_have_attribute('href', reading['source_url'])
        else:
            expect(paper.locator('.rv-artwork')).to_have_count(0)
        expect(paper.locator('.rv-source-locator')).to_have_count(0)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Registered reading overflow: {identifier} at {width}px'
        if out:
            out.mkdir(parents=True, exist_ok=True)
            key = hashlib.sha256(identifier.encode()).hexdigest()[:12]
            page.screenshot(path=str(out / f'observatory-{width}-registered-{key}.png'), full_page=True)
    if fallback:
        assert any('/data/public-library.json' in request for request in requests)
    else:
        assert any('/data/reader/articles/' in request for request in requests), 'Immutable reading payloads did not load'
        assert not any('/data/public-library.json' in request for request in requests), 'Manifest unexpectedly fell back to the compatibility library'
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
      title: readingHeadline(x), source: readableSourceTitle(x), edited: x.display_headline,
      automatic: x.reading?.digest?.status === 'automatically_condensed_source_text',
      type: readingKind(x), genre: x.reader_genre, basis: readingBasisName(x)
    }))""")
    assert len(audit) > 50
    for row in audit:
        assert row['type'] and row['genre'], row
        assert not re.search(r'\b(?:p|r|b|se|sd)\s*[=<>]|β\s*=', row['title'], re.I)
        if row.get('edited'):
            assert row['title'] == row['edited'] and len(row['title']) <= 55 and len(row['title'].split()) <= 10
        elif row['automatic']:
            assert row['title'] == row['source']
    page.evaluate("goto('library')")
    expect(page.locator('#library')).to_be_visible()
    for label in page.locator('.card-type').all_text_contents():
        assert '/' not in label and 'RESULT' not in label
    sample = page.evaluate("""async () => {
      const x = S.records.find(x => x.doi === '10.3389/fpsyg.2026.1971672');
      const full = x.article_payload ? await jsonPayload(readerPath(x.article_payload), true) : x;
      goto('paper', id(x));
      return {title:readingHeadline(x), finding:full.reading.digest.finding};
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


def check_collection_boundaries(page, url, width):
    """Follow every article route and compare the public collections to their source genres."""
    import json
    from urllib.parse import quote
    library = json.loads((ROOT / 'data/public-library.json').read_text())
    records = [row for row in library if not row.get('companion_to')]
    media = {'reporting', 'opinion', 'editorial', 'analysis', 'commentary', 'guide'}
    research = {'research', 'conceptual', 'proposal', 'review'}
    partitions = {
        'scholarly': research,
        'reporting': {'reporting'},
        'opinion': {'opinion', 'editorial'},
        'analysis': {'analysis', 'commentary'},
        'guide': {'guide'},
        'nonacademic': media,
    }
    assert all(row.get('reader_genre') in media | research for row in records)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(url + '#library', wait_until='networkidle')
    for value, genres in partitions.items():
        page.locator('#type-filter').select_option(value)
        expected = [row for row in records if row['reader_genre'] in genres]
        expect(page.locator('#library-count')).to_contain_text(
            re.compile(r'^' + str(len(expected)) + r' matching sources'))
        results = page.locator('#library-results')
        shown = []
        while True:
            check_reader_copy(results)
            shown.extend(results.locator('.library-story h3').all_text_contents())
            if page.locator('#library-next').is_disabled():
                break
            page.locator('#library-next').click()
        assert sorted(shown) == sorted(row['display_headline'] for row in expected), value
    page.goto(url + '#perspectives')
    for panel, genres in (('news', {'reporting'}), ('essays', media - {'reporting', 'guide'}),
                          ('products', {'guide'})):
        choose_section(page, 'perspectives-section', panel)
        scope = page.locator('#perspectives-' + panel)
        actual = scope.locator('article h3').all_text_contents()
        expected = [row['display_headline'] for row in records if row['reader_genre'] in genres]
        assert sorted(actual) == sorted(expected), (panel, actual, expected)

    for row in library:
        identifier = row.get('doi') or row['url']
        page.goto(url + '#paper/' + quote(identifier, safe=''))
        paper = page.locator('#paper-content')
        expect(paper.locator('.rv-source-title')).to_have_text(row['title'].strip())
        expect(paper.locator('.rv-headline')).to_be_visible()
        if row.get('display_headline'):
            expect(paper.locator('.rv-headline')).to_have_text(row['display_headline'])
        family = 'research' if row['reader_genre'] in research else 'product' if row['reader_genre'] == 'guide' else 'media'
        expect(paper.locator('.rv-article')).to_have_attribute('data-source-family', family)
        reading = row.get('reading') or {}
        if (family == 'research' and row['reader_genre'] != 'proposal' and not reading.get('original_summary')
                and reading.get('level') == 'full_text'
                and reading.get('digest', {}).get('editorial_basis') == 'publisher_full_article_paraphrased'):
            overview = paper.locator('#article-overview')
            account = overview.locator('.rv-study-account')
            expect(account).to_be_visible()
            expect(overview.locator('.automatic-evidence')).to_have_count(0)
            content = ' '.join(account.inner_text().split())
            for field in ['methods', 'findings', 'interpretation', 'limitations']:
                if reading.get(field):
                    # An identical passage may already serve as the opening sentence.
                    assert ' '.join(reading[field].split()) in content + ' ' + ' '.join(
                        paper.locator('.rv-intro-copy').inner_text().split()), (identifier, width, field)
            expect(paper.locator('.rv-source-row')).to_contain_text('Based on the full article')
        if (family == 'research' and reading.get('digest', {}).get('status') == 'automatically_condensed_source_text'
                and row.get('abstract_text') and not reading.get('machine_account')):
            account = paper.locator('#article-overview .rv-abstract-account')
            expect(account).to_be_visible()
            expect(paper.locator('.rv-ai-notice')).to_have_count(0)
            assert len(account.inner_text().split()) > 3, (identifier, width)
            assert account.inner_text().rstrip().endswith(('.', '!', '?', '”', '"', "'", ')', ']')), (identifier, width)
        if row['reader_genre'] in media:
            headline = paper.locator('.rv-headline').inner_text()
            assert len(headline) <= 55 and len(headline.split()) <= 10, (identifier, headline)
            headings = ' | '.join(paper.locator('h2, h3, .rv-mini-label').all_text_contents())
            assert not re.search(r'How it was studied|What the study reports|Main finding', headings), (identifier, headings)
        check_reader_copy(paper)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (identifier, width)

    pending = json.loads((ROOT / 'data/public-pending-sources.json').read_text())
    for row in pending:
        page.goto(url + '#paper/' + quote(row['url'], safe=''))
        notice = page.locator('.rv-awaiting-reading')
        expect(notice).to_be_visible()
        expect(notice).to_contain_text(row['title'])
        expect(notice.locator('a')).to_have_attribute('href', row['url'])
        check_reader_copy(notice)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (row['url'], width)

    for route in ('home', 'library', 'perspectives', 'atlas', 'issue', 'lab', 'about'):
        page.goto(url + '#' + route)
        view = page.locator('#' + route)
        expect(view).to_be_visible()
        check_reader_copy(view)
    # Include past issues, superseded permalinks, and the follow page.
    for path in sorted((ROOT / 'issues').rglob('*.html')) + [ROOT / 'newsletter.html', ROOT / 'subscribe.html']:
        response = page.goto(url + path.relative_to(ROOT).as_posix(), wait_until='domcontentloaded')
        assert response and response.ok, path
        check_reader_copy(page.locator('body'))
    assert not errors, errors
    print(f'{width}px: checked {len(library)} article routes, {len(pending)} pending-source pages, all genre filters, perspectives sections and the issue archive.')
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
                check_registered_readings(context.new_page(), url, width, args.screenshots, registered, fallback=width <= 600)
                check_reader_headings(context.new_page(), url, width)
                if args.browser == 'chromium' and width in (390, 1280):
                    check_collection_boundaries(context.new_page(), url, width)
            finally:
                context.close()
        print(f'Observatory browsing passed in {args.browser}: 1280, 768, 390, 320px; theme navigation, filters, dates, reading pages, all routes, generated newsletter and RSS subscription pages.')
        browser.close()

"""Keep typography a shared, deployable contract across live and generated pages."""
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_newsletter


class StyleSources(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.sources = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'style':
            self.sources.append(('inline', ''))
        elif tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.sources.append(('link', attrs.get('href', '')))


class TypographyContractTests(unittest.TestCase):
    def test_all_web_entrypoints_resolve_one_shared_contract_before_local_rules(self):
        paths = [ROOT / name for name in ('index.html', 'subscribe.html', 'newsletter.html')]
        paths += sorted((ROOT / 'issues').glob('*.html'))
        for path in paths:
            with self.subTest(page=str(path.relative_to(ROOT))):
                sources = StyleSources(path.read_text()).sources
                self.assertTrue(sources)
                kind, href = sources[0]
                self.assertEqual(kind, 'link')
                self.assertFalse(urlsplit(href).scheme, 'Fonts should work in local and nested previews')
                self.assertEqual((path.parent / href).resolve(), ROOT / 'assets/typography.css')
                self.assertEqual(sum('typography.css' in value for _, value in sources), 1)
        # XSL produces HTML in the feed document, whose base is the site root.
        links = ET.parse(ROOT / 'assets/feed.xsl').findall('.//link')
        css = next(node.get('href') for node in links if node.get('rel') == 'stylesheet')
        self.assertEqual((ROOT / css).resolve(), ROOT / 'assets/typography.css')

    def test_future_generated_issues_use_the_correct_nested_asset_path(self):
        issue = next(json.loads(path.read_text()) for path in
                     sorted((ROOT / 'data/approved-issues').glob('*.json'), reverse=True)
                     if json.loads(path.read_text()).get('status') == 'published')
        for prefix in ('', '../'):
            page = build_newsletter.render_issue(issue, asset_prefix=prefix)
            self.assertEqual(StyleSources(page).sources[0], ('link', prefix + 'assets/typography.css'))
        self.assertEqual(StyleSources(build_newsletter.render_index([issue])).sources[0],
                         ('link', '../assets/typography.css'))

    def test_font_assets_are_local_licensed_and_within_budget(self):
        folder = ROOT / 'assets/fonts'
        manifest = json.loads((folder / 'manifest.json').read_text())
        css = (ROOT / 'assets/typography.css').read_text()
        files = set()
        total = 0
        for entry in manifest:
            with self.subTest(font=entry['file']):
                self.assertEqual(Path(entry['file']).name, entry['file'])
                self.assertNotIn(entry['file'], files)
                files.add(entry['file'])
                data = (folder / entry['file']).read_bytes()
                self.assertEqual(data[:4], b'wOF2')
                self.assertEqual(len(data), entry['bytes'])
                self.assertEqual(sha256(data).hexdigest(), entry['sha256'])
                self.assertEqual(urlsplit(entry['source']).scheme, 'https')
                self.assertIn('fonts/' + entry['file'], css)
                license_name = entry['family'].lower().replace(' ', '') + '-OFL.txt'
                self.assertIn('SIL OPEN FONT LICENSE', (folder / license_name).read_text())
                total += len(data)
        self.assertLess(total, 300 * 1024, 'New typefaces need an explicit asset-budget review')
        self.assertEqual(files, {p.name for p in folder.glob('*.woff2')})
        self.assertEqual(set(re.findall(r'url\(fonts/([^()]+)\)', css)), files)
        faces = re.findall(r'@font-face\s*\{([^}]+)\}', css)
        self.assertEqual(len(faces), len(manifest))
        self.assertTrue(all('font-display: swap' in face for face in faces))
        self.assertNotRegex(css, r'(?:url|@import)\s*\(?[\s\'"]*https?://')

    def test_family_definitions_do_not_drift_into_components_or_generators(self):
        files = ['styles.css', 'lab-play.css', 'index.html', 'subscribe.html',
                 'scripts/build_newsletter.py', 'assets/feed.xsl', 'app.js', 'lab-play.js']
        named = r'Open Sans|Gentium Book Plus|\bJost\b|DM Sans|Newsreader'
        for name in files:
            with self.subTest(file=name):
                text = (ROOT / name).read_text()
                text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
                self.assertNotRegex(text, named)
                self.assertNotIn('fonts.googleapis.com', text)
                self.assertNotIn('fonts.gstatic.com', text)
                self.assertNotRegex(text, r'--font-(?:reading|editorial|interface)\s*:')
        tokens = (ROOT / 'assets/typography.css').read_text()
        for role in ('reading', 'editorial', 'interface'):
            self.assertRegex(tokens, r'--font-' + role + r'\s*:')
        for scale in ('body', 'caption', 'small', 'title', 'section', 'card'):
            self.assertRegex(tokens, r'--type-' + scale + r'\s*:')

    def test_pages_packaging_includes_the_shared_style_and_fonts(self):
        workflow = (ROOT / '.github/workflows/publish.yml').read_text()
        packaging = workflow.split('name: Prepare static website', 1)[1]
        self.assertIn('assets/typography.css', packaging)
        self.assertRegex(packaging, r'cp\s+-R\s+assets/fonts\s+_site/assets/')


if __name__ == '__main__':
    unittest.main()

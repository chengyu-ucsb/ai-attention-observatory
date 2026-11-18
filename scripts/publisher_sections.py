"""Bounded publisher excerpts, with heading ancestry and explicit coverage gaps.

This is deliberately not a full-document or table-data extractor. Unknown
peer headings end a recognized section; unknown descendants inherit only the
nearest recognized ancestor. Ambiguous combined Results/Discussion stays in
interpretation, never in observed results.
"""
from html.parser import HTMLParser
import re

SECTION_LIMIT = 6700
NAMES = {
    'materials and methods': 'methods', 'methodology': 'methods',
    'method': 'methods', 'methods': 'methods',
    'result': 'results', 'results': 'results', 'findings': 'results',
    'path results': 'results', 'research results': 'results',
    'discussion': 'discussion', 'conclusion': 'discussion',
    'conclusions': 'discussion', 'results and discussion': 'discussion',
    'results & discussion': 'discussion', 'discussion and conclusions': 'discussion',
    'limitations': 'limitations', 'study limitations': 'limitations',
    'limitations of the study': 'limitations',
}
STOP = {'references', 'bibliography', 'statements', 'declarations',
        'data availability', 'data availability statement', 'ethics statement',
        'author contributions', 'funding', 'conflict of interest',
        'conflicts of interest', 'acknowledgments', 'acknowledgements',
        'generative ai statement', "publisher’s note", "publisher's note"}
# These are not empirical results even when nested within a Results section.
EXCLUDE = {'results of previous studies', 'previous research results',
           'suggestions for further research', 'future research', 'future directions',
           'hypotheses', 'hypothesis development', 'hypotheses development',
           'literature review', 'literature review and hypotheses development'}


def clean(text):
    return ' '.join(str(text or '').split())


def section_name(raw):
    title = re.sub(r'^\s*\d+(?:\.\d+)*[.\s]*', '', clean(raw)).strip(' :.').lower()
    if title in STOP:
        return 'stop'
    if title in EXCLUDE:
        return 'exclude'
    return NAMES.get(title, '')


def xml_sections(root, section_tag, title_tag, max_chars):
    """Read disjoint body paragraphs in order, inheriting nested section headings."""
    buckets = {}

    def local(element):
        return element.tag.rsplit('}', 1)[-1].lower()

    def words(element):
        return clean(' '.join(element.itertext()))

    def collect(element, inherited=''):
        tag = local(element)
        if tag in {'back', 'ref-list', 'listbibl', 'table', 'table-wrap', 'figure', 'fig',
                   'caption', 'supplementary-material', 'fn-group'}:
            return
        key = inherited
        if tag == section_tag:
            title = next((words(child) for child in element if local(child) == title_tag), '')
            name = section_name(title)
            if not name:
                prefix = re.sub(r'^\s*\d+(?:\.\d+)*[.\s]*', '', title).casefold()
                name = section_name(prefix.split(':', 1)[0])
                if not name and prefix in {'study design', 'participants', 'procedure', 'data collection', 'statistical analysis'}:
                    name = 'methods'
            if name in ('stop', 'exclude'):
                return
            if inherited == 'discussion' and name == 'results':
                name = 'discussion'
            key = name or inherited
        if tag == 'p':
            value = words(element)
            if key and len(value) >= 45:
                buckets.setdefault(key, []).append(value)
            return
        for child in element:
            if local(child) != title_tag:
                collect(child, key)

    body = next((element for element in root.iter() if local(element) == 'body'), None)
    if body is not None:
        collect(body)
    return {key: ' '.join(paragraphs)[:max_chars].rstrip() for key, paragraphs in buckets.items()}


class ArticleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocked = 0
        self.heading = None
        self.paragraph = None
        self.stack = []
        self.stopped = False
        self.table_depth = 0
        self.secs = {}
        self.coverage = {
            'scope': 'bounded_section_excerpts', 'full_document': False,
            'section_character_limit': SECTION_LIMIT, 'truncated_sections': [],
            'encountered_section_headings': {}, 'tables_omitted_by_section': {},
            'table_policy': 'Table cells are not extracted; prose may mention tables. Consult original source.',
        }

    @property
    def active(self):
        if self.stopped or any(key == 'exclude' for _, _, key in self.stack):
            return ''
        for _, _, key in reversed(self.stack):
            if key:
                # A Results subheading inside author interpretation cannot
                # establish a separate observed-findings section.
                if key == 'results' and any(k == 'discussion' for _, _, k in self.stack):
                    return 'discussion'
                return key
        return ''

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'footer', 'aside'):
            self.blocked += 1
        if self.blocked:
            return
        if re.fullmatch(r'h[1-6]', tag) and self.heading is None:
            self.heading = [int(tag[1]), []]
        if tag == 'table':
            if not self.table_depth and self.active:
                counts = self.coverage['tables_omitted_by_section']
                counts[self.active] = counts.get(self.active, 0) + 1
            self.table_depth += 1
        if tag == 'p' and self.paragraph is None and not self.table_depth:
            self.paragraph = []

    def handle_data(self, data):
        if self.blocked:
            return
        if self.heading is not None:
            self.heading[1].append(data)
        if self.paragraph is not None and not self.table_depth:
            self.paragraph.append(data)

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'footer', 'aside'):
            self.blocked = max(0, self.blocked - 1)
            return
        if self.blocked:
            return
        if tag == 'table':
            self.table_depth = max(0, self.table_depth - 1)
        if self.heading is not None and tag == 'h' + str(self.heading[0]):
            level, parts = self.heading
            title = clean(' '.join(parts))
            key = section_name(title)
            self.heading = None
            while self.stack and self.stack[-1][0] >= level:
                self.stack.pop()
            self.stack.append((level, title, key))
            if key == 'stop':
                self.stopped = True
        if tag == 'p' and self.paragraph is not None:
            value = clean(' '.join(self.paragraph))
            self.paragraph = None
            key = self.active
            if not key or len(value) < 45 or self.table_depth:
                return
            paths = self.coverage['encountered_section_headings'].setdefault(key, [])
            path = ' > '.join(title for _, title, _ in self.stack)
            if path not in paths:
                paths.append(path)
            joined = self.secs.get(key, '')
            candidate = (joined + ' ' + value).strip()
            self.secs[key] = candidate[:SECTION_LIMIT]
            if len(candidate) > SECTION_LIMIT and key not in self.coverage['truncated_sections']:
                self.coverage['truncated_sections'].append(key)

"""Conservative article-body blocks, kept in memory and never completeness proof.

Prefer explicit publisher body containers within the primary full article. Keep
list items and short headings; exclude hidden UI and known related-story cards.
The parser does not execute HTML, follow links, or read image/source resources.
"""
from dataclasses import dataclass, field
from html.parser import HTMLParser
import re

# Bump when body selection changes; queue provenance must not reset discovery.
EXTRACTION_VERSION = 'article-body-v3'

VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
BLOCKED = {'script','style','nav','footer','aside','form','noscript','svg','template','button','select','textarea'}
TEXT_BLOCKS = {'p','li','dt','dd','blockquote','figcaption','h1','h2','h3','h4','h5','h6','pre'}
CONTAINERS = {'div','section','article','main','ul','ol','dl'}
BODY_CLASSES = {'entry-content','article-body','article__body','post-content','post__content',
                'field-name-body','field--name-body'}
EXCLUDED_CLASSES = {'related-content','related-posts','related-articles','related-stories',
    'related-items','related-article','related-story','view-related-content',
    'field--name-field-related-content','pane-blog-related-content-panel-pane-1',
    'view-blog-related-content','node-teaser','node--teaser','node--view-mode-teaser','node--view-mode-card',
    'share-links','social-share','newsletter-signup','subscription-prompt','comments',
    'comment-list','cookie-banner','advertisement'}

@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: object = None


def classes(node):
    return set((node.attrs.get('class') or '').lower().split())


def ignored(node):
    attrs=node.attrs
    style=re.sub(r'\s+','',attrs.get('style') or '').lower()
    return (node.tag in BLOCKED or 'hidden' in attrs or
            str(attrs.get('aria-hidden','')).lower()=='true' or
            attrs.get('role') in {'navigation','contentinfo','complementary'} or
            bool(classes(node) & EXCLUDED_CLASSES) or
            (attrs.get('id') or '').lower() in EXCLUDED_CLASSES or
            'display:none' in style or 'visibility:hidden' in style)


def visible_nodes(node):
    if ignored(node): return
    yield node
    for child in node.children:
        if isinstance(child,Node): yield from visible_nodes(child)


def body_container(node):
    return 'articleBody' in (node.attrs.get('itemprop') or '').split() or bool(classes(node)&BODY_CLASSES)


def section_role(headings, default='body'):
    """Use explicit section titles as context, never as proof of a finding."""
    from publisher_sections import section_name
    role = default
    for heading in headings:
        title = re.sub(r'^\s*\d+(?:\.\d+)*[.\s]*', '', heading).strip(' :.').casefold()
        if role in {'references', 'metadata', 'prior_work', 'hypotheses'}:
            continue
        if title in {'references', 'bibliography', 'literature cited', 'works cited'}:
            role = 'references'
        elif title in {'literature review', 'related work', 'background', 'previous studies',
                       'prior work', 'results of previous studies'}:
            role = 'prior_work'
        elif re.match(r'^(?:research )?hypothes(?:is|es)\b', title):
            role = 'hypotheses'
        elif title in {'abstract', 'structured abstract'}:
            role = 'abstract'
        else:
            category = section_name(title)
            if category in {'methods', 'results', 'discussion', 'limitations'}:
                role = 'discussion' if role == 'discussion' and category == 'results' else category
            elif category == 'stop':
                role = 'metadata'
    return role


def table_rows(rows, ambiguous=False):
    """Expose only explicit, rectangular column associations; keep other rows as text."""
    headers = [index for index, (is_header, _, _) in enumerate(rows) if is_header]
    columns = rows[0][1] if headers == [0] else []
    aligned = (not ambiguous and len(columns) >= 2 and
               all(name.strip() for name in columns[1:]) and
               len(set(columns)) == len(columns) and
               all(not merged and len(cells) == len(columns) for _, cells, merged in rows))
    blocks = []
    for is_header, cells, _ in rows:
        text = ' | '.join(cells)
        role = 'table_header' if is_header else 'table_row' if aligned else 'table_unaligned'
        block = {'text': text, 'role': role}
        if role == 'table_row':
            block['columns'] = list(columns)
        blocks.append(block)
    return blocks


def table_elements(node, tags):
    """Walk this table in order, stopping before nested rows/tables."""
    for child in node.children:
        if not isinstance(child, Node) or ignored(child):
            continue
        if child.tag in tags:
            yield child
        elif child.tag != 'table':
            yield from table_elements(child, tags)


def cell_text(node):
    parts = []
    def visit(item):
        if isinstance(item, str):
            parts.append(item)
        elif not ignored(item):
            block = item.tag in TEXT_BLOCKS | CONTAINERS | {'br', 'td', 'th', 'tr'}
            if block:
                parts.append(' ')
            for child in item.children:
                visit(child)
            if block:
                parts.append(' ')
    visit(node)
    return ' '.join(''.join(parts).split())


class ArticleParser(HTMLParser):
    """Use paragraph-compatible output for both article retrieval paths."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root=Node('document'); self.stack=[self.root]; self.node_count=0
        self.selection='no_article_container'
        self.blocks=[]
        self.list_items_found=0
        self.headings=[]

    def handle_starttag(self,tag,attrs):
        self.node_count+=1
        if self.node_count>100000: raise ValueError('html_node_budget_exceeded')
        if len(self.stack)>256: raise ValueError('html_nesting_budget_exceeded')
        # Common optional closes. In particular, void tags must never consume
        # the later article body or keep a hidden container active forever.
        if tag in {'p','li','dt','dd'} and self.stack[-1].tag == tag:
            self.stack.pop()
        if tag in {'tr','th','td'}:
            for index in range(len(self.stack)-1, 0, -1):
                prior = self.stack[index].tag
                if prior == 'table' or (prior == 'tr' and tag != 'tr'):
                    break
                if (tag == 'tr' and prior == 'tr') or (tag in {'td','th'} and prior in {'td','th'}):
                    del self.stack[index:]
                    break
        node=Node(tag,dict(attrs),parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID: self.stack.append(node)

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)

    def handle_endtag(self,tag):
        if tag in VOID:return
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:
                del self.stack[i:];return

    def handle_data(self,data):
        self.stack[-1].children.append(data)

    def _roots(self):
        nodes=list(visible_nodes(self.root))
        full=[n for n in nodes if n.tag=='article' and
              classes(n)&{'node--view-mode-full','node--full','post-full','article-full'}]
        articles=[n for n in nodes if n.tag=='article']
        mains=[n for n in nodes if n.tag=='main']
        # Multiple full primary articles are ambiguous; never choose by length.
        if len(full)>1:self.selection='ambiguous_primary_articles';return []
        if not full and len(articles)>1:
            self.selection='ambiguous_primary_articles';return []
        if full:outer=full[0];self.selection='full_article'
        elif len(articles)==1:outer=articles[0];self.selection='article'
        elif len(mains)==1:outer=mains[0];self.selection='main'
        else:self.selection='no_unique_article_container';return []
        bodies=[n for n in visible_nodes(outer) if body_container(n)]
        # Nested body markers are the same body, not duplicated content.
        roots=[]; selected=set()
        for node in bodies:
            parent=node.parent
            while parent is not None and parent not in selected:parent=parent.parent
            if parent is None:roots.append(node);selected.add(node)
        if roots:
            self.selection+=':explicit_body'
            return roots
        return [outer]

    def article_blocks(self):
        self.blocks=[]
        self.headings=[]
        roots=self._roots()
        self.list_items_found=sum(n.tag=='li' for root in roots for n in visible_nodes(root))
        for root in roots:self._extract(root)
        return self.blocks

    @property
    def paragraphs(self):
        return [block['text'] for block in self.article_blocks()]

    def _append(self, kind, text, *, role=None, columns=None):
        if kind in {'h1','h2','h3','h4','h5','h6'}:
            level = int(kind[1])
            while self.headings and self.headings[-1][0] >= level:
                self.headings.pop()
            self.headings.append((level, text))
            role = 'heading'
        path = [title for _, title in self.headings]
        block = {'kind': kind, 'text': text, 'headings': path,
                 'role': role or ('caption' if kind == 'figcaption' else section_role(path))}
        if columns:
            block['columns'] = columns
        self.blocks.append(block)

    def _table(self, node):
        elements = list(table_elements(node, {'tr', 'caption'}))
        rows = []
        for row in (item for item in elements if item.tag == 'tr'):
            cells = list(table_elements(row, {'td', 'th'}))
            header = bool(cells) and all(cell.tag == 'th' for cell in cells)
            merged = any(str(cell.attrs.get(key, '1')) != '1'
                         for cell in cells for key in ('rowspan', 'colspan'))
            rows.append((header, [cell_text(cell) for cell in cells], merged))
        nested = any(child.tag == 'table' and child is not node for child in visible_nodes(node))
        blocks = iter(table_rows(rows, ambiguous=nested))
        for item in elements:
            if item.tag == 'caption':
                caption = cell_text(item)
                if caption:
                    self._append('caption', caption, role='caption')
                continue
            block = next(blocks)
            if block['text'].strip(' |'):
                self._append('tr', **block)

    def _extract(self,node,kind='p'):
        if ignored(node):return
        kind=node.tag if node.tag in TEXT_BLOCKS else kind
        pending=[]
        def flush():
            text=' '.join(''.join(pending).split());pending.clear()
            if len(text)<3:return
            if re.search(r'^(?:sign up|subscribe|all rights reserved|read more|advertisement)\b',text,re.I):return
            self._append(kind, text)
        def visit(child):
            if isinstance(child,str):pending.append(child);return
            if ignored(child):return
            if child.tag=='br':pending.append('\n');return
            if child.tag=='table':
                flush();self._table(child);return
            if child.tag in TEXT_BLOCKS|CONTAINERS:
                flush();self._extract(child,kind)
            else:
                for inner in child.children:visit(inner)
        for child in node.children:visit(child)
        flush()

"""Conservative article-body blocks, kept in memory and never completeness proof.

Prefer explicit publisher body containers within the primary full article. Keep
list items and short headings; exclude hidden UI and known related-story cards.
The parser does not execute HTML, follow links, or read image/source resources.
"""
from dataclasses import dataclass, field
from html.parser import HTMLParser
import re

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


class ArticleParser(HTMLParser):
    """Use paragraph-compatible output for both article retrieval paths."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root=Node('document'); self.stack=[self.root]; self.node_count=0
        self.selection='no_article_container'
        self.blocks=[]
        self.list_items_found=0

    def handle_starttag(self,tag,attrs):
        self.node_count+=1
        if self.node_count>100000: raise ValueError('html_node_budget_exceeded')
        if len(self.stack)>256: raise ValueError('html_nesting_budget_exceeded')
        # Common optional closes. In particular, void tags must never consume
        # the later article body or keep a hidden container active forever.
        if tag in {'p','li','dt','dd'} and self.stack[-1].tag==tag:
            self.stack.pop()
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

    @property
    def paragraphs(self):
        self.blocks=[]
        roots=self._roots()
        self.list_items_found=sum(n.tag=='li' for root in roots for n in visible_nodes(root))
        for root in roots:self._extract(root)
        return [block['text'] for block in self.blocks]

    def _extract(self,node,kind='p'):
        if ignored(node):return
        kind=node.tag if node.tag in TEXT_BLOCKS else kind
        pending=[]
        def flush():
            text=' '.join(''.join(pending).split());pending.clear()
            if len(text)<3:return
            if re.search(r'^(?:sign up|subscribe|all rights reserved|read more|advertisement)\b',text,re.I):return
            self.blocks.append({'kind':kind,'text':text})
        def visit(child):
            if isinstance(child,str):pending.append(child);return
            if ignored(child):return
            if child.tag=='br':pending.append('\n');return
            if child.tag in TEXT_BLOCKS|CONTAINERS:
                flush();self._extract(child,kind)
            else:
                for inner in child.children:visit(inner)
        for child in node.children:visit(child)
        flush()

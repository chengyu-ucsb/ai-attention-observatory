"""Synthetic page structure only; no publisher article prose is persisted."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from article_body_parser import ArticleParser
from full_document_access import document_from_html


def parse(html):
    p=ArticleParser();p.feed(html);return p,p.paragraphs


class BodyTests(unittest.TestCase):
    def test_drupal_full_body_not_ten_teasers_with_same_body_class(self):
        body='<div class="field field--name-body"><p>Main source introduction.</p><ol>'+''.join(f'<li>Recommendation {n} with required context.</li>' for n in range(10))+'</ol><p>End qualification.</p></div>'
        teaser='<article class="node-teaser node--teaser"><div class="field field--name-body"><p>Other story cannot be evidence.</p></div></article>'
        p,paragraphs=parse('<main><article class="node node--full">'+body+'</article><div class="view-blog-related-content">'+teaser*10+'</div></main>')
        self.assertEqual(p.selection,'full_article:explicit_body')
        self.assertEqual(len(paragraphs),12)
        self.assertEqual(sum(b['kind']=='li' for b in p.blocks),10)
        self.assertNotIn('Other story',' '.join(paragraphs))

    def test_nested_body_markers_do_not_duplicate(self):
        _,p=parse('<article><div itemprop="articleBody"><div class="entry-content"><p>Keep this paragraph once.</p></div></div></article>')
        self.assertEqual(p,['Keep this paragraph once.'])

    def test_lists_with_paragraphs_nested_lists_and_trailing_text(self):
        _,p=parse('<article><ul><li>Outer advice.<p>Elaborated reason.</p><ul><li>Nested caution.</li></ul>Final qualification.</li></ul></article>')
        self.assertEqual(p,['Outer advice.','Elaborated reason.','Nested caution.','Final qualification.'])

    def test_list_item_count_is_not_a_count_of_unwrapped_text_fragments(self):
        parser,p=parse('<article><ul><li><p>One reason.</p><p>One caveat.</p></li></ul></article>')
        self.assertEqual(parser.list_items_found,1)
        self.assertEqual(p,['One reason.','One caveat.'])

    def test_many_body_siblings_are_selected_without_duplicate_blocks(self):
        parser,p=parse('<article>'+'<div class="entry-content"><p>One bounded body block.</p></div>'*2000+'</article>')
        self.assertEqual(len(p),2000)

    def test_short_h4_and_inline_text_and_void_tags_are_preserved(self):
        _,p=parse('<main><h4>Family plans</h4><p>Use <b>context</b>, then act.<br>Next line.</p><ul><li>Keep appeals.</li></ul><img src="never-requested"><p>Last paragraph.</p></main>')
        self.assertEqual(p,['Family plans','Use context, then act. Next line.','Keep appeals.','Last paragraph.'])

    def test_blocked_hidden_promo_and_ui_are_omitted(self):
        blocked=''.join(f'<div {a}><p>Never keep this.</p></div>' for a in ('hidden','aria-hidden="true"','style="display: none"','style="visibility: hidden"','class="related-posts"','role="navigation"'))
        _,p=parse('<main>'+blocked+'<nav><p>Never keep navigation.</p></nav><script>Never execute</script><p>Keep actual source prose.</p></main>')
        self.assertEqual(p,['Keep actual source prose.'])

    def test_optional_list_closes(self):
        _,p=parse('<main><ol><li>First recommendation.<li>Second recommendation.</ol></main>')
        self.assertEqual(p,['First recommendation.','Second recommendation.'])

    def test_multiple_full_articles_fail_closed(self):
        parser,p=parse('<main><article class="node--full"><p>First article.</p></article><article class="node--full"><p>Second article.</p></article></main>')
        self.assertEqual(p,[]);self.assertEqual(parser.selection,'ambiguous_primary_articles')

    def test_plain_article_siblings_cannot_be_merged_as_one_source(self):
        parser,p=parse('<main><article><div class="entry-content"><p>First source.</p></div></article><article><div class="entry-content"><p>Second source.</p></div></article></main>')
        self.assertEqual(p,[]);self.assertEqual(parser.selection,'ambiguous_primary_articles')

    def test_no_article_or_main_does_not_turn_entire_webpage_into_evidence(self):
        _,p=parse('<html><body><p>Only arbitrary website chrome.</p></body></html>')
        self.assertEqual(p,[])

    def test_nesting_budget_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'nesting_budget'):
            parse('<main>'+'<div>'*260)

    def test_full_document_path_keeps_partial_status_and_no_source_prose_in_manifest(self):
        title='A synthetic article on attention and agency'
        prose='This synthetic example describes a claim with its explanation and qualification. '
        html='<head><title>'+title+'</title></head><main><article class="node--full"><div class="field--name-body">'+''.join('<p>'+prose*4+'</p>' for _ in range(8))+'<ol><li>Preserve this recommendation.</li></ol></div></article></main>'
        doc=document_from_html(html.encode(),{'title':title},'https://www.eff.org/example')
        self.assertEqual(doc.coverage['evidence_status'],'partial_full_text')
        self.assertEqual(doc.coverage['html_completeness'],'not_verified')
        self.assertEqual(doc.coverage['html_list_items_found'],1)
        self.assertIn('Preserve this recommendation.',[u['text'] for u in doc.units])
        self.assertNotIn(prose,str(doc.manifest()))

if __name__=='__main__':unittest.main()

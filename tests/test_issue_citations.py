"""Exact source spans stay linked, escaped, and accessible on web and RSS."""
import copy
import pathlib
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import build_issue as bi
import build_newsletter as bn


def fixture():
    section={'title':'Compare','text':'Alpha & <study> found a gap. Beta found uncertainty.',
             'sources':['Alpha paper','Beta paper'],'source_ids':['a','b'],
             'citations':[{'text':'Alpha & <study>','source':'Alpha paper'},
                          {'text':'Beta','source':'Beta paper'}]}
    return {'citation_schema_version':1,'status':'published','edition_date':'2026-11-02',
            'number':1,'subject':'Issue','headline':'Findings','deck':'A gap','letter':'Opening',
            'closer':'Keep checking','editorial_note':'Scope','signals':[section],
            'tension':copy.deepcopy(section),'experiment':{'title':'Try','text':'Test uncertainty.'},
            'sources':[{'id':'a','title':'Alpha paper','url':'https://example.org/alpha',
                        'source_url':'https://example.org/read.pdf?version=2'},
                       {'id':'b','title':'Beta paper','url':'https://example.org/beta'}],
            'glossary':[{'term':'uncertainty','definition':'What we do not yet know.'}]}


class CitationTests(unittest.TestCase):
    def test_archive_correction_requires_date_and_current_source_approval(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        import json
        with self.assertRaisesRegex(ValueError,'explicit edition date'):
            bi.build(use_published_sources=True)
        with TemporaryDirectory() as tmp:
            data=Path(tmp);(data/'approved-issues').mkdir()
            (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-11-07'},'items':[]}))
            (data/'issue-editorial.json').write_text('{}')
            archived={'status':'published','sources':[{'id':'a','title':'Previously approved source'}]}
            (data/'approved-issues/2026-11-07.json').write_text(json.dumps(archived))
            with patch.object(bi,'DATA',data),patch.object(bi,'resolve_queued_original',side_effect=ValueError('Source approval revoked')) as check:
                with self.assertRaisesRegex(ValueError,'Source approval revoked'):
                    bi.build('2026-11-07',use_published_sources=True)
                check.assert_called_once()
            self.assertFalse((data/'public-issue.json').exists())
            archived['status']='awaiting_publication'
            (data/'approved-issues/2026-11-07.json').write_text(json.dumps(archived))
            with patch.object(bi,'DATA',data),self.assertRaisesRegex(ValueError,'existing published edition'):
                bi.build('2026-11-07',use_published_sources=True)

    def test_multiple_exact_sources_and_fallback(self):
        issue=bi.validate_issue_citations(fixture())
        self.assertEqual([c['source_id'] for c in issue['signals'][0]['citations']],['a','b'])
        rendered=bn.render_issue(issue)
        self.assertIn('href="https://example.org/read.pdf?version=2"',rendered)
        self.assertIn('>Alpha &amp; &lt;study&gt;</a>',rendered)
        self.assertIn('href="https://example.org/beta"',rendered)
        self.assertNotIn('Reading 1',rendered)
        self.assertIn('>Alpha paper</a>',rendered)

    def test_invalid_citations(self):
        for phrase in ('', 'not there', 'found'):
            with self.subTest(phrase=phrase):
                i=fixture();i['signals'][0]['citations'][0]['text']=phrase
                with self.assertRaises(ValueError):bi.validate_issue_citations(i)
        for entries in ([],None,[{'text':'Alpha','source':'Alpha paper'},{'text':'Alpha & <study>','source':'Alpha paper'}],
                        [{'text':'Alpha','source':'Missing paper'}]):
            with self.subTest(entries=entries):
                i=fixture();i['signals'][0]['citations']=entries
                with self.assertRaises(ValueError):bi.validate_issue_citations(i)
        i=fixture();del i['signals'][0]['citations']
        with self.assertRaises(ValueError):bi.validate_issue_citations(i)
        i=fixture();i['sources'].append(copy.deepcopy(i['sources'][0]))
        with self.assertRaises(ValueError):bi.validate_issue_citations(i)

    def test_unsafe_urls_and_fallback(self):
        for url in ('javascript:alert(1)','https://bad host/x','https://user:password@example.org','https://[broken'):
            i=fixture();i['sources'][0]['source_url']=url
            self.assertEqual(bi.citation_url(i['sources'][0]),'https://example.org/alpha')
            i['sources'][0]['url']=url
            with self.assertRaises(ValueError):bi.validate_issue_citations(i)

    def test_preview_boundary_and_paragraphs(self):
        i=fixture();section=i['signals'][0]
        section['text']='Alpha & <study>. Beta found uncertainty.\n\n'+'Remaining details. '*30
        section['citations']=[{'text':'Alpha & <study>. Beta','source':'Alpha paper'},
                              {'text':'Remaining details. '*30,'source':'Beta paper'}]
        rendered=bn.long_copy(section['text'],issue=i,section=section)
        preview=rendered.split('<details>')[0]
        self.assertIn('>Alpha &amp; &lt;study&gt;. Beta</a>',preview)
        self.assertEqual(rendered.count('<p'),3)
        self.assertNotIn('<study>',rendered)

    def test_legacy_without_citations(self):
        i=fixture();del i['citation_schema_version']
        for s in i['signals']+[i['tension']]:del s['citations']
        self.assertIn('Alpha &amp; &lt;study&gt;',bn.render_issue(i))
        self.assertIn('Alpha paper',bn.rss_content(i))

    def test_glossary_and_citation_priority(self):
        i=fixture();i['glossary'].append({'term':'Alpha','definition':'A named source.'})
        rendered=bn.render_issue(i)
        self.assertIn('class="glossary-term" href="#term-uncertainty-1"',rendered)
        self.assertIn('<dt id="term-uncertainty-1" tabindex="-1">',rendered)
        self.assertNotIn('href="#term-alpha-2"',rendered)
        self.assertIn('What we do not yet know.',bn.rss_content(i))

    def test_rss_and_pdf_locator(self):
        i=fixture();i['signals'][0]['citations'][0].update(page=6,locator='§4.4, pp. 6–8')
        with tempfile.TemporaryDirectory() as folder,patch.object(bn,'ROOT',pathlib.Path(folder)):
            bn.build_rss([i]);root=ET.parse(pathlib.Path(folder)/'issue-feed.xml')
        body=root.find('./channel/item/{'+bn.CONTENT+'}encoded').text
        self.assertIn('href="https://example.org/read.pdf?version=2#page=6"',body)
        self.assertIn('§4.4, pp. 6–8',body)
        self.assertIn('>Alpha &amp; &lt;study&gt;</a>',body)

    def test_validation_precedes_archive_replacement(self):
        i=fixture();i['signals'][0]['citations']=[]
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder);(path/'public-issue.json').write_text(__import__('json').dumps(i))
            (path/'approved-issues').mkdir();archive=path/'approved-issues/2026-11-02.json';archive.write_text('previous')
            with patch.object(bn,'DATA',path),self.assertRaises(ValueError):bn.build()
            self.assertEqual(archive.read_text(),'previous')

if __name__=='__main__':unittest.main()

"""Publication safety at the automatic edition boundary."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compose_issue as composer
from build_newsletter import rss_content


class CompositionTests(unittest.TestCase):
    def fixture(self):
        passage = ('The classroom comparison followed students using different forms of support. '
                   'Researchers reported changes in engagement but did not establish lasting independent learning. '
                   'The limited sample and short observation period constrain conclusions about transfer across contexts.')
        packet = [{'key': f'S{i}', 'title': f'Source {i}', 'id': str(i), 'evidence': passage} for i in range(1, 5)]
        paragraph = ('A useful distinction runs through these readings: the quality of work completed with assistance '
                     'can differ from the ability a learner retains afterwards. These accounts invite closer examination '
                     'of the decisions students continue to make themselves. Their different settings and methods '
                     'also make direct comparisons difficult. Taken together, they frame a question about evaluation '
                     'rather than establish a shared causal effect. Future studies could separate immediate task success '
                     'from later performance on a comparable task completed independently, while observing how participants '
                     'check suggestions and revise their own explanations.')
        section = lambda a,b: dict(short='A theme', title='Assistance and learning', text=paragraph,
            evidence=[{'key':a,'quote':'did not establish lasting independent learning'},
                      {'key':b,'quote':'limited sample and short observation period'}])
        draft = dict(headline='What remains when the assistance ends?', deck=' '.join(paragraph.split()[:30]),
                     letter=paragraph, closer='The research question is which forms of assistance leave independent judgment stronger.',
                     signals=[section('S1','S2'),section('S2','S3'),section('S3','S4')], tension=section('S1','S4'))
        return draft, packet

    def test_valid_citations_resolve_but_foreign_sources_and_statistics_fail(self):
        draft, packet = self.fixture()
        result = composer.validate(copy.deepcopy(draft), packet)
        self.assertEqual(result['signals'][0]['sources'], ['Source 1','Source 2'])
        for corrupt in ('foreign', 'quote', 'number'):
            bad = copy.deepcopy(draft)
            if corrupt == 'foreign': bad['signals'][0]['evidence'][0]['key']='S99'
            if corrupt == 'quote': bad['signals'][0]['evidence'][0]['quote']='invented words that never appeared anywhere'
            if corrupt == 'number': bad['signals'][0]['text'] += ' Scores improved by 47 percent.'
            with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                composer.validate(bad, packet)

    def test_preview_and_citation_only_records_are_not_evidence(self):
        items=[{'title':'Feed preview','url':'https://example.org/1','reading':{'level':'curated','overview':'x '*100}},
               {'title':'Metadata','url':'https://example.org/2','reading':{'level':'citation_only','findings':'x '*100}}]
        self.assertEqual(composer.evidence(items), [])

    def test_failure_never_overwrites_published_copy_and_existing_week_is_idempotent(self):
        _, packet = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); data=root/'data'; data.mkdir()
            items=[{'title':p['title'],'url':'https://example.org/'+p['id'],
                    'reading':{'level':'abstract','findings':p['evidence']}} for p in packet]
            (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-10-26'},'items':items}),encoding='utf-8')
            path=data/'issue-editorial.json'
            original=json.dumps({'2026-10-18':{'headline':'Previously published'}})
            path.write_text(original,encoding='utf-8')
            fake=Mock()
            fake.create_chat_completion.return_value={'choices':[{'message':{'content':'{}'}}]}
            with self.assertRaises(ValueError): composer.compose(root,fake)
            self.assertEqual(path.read_text(encoding='utf-8'),original)
            self.assertEqual(fake.create_chat_completion.call_count,2)
            audit=json.loads((data/'edition-audits/2026-10-26.json').read_text(encoding='utf-8'))
            self.assertEqual(audit['status'],'failed_validation')
            path.write_text(json.dumps({'2026-10-26':{'headline':'Already published'}}),encoding='utf-8')
            fake.reset_mock()
            self.assertFalse(composer.compose(root,fake))
            fake.create_chat_completion.assert_not_called()

    def test_rss_delivers_the_same_edition_copy_and_citations(self):
        issue={'headline':'Canonical & safe', 'letter':'The website opening.',
               'signals':[{'title':'A theme','text':'A published claim.','source_ids':['source']}],
               'sources':[{'id':'source','title':'Original','url':'https://example.org/paper'}],
               'editorial_note':'Automatically synthesized; limited evidence.'}
        html=rss_content(issue)
        for content in ('Canonical &amp; safe','The website opening.','A published claim.',
                        'https://example.org/paper','Automatically synthesized'):
            self.assertIn(content,html)


if __name__=='__main__': unittest.main()

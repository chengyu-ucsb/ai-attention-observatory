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
from build_newsletter import rss_content, json_feed


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
               {'title':'Metadata','url':'https://example.org/2','reading':{'level':'citation_only','findings':'x '*100}},
               {'title':'Design only','url':'https://example.org/3','reading':{'level':'abstract','methods':'x '*100}}]
        self.assertEqual(composer.evidence(items), [])

    def test_long_results_do_not_displace_design_or_limitations(self):
        item={'title':'A study','url':'https://example.org/study','reading':{'level':'full_text',
              'findings':'Reported result. '*300,'methods':'Nonrandom classroom allocation.',
              'interpretation':'An author interpretation. '*100,
              'limitations':'Class-level confounding prevents a causal conclusion.'}}
        packet=composer.evidence([item])[0]['evidence']
        self.assertIn('Nonrandom classroom allocation.',packet)
        self.assertIn('Class-level confounding prevents a causal conclusion.',packet)

    def test_each_comparison_receives_only_its_own_source_pair(self):
        draft,packet=self.fixture()
        for p in packet: p.update(kind='scholarly',level='abstract',research_type='observational')
        pairs=[['S1','S2'],['S2','S3'],['S3','S4']]
        plan={'themes':[{'short':'A theme','title':'Assistance and independent learning','keys':pair} for pair in pairs]}
        frame={k:copy.deepcopy(v) for k,v in draft.items() if k!='signals'}
        frame['tension'].pop('evidence')
        bad=copy.deepcopy(draft['signals'][0])
        bad['evidence'][0]['quote']='unsupported anchor words from another source'
        replies=[plan,bad]+draft['signals']+[frame]
        model=Mock()
        model.create_chat_completion.side_effect=[{'choices':[{'message':{'content':json.dumps(x)}}]} for x in replies]
        result=composer.draft_in_stages(model,packet,{})
        self.assertEqual(len(result['signals']),3)
        first=model.create_chat_completion.call_args_list[1].kwargs['messages'][1]['content']
        self.assertIn('Source 1',first)
        self.assertIn('Source 2',first)
        self.assertNotIn('Source 3',first)
        repair=model.create_chat_completion.call_args_list[2].kwargs['messages']
        self.assertEqual(repair[2]['role'],'assistant')
        self.assertEqual(json.loads(repair[2]['content'])['text'],bad['text'])
        self.assertIn('Preserve the substantive prose',repair[3]['content'])

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
            self.assertEqual(fake.create_chat_completion.call_count,3)
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


    def test_json_delivery_preserves_rss_identity_and_exact_content(self):
        issue={'edition_date':'2026-10-26','status':'published','subject':'Weekly edition',
               'headline':'Canonical title','letter':'Published opening','sources':[]}
        items=json_feed([issue,dict(issue,status='awaiting_publication')])['items']
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['id'],items[0]['url'])
        self.assertTrue(items[0]['id'].endswith('/issues/2026-10-26.html'))
        self.assertEqual(items[0]['content_html'],rss_content(issue))
        self.assertEqual(items[0]['_observatory'],issue)


if __name__=='__main__': unittest.main()

"""Publication safety at the automatic edition boundary."""
import copy
from datetime import date
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
        packet = [{'key': f'S{i}', 'title': f'Source {i}', 'id': str(i), 'url': f'https://example.org/source-{i}', 'evidence': passage + ' Source labels: 1 2 3 4.'} for i in range(1, 5)]
        paragraph = ('A useful distinction runs through these readings: the quality of work completed with assistance '
                     'can differ from the ability a learner retains afterwards. These accounts invite closer examination '
                     'of the decisions students continue to make themselves. Their different settings and methods '
                     'also make direct comparisons difficult. Taken together, they frame a question about evaluation '
                     'rather than establish a shared causal effect. Future studies could separate immediate task success '
                     'from later performance on a comparable task completed independently, while observing how participants '
                     'check suggestions and revise their own explanations. These abstract-based accounts require full-text confirmation.')
        section = lambda a,b: dict(short='A theme', title='Assistance and learning', text=f'Source {a[1:]} and Source {b[1:]} address this question. '+paragraph,
            citations=[{'key':a,'text':f'Source {a[1:]}'},{'key':b,'text':f'Source {b[1:]}'}],
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
        self.assertIn('Keep only valid claims and fields',repair[3]['content'])
        self.assertIn('Rewrite copied or unsupported prose',repair[3]['content'])
        self.assertNotIn('Preserve the substantive prose',repair[3]['content'])

    def test_failure_never_overwrites_published_copy_and_existing_week_is_idempotent(self):
        _, packet = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); data=root/'data'; data.mkdir()
            items=[{'title':p['title'],'url':'https://example.org/'+p['id'],
                    'kind':'scholarly','published':'2026-10-20',
                    'publication_date_provenance':{'status':'day_known','basis':'editor_verified_original_publication_date','value':'2026-10-20'},
                    'reading':{'level':'abstract','findings':p['evidence']}} for p in packet]
            (data/'public-weekly.json').write_text(json.dumps({'run':{'date':'2026-10-26'},'items':items}),encoding='utf-8')
            path=data/'issue-editorial.json'
            original=json.dumps({'2026-10-18':{'headline':'Previously published'}})
            path.write_text(original,encoding='utf-8')
            fake=Mock()
            fake.create_chat_completion.return_value={'choices':[{'message':{'content':'{}'}}]}
            with self.assertRaises(ValueError): composer.compose(root,fake,today=date(2026,10,26))
            self.assertEqual(path.read_text(encoding='utf-8'),original)
            self.assertEqual(fake.create_chat_completion.call_count,3)
            audit=json.loads((data/'edition-audits/2026-10-26.json').read_text(encoding='utf-8'))
            self.assertEqual(audit['status'],'failed_validation')
            path.write_text(json.dumps({'2026-10-26':{'headline':'Already published'}}),encoding='utf-8')
            fake.reset_mock()
            self.assertFalse(composer.compose(root,fake,today=date(2026,10,26)))
            fake.create_chat_completion.assert_not_called()

    def test_real_failure_shape_reports_anchors_and_hidden_inline_errors_together(self):
        # Synthetic content reproduces the Nov 10 three-attempt failure shape;
        # no source extracts or generated article text are stored in this test.
        draft, packet = self.fixture()
        plan = {'themes': [dict(short='A theme', title='Assistance and learning', keys=keys)
                           for keys in (['S1', 'S2'], ['S2', 'S3'], ['S3', 'S4'])]}
        long_quote = ' '.join(composer.normalize(packet[0]['evidence']).split()[:15])
        first = copy.deepcopy(draft['signals'][0])
        first['evidence'] = [{'key': 'S1', 'quote': long_quote}]
        first['citations'] = [{'key': 'S1', 'text': 'an absent source name'}]
        second = copy.deepcopy(first)
        second['evidence'].append({'key': 'S2', 'quote': long_quote})
        second['citations'].append({'key': 'S2', 'text': 'another absent source name'})
        third = copy.deepcopy(second)
        third['evidence'][0]['quote'] = 'did not establish lasting independent learning'
        third['evidence'][1]['quote'] = 'a paraphrased unsupported anchor not in this source'
        third['citations'][1]['text'] = 'Source 2'
        replies = [plan, first, second, third]
        model = Mock()
        model.create_chat_completion.side_effect = [
            {'choices': [{'message': {'content': json.dumps(value)}}]} for value in replies]
        audit = {}
        before = copy.deepcopy(replies)
        with self.assertRaisesRegex(ValueError, 'theme 1'):
            composer.draft_in_stages(model, packet, audit)
        failures = [entry['validation_error'] for entry in audit['stages'][1:]]
        for expected in ('Evidence array must cover', '15 normalized words',
                         'S1 inline link: Citation text must occur exactly once'):
            self.assertIn(expected, failures[0])
        for key in ('S1', 'S2'):
            self.assertIn(f'{key} evidence quote has 15', failures[1])
            self.assertIn(f'{key} inline link: Citation text must occur exactly once', failures[1])
        self.assertIn('Evidence anchor does not match source: S2', failures[2])
        self.assertIn('S1 inline link: Citation text must occur exactly once', failures[2])
        self.assertNotIn('candidate', audit)
        self.assertEqual(replies, before)  # No silent trimming or inserted links.
        instruction = model.create_chat_completion.call_args_list[1].kwargs['messages'][1]['content']
        self.assertIn('The two arrays have DIFFERENT purposes', instruction)
        self.assertIn('If findings are\nabsent', instruction)

    def test_generated_section_keeps_anchor_and_inline_gates(self):
        draft, packet = self.fixture()
        original = draft['signals'][0]
        for count in (4, 13):
            section = copy.deepcopy(original)
            section['evidence'][0]['quote'] = ' '.join(
                composer.normalize(packet[0]['evidence']).split()[:count])
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, '5–12'):
                composer.validate_generated_section(section, packet[:2])
        for change in ('wrong_source', 'unknown_source', 'missing_link', 'duplicate_link'):
            section = copy.deepcopy(original)
            sources = copy.deepcopy(packet[:2])
            if change == 'wrong_source':
                sources[1]['evidence'] = 'Only a different population discussed these separate questions.'
                section['evidence'][0]['quote'] = sources[1]['evidence']
            elif change == 'unknown_source':
                section['evidence'][0]['key'] = 'S99'
            elif change == 'missing_link':
                section['citations'].pop()
            else:
                section['text'] += ' Source 1 is mentioned again.'
            with self.subTest(change=change), self.assertRaises(ValueError):
                composer.validate_generated_section(section, sources)
        composer.validate_generated_section(copy.deepcopy(original), packet[:2])
        malformed = copy.deepcopy(original)
        malformed['evidence'][0]['key'] = ['S1']
        malformed['citations'][0]['key'] = {'source': 'S1'}
        with self.assertRaisesRegex(ValueError, 'unknown source'):
            composer.validate_generated_section(malformed, packet[:2])

    def test_citation_label_contract_uses_identity_never_claim_text(self):
        _, packet = self.fixture()
        packet[0]['authors'] = ['Avery Researcher']
        packet[1]['authors'] = ['Robin Author', 'Lee Colleague']
        contract = composer.section_citation_contract(packet)
        self.assertEqual([c['text'] for c in contract],
                         ['Avery Researcher', 'Robin Author and colleagues', 'Source 3', 'Source 4'])
        packet[2]['authors'] = ['Avery Researcher']
        self.assertEqual(composer.section_citation_contract(packet)[0]['text'], '“Source 1”')
        self.assertEqual(composer.section_citation_contract(packet)[2]['text'], '“Source 3”')

    def test_solo_and_shared_author_labels_do_not_create_overlapping_links(self):
        draft, packet = self.fixture()
        packet[0].update(authors=['Avery Researcher'], title='Practice')
        packet[1].update(authors=['Avery Researcher', 'Another Author'], title='Practice now')
        contract = composer.section_citation_contract(packet[:2])
        self.assertEqual([c['text'] for c in contract], ['“Practice”', '“Practice now”'])
        section = copy.deepcopy(draft['signals'][0])
        section['text'] = '“Practice” and “Practice now” address this question. ' + section['text']
        section['citations'] = contract
        composer.validate_generated_section(section, packet[:2])

    def test_stale_discovery_fails_instead_of_silently_skipping_the_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data'
            data.mkdir()
            (data / 'public-weekly.json').write_text(
                json.dumps({'run': {'date': '2026-10-26'}, 'items': []}), encoding='utf-8')
            (data / 'issue-editorial.json').write_text(
                json.dumps({'2026-10-26': {'headline': 'Old issue'}}), encoding='utf-8')
            fake = Mock()
            with self.assertRaisesRegex(ValueError, 'Stale weekly discovery'):
                composer.compose(root, fake, today=date(2026, 11, 2))
            fake.create_chat_completion.assert_not_called()
            self.assertEqual(composer.collection_week_start(date(2026, 11, 3)),
                             date(2026, 11, 2))
            (data / 'public-weekly.json').write_text(
                json.dumps({'run': {'date': '2026-11-02'}, 'items': []}), encoding='utf-8')
            self.assertIsNotNone(composer.pending(root, today=date(2026, 11, 3)))

    def test_same_strict_window_is_not_reissued_when_observation_date_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data = root / 'data'; data.mkdir()
            weekly = {'run': {'date': '2026-11-10', 'publication_window':
                composer.window_metadata('2026-11-10')}, 'items': []}
            (data / 'public-weekly.json').write_text(json.dumps(weekly))
            drafts = {'2026-11-09': {'headline': 'Original Monday edition'}}
            (data / 'issue-editorial.json').write_text(json.dumps(drafts))
            self.assertIsNone(composer.pending(root, today=date(2026, 11, 10)))
            self.assertEqual(json.loads((data / 'public-weekly.json').read_text()), weekly)
            self.assertEqual(json.loads((data / 'issue-editorial.json').read_text()), drafts)
            # An archive still prevents a duplicate when the draft has moved on.
            (data / 'issue-editorial.json').write_text('{}')
            (data / 'approved-issues').mkdir()
            archive = data / 'approved-issues/2026-11-09.json'
            archive.write_text(json.dumps({'edition_date': '2026-11-09', 'status': 'published',
                'publication_window': composer.window_metadata('2026-11-09')}))
            self.assertIsNone(composer.pending(root, today=date(2026, 11, 10)))
            # Neither a different week nor an unapproved archive suppresses work.
            archive.write_text(json.dumps({'edition_date': '2026-11-09', 'status': 'awaiting_publication'}))
            self.assertIsNotNone(composer.pending(root, today=date(2026, 11, 10)))
            archive.write_text(json.dumps({'edition_date': '2026-11-02', 'status': 'published'}))
            self.assertIsNotNone(composer.pending(root, today=date(2026, 11, 10)))
            # Invalid current windows still fail even if a matching draft exists.
            (data / 'issue-editorial.json').write_text(json.dumps(drafts))
            weekly['run']['publication_window']['from'] = '2026-11-03'
            (data / 'public-weekly.json').write_text(json.dumps(weekly))
            with self.assertRaisesRegex(ValueError, 'Publication window'):
                composer.pending(root, today=date(2026, 11, 10))

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

    def test_source_access_and_commentary_require_explicit_labels(self):
        for source in ({'level':'abstract'}, {'kind':'nonacademic'}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                composer.qualify_section({'text':'The study established a broad improvement.'},[source])
        composer.qualify_section({'text':'The abstract reports a limited comparison.'},[{'level':'abstract'}])
        composer.qualify_section({'text':'The commentary proposes a design question.'},[{'kind':'nonacademic'}])


    def preprint_fixture(self):
        draft, packet = self.fixture()
        for source in packet:
            source.update(kind='scholarly', level='full_text', preprint=True,
                          research_type='observational',
                          review_scope='Peer review is not verified.',
                          review_label='Preprint, not verified peer-reviewed evidence.')
        for section in draft['signals'] + [draft['tension']]:
            section['text'] += (' These preprints are not verified peer-reviewed evidence; '
                                'their results do not establish strong causal evidence.')
        return draft, packet

    def test_unverified_peer_review_qualifications_preserve_uncertainty(self):
        _, packet = self.preprint_fixture()
        for phrase in ('not verified peer-reviewed evidence', 'not verified as peer reviewed',
                       'peer review is unverified', 'peer-review status is not verified'):
            for causal in ('does not establish causality', 'do not establish strong causal evidence',
                           'cannot establish causal effects', 'cannot establish a strong causal effect'):
                with self.subTest(phrase=phrase, causal=causal):
                    composer.qualify_section({'text':f'Preprint: {phrase}; the evidence {causal}.'}, packet[:2])
        with self.assertRaisesRegex(ValueError, 'does not mean verified absence'):
            composer.qualify_section({'text':'This preprint is not peer reviewed and does not establish causality.'}, packet[:2])
        composer.qualify_section({'text':
            'These preprints are not verified peer-reviewed evidence; their results do not establish '
            'strong causal evidence. Self-report cannot establish causal mediation. A brief session '
            'cannot establish causal or lasting learning effects.'}, packet[:2])

    def test_frame_cannot_convert_unverified_review_into_absence(self):
        draft, packet = self.preprint_fixture()
        for field in ('headline', 'deck', 'letter', 'closer'):
            bad = copy.deepcopy(draft)
            bad[field] += ' These preprints are not peer reviewed.'
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'does not mean verified absence'):
                composer.validate(bad, packet)
            good = copy.deepcopy(draft)
            good[field] += ' These preprints have peer review status unverified.'
            composer.validate(good, packet)

    def test_evidence_anchor_word_bounds_are_five_through_twelve(self):
        draft, packet = self.preprint_fixture()
        source_words = composer.normalize(packet[0]['evidence']).split()
        for count in (4, 5, 12, 13):
            candidate = copy.deepcopy(draft)
            candidate['signals'][0]['evidence'][0]['quote'] = ' '.join(source_words[:count])
            with self.subTest(count=count):
                if count in (5, 12):
                    composer.validate(candidate, packet)
                else:
                    with self.assertRaisesRegex(ValueError, '5–12 normalized words'):
                        composer.validate(candidate, packet)

    def test_original_comparison_can_retain_labels_and_exact_denominators(self):
        draft, packet = self.preprint_fixture()
        for source in packet:
            source['evidence'] += (
                ' Methods: The synthetic classroom sample has 112 enrolled pupils and 89 paired observations. '
                'Findings: The study codes critical engagement and conceptual/procedural help as separate labels. '
                'Limitations: Preprint, not verified peer-reviewed evidence. Article screening is not peer review; '
                'reported results do not establish strong causal evidence.')
        for section in draft['signals'] + [draft['tension']]:
            section['text'] += (
                ' The account describes 112 participants, but the model uses 89 matched cases. '
                'Its critical engagement measure is distinct from conceptual/procedural help.')
        composer.validate(draft, packet)

    def test_valid_caveat_does_not_hide_positive_peer_review_or_causal_claim(self):
        draft, packet = self.preprint_fixture()
        for overclaim in ('This is peer-reviewed evidence.', 'These findings prove a lasting benefit.',
                          'This causes independent learning.', 'This establishes causality.',
                          'This provides strong causal evidence.', 'Peer review is verified.',
                          'This has confirmed peer review.',
                          'The findings establish a causal effect.',
                          'The findings establish strong causality.',
                          'The findings do not establish causality but do establish strong causal effects.',
                          'The findings cannot establish a causal effect but establish a strong causal effect.'):
            for field in ('title', 'text'):
                bad = copy.deepcopy(draft)
                bad['signals'][0][field] += ' ' + overclaim
                with self.subTest(overclaim=overclaim, field=field), self.assertRaisesRegex(ValueError, 'unsupported peer-review or causal'):
                    composer.validate(bad, packet)
            bad = copy.deepcopy(draft)
            bad['letter'] += ' ' + overclaim
            with self.subTest(overclaim=overclaim, field='letter'), self.assertRaisesRegex(ValueError, 'unsupported peer-review or causal'):
                composer.validate(bad, packet)

    def test_full_validator_accepts_original_qualified_fixture_without_repairing_prose(self):
        draft, packet = self.preprint_fixture()
        before = copy.deepcopy(draft)
        result = composer.validate(draft, packet)
        for new, old in zip(result['signals'] + [result['tension']], before['signals'] + [before['tension']]):
            for field in ('short', 'title', 'text', 'evidence'):
                self.assertEqual(new[field], old[field])
        for field in ('headline', 'deck', 'letter', 'closer'):
            self.assertEqual(result[field], before[field])

    def test_explicit_causal_demonstration_rejects_claim_without_masking_contrast(self):
        draft, packet = self.preprint_fixture()
        for statement in ('The result demonstrates causality.',
                          'The results demonstrate a strong causal effect.',
                          'The result demonstrated causal effects.',
                          'The result does not demonstrate causality but demonstrates causality.',
                          'The results cannot demonstrate a causal effect but demonstrate strong causal evidence.'):
            for field in ('headline', 'deck', 'letter', 'closer', 'signal_text'):
                bad = copy.deepcopy(draft)
                if field == 'signal_text': bad['signals'][0]['text'] += ' ' + statement
                else: bad[field] += ' ' + statement
                with self.subTest(statement=statement, field=field), self.assertRaisesRegex(ValueError, 'unsupported peer-review or causal'):
                    composer.validate(bad, packet)
        for negative in ('The result does not demonstrate causality.',
                         'The results do not demonstrate strong causal effects.',
                         'The result did not demonstrate a causal effect.',
                         'The result cannot demonstrate causal evidence.'):
            good = copy.deepcopy(draft)
            good['signals'][0]['text'] += ' ' + negative
            good['letter'] += ' ' + negative
            composer.validate(good, packet)

    def test_outcome_gain_headings_are_not_repaired_by_body_caveats(self):
        draft, packet = self.preprint_fixture()
        for title in ("GenAI's Role in Enhancing Critical Thinking Across Cultures",
                      'AI improves independent learning in classrooms', 'AI produces lasting learning gains'):
            for field in ('headline', 'signal_title', 'short', 'tension_title'):
                bad = copy.deepcopy(draft)
                if field == 'headline': bad[field] = title
                elif field == 'tension_title': bad['tension']['title'] = title
                else: bad['signals'][0]['short' if field == 'short' else 'title'] = title
                with self.subTest(title=title, field=field), self.assertRaisesRegex(ValueError, 'neutral preprint heading'):
                    composer.validate(bad, packet)
        composer.validate_title('Reported engagement and open learning questions', packet)

    def test_copy_guards_reject_long_and_stitched_passages_but_allow_short_caveat(self):
        passage = ('Observers recorded each participant choosing between possible explanations during practice. '
                   'Interviewees described uncertainty about interpreting unfamiliar feedback from the classroom assistant. '
                   'The authors warned that self reports alone cannot measure sustained independent skill development.')
        packet = [{'key':'S1', 'evidence':passage}]
        with self.assertRaisesRegex(ValueError, 'copies a long source passage'):
            composer.validate_original_prose(passage, packet)
        stitched = ('Observers recorded each participant choosing between possible explanations during practice. '
                    'A separate issue emerges. Interviewees described uncertainty about interpreting unfamiliar feedback '
                    'from the classroom assistant. Consider another limitation. The authors warned that self reports '
                    'alone cannot measure sustained independent skill development.')
        # Every copied run is below sixteen words, but most of the paragraph is excerpts.
        with self.assertRaisesRegex(ValueError, 'stitches together source passages'):
            composer.validate_original_prose(stitched, packet)
        composer.validate_original_prose(
            'A cautious comparison begins with the available observations. Observers recorded each '
            'participant choosing between possible explanations during practice. That narrow task '
            'would need separate evaluation before it could answer a broader question about transfer.', packet)

    def test_staged_repairs_recheck_copy_numbers_plan_titles_and_frame(self):
        draft, packet = self.preprint_fixture()
        pairs = [['S1','S2'], ['S2','S3'], ['S3','S4']]
        plan = {'themes':[{'short':'A theme', 'title':'Assistance and independent learning', 'keys':p} for p in pairs]}
        bad_plan = copy.deepcopy(plan)
        bad_plan['themes'][0]['title'] = "GenAI's Role in Enhancing Critical Thinking Across Cultures"
        bad_copy = copy.deepcopy(draft['signals'][0])
        bad_copy['text'] += ' ' + packet[0]['evidence']
        bad_number = copy.deepcopy(draft['signals'][0])
        bad_number['text'] += ' The sample contained 789 people.'
        frame = {k:copy.deepcopy(v) for k,v in draft.items() if k != 'signals'}
        frame['tension'].pop('evidence')
        bad_frame = copy.deepcopy(frame)
        bad_frame['headline'] = 'AI improves independent learning in classrooms'
        bad_anchor = copy.deepcopy(draft['signals'][1])
        bad_anchor['evidence'][0]['quote'] = ' '.join(composer.normalize(packet[1]['evidence']).split()[:13])
        replies = [bad_plan, plan, bad_copy, bad_number, draft['signals'][0],
                   bad_anchor] + draft['signals'][1:] + [bad_frame, frame]
        model = Mock()
        model.create_chat_completion.side_effect = [{'choices':[{'message':{'content':json.dumps(x)}}]} for x in replies]
        audit = {}
        result = composer.draft_in_stages(model, packet, audit)
        self.assertEqual(result['headline'], draft['headline'])
        errors = [s.get('validation_error', '') for s in audit['stages']]
        for expected in ('neutral preprint heading', 'copies a long source passage', 'Unsupported numeric claim',
                         '5–12 normalized words'):
            self.assertTrue(any(expected in error for error in errors), expected)
        self.assertTrue(any(s['stage'] == 'editorial frame' and s.get('validation_error') for s in audit['stages']))
        overview = model.create_chat_completion.call_args_list[0].kwargs['messages'][1]['content']
        self.assertIn('review_scope', overview)
        self.assertIn('limitations_preview', overview)
        self.assertIn('Peer review is not verified', overview)

    def test_repeated_invalid_candidates_receive_rewrite_feedback_and_remain_rejected(self):
        _, packet = self.preprint_fixture()
        invalid = {'themes':[]}
        model = Mock()
        model.create_chat_completion.return_value = {'choices':[{'message':{'content':json.dumps(invalid)}}]}
        audit = {}
        with self.assertRaises(ValueError): composer.draft_in_stages(model, packet, audit)
        self.assertEqual([s['repeated_candidate'] for s in audit['stages']], [False, True, True])
        self.assertIn('Make a substantive correction', model.create_chat_completion.call_args_list[2].kwargs['messages'][-1]['content'])
        self.assertNotIn('candidate', audit)  # No final draft was fabricated.

    def test_prompt_does_not_order_false_review_status_or_preserve_flawed_prose(self):
        _, packet = self.preprint_fixture()
        instruction = composer.prompt(packet)
        self.assertIn('Preserve unverified peer review as uncertainty', instruction)
        self.assertIn('never copy sixteen consecutive source words', instruction)
        self.assertNotIn('explicitly say "preprint", "not peer reviewed"', instruction)


if __name__=='__main__': unittest.main()

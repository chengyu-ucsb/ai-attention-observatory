"""Restart, budget and publication-boundary tests with offline model fixtures."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from edition_progress import Progress, MemoryStore, HeldStage
from edition_schedule import publication_cutoff
import compose_issue as composer
import test_compose_issue


def responses(*values):
    model = Mock()
    model.create_chat_completion.side_effect = [
        {'choices':[{'message':{'content':json.dumps(value)}}]} for value in values]
    return model


def check(value):
    if value != {'answer':'supported'}:
        raise ValueError('unsupported claim')


class ProgressTests(unittest.TestCase):
    def test_restart_reuses_checked_result_but_revalidates_it(self):
        store = MemoryStore(); model = responses({'answer':'supported'})
        Progress(store,'model').generate(model,'theme','source v1',check,{})
        validator = Mock(side_effect=check)
        Progress(store,'model').generate(model,'theme','source v1',validator,{})
        self.assertEqual(model.create_chat_completion.call_count,1)
        validator.assert_called_once()
        rejecting = Mock(side_effect=ValueError('policy no longer accepts this claim'))
        with self.assertRaises(ValueError):
            Progress(store,'model').generate(model,'theme','source v1',rejecting,{})
        self.assertEqual(model.create_chat_completion.call_count,1)

    def test_only_changed_evidence_or_model_opens_a_new_attempt_budget(self):
        store = MemoryStore(); model = responses({}, {}, {'answer':'supported'})
        for _ in range(2):
            with self.assertRaises(HeldStage):
                Progress(store,'model').generate(model,'theme','source v1',check,{})
        self.assertEqual(model.create_chat_completion.call_count,2)
        Progress(store,'model').generate(model,'theme','source v2',check,{})
        self.assertEqual(model.create_chat_completion.call_count,3)

    def test_shutdown_during_inference_consumes_reserved_attempt(self):
        store = MemoryStore(); model = Mock()
        model.create_chat_completion.side_effect = RuntimeError('runner interrupted')
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError,'runner interrupted'):
                Progress(store,'model').generate(model,'theme','same source',check,{})
        with self.assertRaises(HeldStage):
            Progress(store,'model').generate(model,'theme','same source',check,{})
        self.assertEqual(model.create_chat_completion.call_count,2)

    def test_conflicting_write_cannot_start_inference(self):
        store = MemoryStore(); store.save_editorial = Mock(side_effect=RuntimeError('conflict'))
        model = Mock()
        with self.assertRaisesRegex(RuntimeError,'conflict'):
            Progress(store,'model').generate(model,'theme','same source',check,{})
        model.create_chat_completion.assert_not_called()

    def test_time_budget_defers_without_consuming_an_attempt(self):
        store = MemoryStore(); model = Mock()
        with self.assertRaisesRegex(HeldStage,'time_budget'):
            Progress(store,'model',seconds=0).generate(model,'theme','same source',check,{})
        self.assertEqual(store.rows,{})
        model.create_chat_completion.assert_not_called()

    def test_semantic_correction_shares_the_writer_budget(self):
        store = MemoryStore(); model = responses({'answer':'supported'},{'answer':'supported'})
        progress = Progress(store,'model')
        progress.generate(model,'theme','same source',check,{})
        progress.generate(model,'theme','same source',check,{},correction='Fix attribution')
        with self.assertRaises(HeldStage):
            progress.generate(model,'theme','same source',check,{},correction='Still wrong')
        self.assertEqual(model.create_chat_completion.call_count,2)
        with self.assertRaises(HeldStage):
            Progress(store,'model').generate(model,'theme','same source',check,{})


class EditionRecoveryTests(unittest.TestCase):
    def fixture(self):
        draft, packet = test_compose_issue.CompositionTests().fixture()
        pairs = [['S1','S2'],['S2','S3'],['S3','S4']]
        plan = {'themes':[{'short':'A theme','title':'Assistance and learning','keys':pair} for pair in pairs]}
        frame = {k:copy.deepcopy(v) for k,v in draft.items() if k != 'signals'}
        frame['tension'].pop('evidence')
        return draft, packet, plan, frame

    def test_cutoff_reuses_passed_sections_and_leaves_failed_section_out(self):
        draft, packet, plan, frame = self.fixture()
        store = MemoryStore()
        model = responses(plan,draft['signals'][0],{}, {},draft['signals'][2],frame)
        # This test isolates staging/caching; separate tests exercise actual
        # review receipt validation. Production always runs section reviews.
        with self.assertRaisesRegex(HeldStage,'cutoff'):
            composer.draft_in_stages(model,packet,{},progress=Progress(store,composer.MODEL),review_sections=False)
        self.assertEqual(model.create_chat_completion.call_count,5)
        result = composer.draft_in_stages(model,packet,{},progress=Progress(store,composer.MODEL),
                                         compact=True,review_sections=False)
        self.assertEqual(model.create_chat_completion.call_count,6)
        self.assertEqual(result['edition_format'],'compact')
        self.assertEqual(len(result['signals']),2)
        self.assertEqual(result['signals'][0]['text'],draft['signals'][0]['text'])
        self.assertEqual(result['signals'][1]['text'],draft['signals'][2]['text'])
        self.assertNotIn('S99',json.dumps(result))

    def test_production_path_reviews_every_section_and_final_draft(self):
        draft, packet, plan, frame = self.fixture()
        outputs = iter([plan,*draft['signals'],frame])
        model = Mock(); review_calls = []
        def answer(**kwargs):
            instruction = kwargs['messages'][1]['content']
            if '\nDRAFT:\n' not in instruction:
                value = next(outputs)
            else:
                candidate, _ = json.JSONDecoder().raw_decode(instruction.split('\nDRAFT:\n',1)[1])
                review_calls.append(candidate)
                passage = candidate['signals'][0]['text'][:85]
                keys = {a['key'] for s in candidate['signals']+[candidate['tension']] for a in s['evidence']}
                value = {'decision':'pass','checks':[{'criterion':c,'pass':True,
                    'reason':'The specific comparison preserves source attribution and the stated evidence boundaries.',
                    'example':passage} for c in composer.REVIEW_CRITERIA],
                    'source_checks':[{'key':k,'quote':'did not establish lasting independent learning',
                        'claim':passage,'supported':True} for k in sorted(keys)], 'issues':[]}
            return {'choices':[{'message':{'content':json.dumps(value)}}]}
        model.create_chat_completion.side_effect = answer
        store = MemoryStore()
        first = composer.draft_in_stages(model,packet,{},progress=Progress(store,composer.MODEL))
        self.assertEqual(len(review_calls),4)
        self.assertEqual([len(x['signals']) for x in review_calls],[1,1,1,3])
        second = composer.draft_in_stages(model,packet,{},progress=Progress(store,composer.MODEL))
        self.assertEqual(first,second)
        self.assertEqual(len(review_calls),4)
        self.assertEqual(model.create_chat_completion.call_count,9)

    def test_same_week_recovery_date_does_not_reset_held_inputs(self):
        _,packet,_,_ = self.fixture()
        weekly = {'run':{'date':'2026-11-09','publication_window':composer.window_metadata('2026-11-09')},'items':[]}
        key = composer.edition_key(weekly,packet,True)
        store = MemoryStore()
        store.save_editorial(key,0,{'kind':'edition','status':'held','runs':1,'reason':'unsupported number'})
        weekly['run']['date'] = '2026-11-12'
        with patch.object(composer,'pending',return_value=weekly), patch.object(composer,'evidence',return_value=packet):
            result = composer.readiness(today=dt.date(2026,11,12),store=store)
        self.assertFalse(result['needed']); self.assertFalse(result['needs_model'])
        self.assertEqual(result['status'],'held_unchanged_inputs')

    def test_checked_release_skips_model_download(self):
        _,packet,_,_ = self.fixture()
        weekly = {'run':{'date':'2026-11-12','publication_window':composer.window_metadata('2026-11-12')},'items':[]}
        store = MemoryStore()
        store.save_editorial(composer.edition_key(weekly,packet,True),0,
                             {'kind':'edition','status':'checked','runs':3})
        with patch.object(composer,'pending',return_value=weekly), patch.object(composer,'evidence',return_value=packet):
            result = composer.readiness(today=dt.date(2026,11,12),store=store)
        self.assertTrue(result['needed']); self.assertFalse(result['needs_model'])

    def test_compact_format_keeps_citation_and_numeric_gates(self):
        draft, packet, _, _ = self.fixture()
        draft.update(edition_format='compact',citation_schema_version=1)
        draft['signals'] = draft['signals'][:1]
        composer.validate(copy.deepcopy(draft),packet)
        draft['signals'][0]['text'] += ' The sample had 9876 people.'
        with self.assertRaisesRegex(ValueError,'Unsupported numeric claim'):
            composer.validate(draft,packet)

    def test_elapsed_budget_keeps_unattempted_work_resumable(self):
        _,packet,_,_ = self.fixture()
        weekly = {'run':{'date':'2026-11-12','publication_window':composer.window_metadata('2026-11-12')},'items':[]}
        store = MemoryStore()
        def exhausted(model,packet,audit,**kwargs):
            audit['budget_deferred'] = True
            raise HeldStage('Insufficient checked material for an edition')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir();(root/'data/issue-editorial.json').write_text('{}')
            with patch.object(composer,'pending',return_value=weekly), patch.object(composer,'evidence',return_value=packet), patch.object(composer,'draft_in_stages',side_effect=exhausted):
                with self.assertRaises(ValueError):
                    composer.compose(root,Mock(),today=dt.date(2026,11,12),store=store)
                self.assertTrue(composer.readiness(root,today=dt.date(2026,11,12),store=store)['needed'])
        row=store.get_editorial(composer.edition_key(weekly,packet,True))['value']
        self.assertEqual(row['status'],'pending')
        self.assertEqual(row['runs'],1)

    def test_monday_cutoff_tracks_eastern_time_and_dst(self):
        for month,day,hour in [(11,9,16),(6,8,15)]:
            self.assertFalse(publication_cutoff(dt.datetime(2026,month,day,hour,29,tzinfo=dt.timezone.utc)))
            self.assertTrue(publication_cutoff(dt.datetime(2026,month,day,hour,30,tzinfo=dt.timezone.utc)))


if __name__ == '__main__':
    unittest.main()

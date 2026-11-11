"""Private intake cannot supply public approval; all sources/models are offline."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import comprehensive_readings as reading
import preparation_pipeline as pipeline
import prepared_article_readings as prepared
from source_quality import private_reading_eligibility, screen
import test_preparation_pipeline as fixtures
NOW = fixtures.NOW


class PrivateSelectionTests(unittest.TestCase):
    def records(self):
        # Frozen historical metadata, never the mutable production queue.
        fixture = ROOT / 'tests/fixtures/private-reading-selection-2026-11-10.json'
        return json.loads(fixture.read_text())['records']

    def test_actual_six_documents_select_two_human_ai_papers_not_engineering_or_cooldowns(self):
        records = self.records()
        before = deepcopy(records)
        retrieve = Mock(return_value=(None, []))
        stats = reading.process(records, Mock(), run_date=date(2026, 11, 10), retriever=retrieve)
        self.assertEqual({call.args[0]['doi'] for call in retrieve.call_args_list},
                         {'10.48550/arxiv.2611.04783', '10.48550/arxiv.2611.06830'})
        self.assertEqual(stats['selection'], {'considered': 6, 'eligible': 2,
            'deferred_by_limit': 0, 'skipped': {'no_explicit_human_topic': 2, 'retry_cooldown': 2}})
        pipeline.validate_stage_report('review', stats)
        attempted = {id(call.args[0]) for call in retrieve.call_args_list}
        for original, record in zip(before, records):
            if id(record) not in attempted:
                self.assertEqual(record, original)
        # Same failure checkpoints do not churn on the next preparation pass.
        retrieve.reset_mock()
        again = reading.process(records, Mock(), run_date=date(2026, 11, 10), retriever=retrieve)
        retrieve.assert_not_called()
        self.assertEqual(again['selection']['skipped']['retry_cooldown'], 4)

    def test_future_topics_and_unknown_venues(self):
        base = {'kind': 'scholarly', 'venue': 'arXiv', 'doi': '10.48550/arxiv.2611.00001'}
        for title, abstract in [
            ('Student agency with generative AI', ''),
            ('Longitudinal AI interaction', 'Cognitive atrophy and diminished human agency motivate this proposal.'),
            ('Student metacognition with generative AI', 'Students evaluate their own learning.'),
            ('How people allocate attention with AI', ''),
        ]:
            with self.subTest(title=title):
                record = dict(base, title=title, abstract_text=abstract)
                self.assertEqual(private_reading_eligibility(record), 'human_ai_topic_for_private_review')
                self.assertEqual(screen(record)['decision'], 'hold')
                record['venue'] = 'Unknown Publisher'
                self.assertEqual(private_reading_eligibility(record), 'skip_unverified_venue')
        for title in ['Transformer cross-attention for image recognition',
                      'AI reasoning benchmarks', 'KV cache offloading for LLM inference',
                      'Artificial intelligence for Alzheimer disease detection',
                      'AI agents plan autonomous tool execution', 'Attention in AI models']:
            with self.subTest(title=title):
                self.assertTrue(private_reading_eligibility(dict(base, title=title)).startswith('skip_'))

    def test_model_reasoning_and_clinical_cognition_are_not_human_ai_outcomes(self):
        for title, abstract in [
            ('LLM reasoning cache optimization for users',
             'We improve transformer throughput for users by reducing KV cache memory during reasoning.'),
            ('AI-assisted Alzheimer detection',
             'Our machine learning classifier detects disease using human cognition and cognitive load features from clinical patients.'),
        ]:
            self.assertEqual(private_reading_eligibility({'kind': 'scholarly', 'venue': 'arXiv',
                'title': title, 'abstract_text': abstract}), 'skip_no_explicit_human_topic')

    def test_successful_private_note_does_not_approve_preprint_or_store_source(self):
        record = next(r for r in self.records() if r.get('doi', '').endswith('2611.04783'))
        original = deepcopy(record)
        document = reading.Document([{'location': 'page:1', 'text': 'PRIVATE_SOURCE_SENTINEL'}],
            record['url'], coverage={'evidence_status': 'full_document_retrieved'})
        with patch.object(reading, 'synthesize', return_value={
                'coverage': {**document.manifest(), 'all_retrieved_text_processed': True}}):
            stats = reading.process([record], Mock(), run_date=date(2026, 11, 10),
                retriever=Mock(return_value=(document, [])))
        self.assertEqual(stats['summaries_completed'], 1)
        self.assertEqual(screen(record)['decision'], 'hold')
        from original_readings import weekly_source_eligible
        self.assertFalse(weekly_source_eligible(record))
        self.assertNotIn('original_reading', record)
        self.assertNotIn('source_review', record)
        self.assertNotIn('PRIVATE_SOURCE_SENTINEL', json.dumps(record))
        import build_public
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            (data / 'library.json').write_text(json.dumps([record]))
            (data / 'weekly.json').write_text(json.dumps({'run': {}, 'items': [record]}))
            with patch.object(build_public, 'DATA', data):
                build_public.build()
            self.assertEqual(json.loads((data / 'public-library.json').read_text()), [])
            self.assertEqual(json.loads((data / 'public-weekly.json').read_text())['items'], [])
            self.assertEqual(json.loads((data / 'editorial-weekly.json').read_text())['items'], [])
        for key, value in original.items():
            self.assertEqual(record[key], value)

    def test_selection_is_bounded_fails_closed_and_optional_for_old_reports(self):
        base = {'attempted': 0, 'summaries_completed': 0, 'failed': 0, 'skipped_no_model': False}
        pipeline.validate_stage_report('review', base)
        good = dict(base, selection={'considered': 3, 'eligible': 1,
                                    'deferred_by_limit': 1, 'skipped': {'retry_cooldown': 2}})
        pipeline.validate_stage_report('review', good)
        bad = []
        for field, value in [('considered', True), ('eligible', -1), ('deferred_by_limit', 0),
                             ('skipped', {'invented_reason': 2}), ('skipped', {'retry_cooldown': True})]:
            report = deepcopy(good); report['selection'][field] = value; bad.append(report)
        report = deepcopy(good); report['selection']['source_text'] = 'forbidden'; bad.append(report)
        for report in bad:
            with self.assertRaises(ValueError): pipeline.validate_stage_report('review', report)


class PolicyReceiptTests(unittest.TestCase):
    setUp = fixtures.PipelineTests.setUp
    save = fixtures.PipelineTests.save
    save_packet = fixtures.PipelineTests.save_packet
    receipt = fixtures.PipelineTests.receipt

    def test_old_policy_receipt_is_valid_but_requires_one_fresh_bounded_pass(self):
        run = self.receipt()
        pipeline.finalize(self.root, NOW)
        self.assertTrue(pipeline.edition_ready(self.root, NOW)['ready'])
        # Model an old legitimate receipt, not a corrupt one.
        run.pop('reading_policy_version')
        run['stages']['review'].pop('selection')
        pipeline.validate_reading_receipt(run, 'preparation_reading_run', NOW)
        pipeline.atomic_save(self.folder / 'reading-run.json', run)
        final = pipeline.read(self.folder / 'final-reading.json')
        final['reading_run_sha256'] = pipeline.digest(run)
        pipeline.atomic_save(self.folder / 'final-reading.json', final)
        self.assertEqual(pipeline.edition_ready(self.root, NOW)['status'], 'final_reading_policy_changed')
        with self.assertRaisesRegex(ValueError, 'current_final_reading_run_required'):
            pipeline.finalize(self.root, NOW)
        self.receipt()
        pipeline.finalize(self.root, NOW)
        for _ in range(3): self.assertTrue(pipeline.edition_ready(self.root, NOW)['ready'])

    def test_policy_version_malformed_or_future_is_corrupt_not_retryable(self):
        run = self.receipt()
        missing = deepcopy(run); missing['stages']['review'].pop('selection')
        with self.assertRaisesRegex(ValueError, 'invalid_preparation_reading_run_receipt'):
            pipeline.validate_reading_receipt(missing, 'preparation_reading_run', NOW)
        for version in [True, 0, -1, '2', 3]:
            changed = dict(run, reading_policy_version=version)
            with self.assertRaisesRegex(ValueError, 'invalid_preparation_reading_run_receipt'):
                pipeline.validate_reading_receipt(changed, 'preparation_reading_run', NOW)

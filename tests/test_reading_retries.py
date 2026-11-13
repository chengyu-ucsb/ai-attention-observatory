from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import comprehensive_readings as reading
from prepared_reading_schema import validate_saved_record


class ReadingRetryTests(unittest.TestCase):
    def test_two_bounded_same_day_format_retries_then_cooldown(self):
        record={'kind':'nonacademic','title':'Example','url':'https://example.org/a'}
        doc=reading.Document([{'location':'page:1','text':'Full source text for the reading attempt.'}],record['url'])
        now=datetime(2026,11,11,4,tzinfo=timezone.utc)
        for count in range(1,4):
            with patch.object(reading,'synthesize',side_effect=reading.ModelFormatError('model_schema_invalid')):
                report=reading.process([record],Mock(),retriever=lambda _:(doc,[]),run_date=now.date(),run_at=now)
            self.assertEqual(report['failed'],1)
            attempt=record['complete_reading_attempt']
            self.assertEqual(attempt['format_failures'],count)
            validate_saved_record(record,now=now)
            if count<=2:
                ready=datetime.fromisoformat(attempt['retry_after'])
                self.assertFalse(reading.due(record,now.date().isoformat(),ready-timedelta(seconds=1)))
                self.assertTrue(reading.due(record,now.date().isoformat(),ready))
                now=ready
            else:self.assertNotIn('retry_after',attempt)
        self.assertNotIn('deep_analysis',record)

    def test_rejected_evidence_never_enters_format_retry_path(self):
        for reason in ('claim_verification_failed','copied_source_passage'):
            record={'kind':'nonacademic','title':'Example','url':'https://example.org/a'}
            doc=reading.Document([{'location':'page:1','text':'A source.'}],record['url'])
            with patch.object(reading,'synthesize',side_effect=ValueError(reason)):
                reading.process([record],Mock(),retriever=lambda _:(doc,[]))
            self.assertNotIn('retry_after',record['complete_reading_attempt'])
            self.assertNotIn('deep_analysis',record)



class PersistentRetryTests(unittest.TestCase):
    def test_format_budget_does_not_reset_at_midnight_or_after_cooldown(self):
        record={'kind':'nonacademic','title':'Example','url':'https://example.org/a'}
        doc=reading.Document([{'location':'page:1','text':'A complete source passage for this attempt.'}],record['url'])
        now=datetime(2026,11,11,23,55,tzinfo=timezone.utc)
        for count in range(1,4):
            with patch.object(reading,'synthesize',side_effect=reading.ModelFormatError('model_schema_invalid')):
                report=reading.process([record],Mock(),retriever=lambda _:(doc,[]),run_date=now.date(),run_at=now)
            self.assertEqual(report['attempted'],1)
            self.assertEqual(record['complete_reading_attempt']['format_failures'],count)
            validate_saved_record(record,now=now)
            now+=timedelta(days=1)
        self.assertTrue(reading.format_retry_exhausted(record))
        self.assertFalse(reading.due(record,'2026-12-31',datetime(2026,12,31,tzinfo=timezone.utc)))
        _, selection=reading.reading_candidates([record],'2026-12-31',datetime(2026,12,31,tzinfo=timezone.utc))
        self.assertEqual(selection['skipped'],{'format_retry_exhausted':1})
        record['abstract_text']='Materially new substantive input.'
        self.assertFalse(reading.format_retry_exhausted(record))

    def test_partition_diagnostics_are_numeric_only_and_schema_valid(self):
        record={'kind':'nonacademic','title':'Example','url':'https://example.org/a'}
        doc=reading.Document([{'location':'page:1','text':'A complete source passage for this attempt.'}],record['url'])
        def fail(*args,**kwargs):
            reading.validate_verdict({'supported':[0,0,9], 'rejected':[0]},2)
        with patch.object(reading,'synthesize',side_effect=fail):
            reading.process([record],Mock(),retriever=lambda _:(doc,[]))
        diagnostic=record['complete_reading_attempt']['verifier_diagnostic']
        self.assertEqual(diagnostic,{'claim_count':2,'duplicate_supported':True,'duplicate_rejected':False,
            'overlap_count':1,'missing_count':1,'out_of_range_count':1})
        validate_saved_record(record)
        diagnostic['source_text']='Private source text must never be retained.'
        with self.assertRaises(ValueError):validate_saved_record(record)

    def test_transient_retrieval_failure_does_not_erase_budget(self):
        record={'kind':'nonacademic','title':'Example','url':'https://example.org/a'}
        doc=reading.Document([{'location':'page:1','text':'A complete source passage for this attempt.'}],record['url'])
        now=datetime(2026,11,11,4,tzinfo=timezone.utc)
        for index,reason in enumerate(('model_schema_invalid','model_schema_invalid','temporary_failure','model_schema_invalid')):
            now+=timedelta(days=3)
            retriever=(Mock(side_effect=ValueError(reason)) if index==2 else lambda _:(doc,[]))
            with patch.object(reading,'synthesize',side_effect=ValueError(reason)):
                reading.process([record],Mock(),retriever=retriever,run_date=now.date(),run_at=now)
            self.assertEqual(record['complete_reading_attempt']['format_failures'],(1,2,2,3)[index])
            validate_saved_record(record,now=now)
        self.assertTrue(reading.format_retry_exhausted(record))

class SavedRetryGateTests(unittest.TestCase):
    def test_evidence_rejection_cannot_carry_fast_retry(self):
        for status in ('claim_verification_failed','copied_source_passage','temporary_failure'):
            record={'kind':'nonacademic','title':'Example','url':'https://example.org/a',
                'complete_reading_attempt':{'status':status,'stage':'synthesis',
                    'last_at':'2026-11-11','next_at':'2026-11-13','format_failures':1,
                    'format_input_sha256':'0'*64,'provider_diagnostics':[]}}
            now=datetime(2026,11,11,4,tzinfo=timezone.utc)
            validate_saved_record(record,now=now)
            record['complete_reading_attempt']['retry_after']='2026-11-11T04:15:00+00:00'
            with self.assertRaises(ValueError): validate_saved_record(record,now=now)

if __name__=='__main__':unittest.main()

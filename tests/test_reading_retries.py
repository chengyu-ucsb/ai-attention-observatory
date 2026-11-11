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


if __name__=='__main__':unittest.main()

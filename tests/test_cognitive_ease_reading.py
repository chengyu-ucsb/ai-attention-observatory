"""Check the accepted journal-version reading and retained evidence boundary."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import original_readings as original
from condense_readings import annotate
from collection_window import previous_week, weekly_eligible

DOI='10.1016/j.chb.2024.108386'

class CognitiveEaseReadingTests(unittest.TestCase):
 def setUp(self):
  self.record=next(r for r in json.loads((ROOT/'data/library.json').read_text()) if r.get('doi')==DOI)
  self.note=next(n for n in json.loads((ROOT/'data/original-readings.json').read_text())['articles'] if n.get('doi')==DOI)

 def test_current_receipts_and_exact_published_source(self):
  self.assertTrue(original.eligible(self.note,self.record))
  self.assertEqual(self.note['source']['version'],'publishedVersion')
  self.assertEqual(self.note['source']['source_doi'],DOI)
  self.assertEqual(self.note['source']['source_sha256'],'fc48d2f5cfdfca039e8225ae91e9c3db5b10a1a78f0e38c32166ca4e3a779daa')
  self.assertIn('not human review',self.note['source']['review_scope'])
  self.assertFalse(self.note['rights']['source_text_redistribution'])

 def test_original_preserves_countervailing_results_and_analysis_denominator(self):
  source=deepcopy(self.record.get('analysis'))
  original.apply([self.record],{'articles':[self.note]})
  projected=annotate(self.record)
  d=projected['reading']['digest']
  self.assertEqual(d['status'],original.STATUS)
  self.assertIn('91 university students were analyzed after one exclusion',d['approach'])
  self.assertIn('1.20 versus 1.87 out of seven possible',d['finding'])
  self.assertIn('did not differ significantly',d['finding'])
  self.assertIn('does not establish equivalence',d['finding'])
  self.assertIn('load and quality comparisons adjusted',d['limitation'])
  self.assertEqual(projected.get('analysis'),source)
  self.assertEqual(projected['reading']['extraction_depth'],'original_summary_not_machine_extraction')

 def test_historical_reading_cannot_pad_current_week(self):
  original.apply([self.record],{'articles':[self.note]})
  start,end=previous_week('2026-11-08')
  self.assertFalse(weekly_eligible(self.record,start,end))

 def test_changed_final_text_invalidates_source_check(self):
  changed=deepcopy(self.note)
  changed['summary']['finding']='AI causes permanent cognitive damage.'
  self.assertFalse(original.eligible(changed,self.record))

if __name__=='__main__':unittest.main()

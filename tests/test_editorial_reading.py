"""Editorials stay usable without borrowing the studies they discuss."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_readings import make_note
from condense_readings import annotate
from compose_issue import evidence


class EditorialReadingTests(unittest.TestCase):
    def test_actual_editorial_survives_reading_and_synthesis_boundary(self):
        rows=json.loads((ROOT/'data/library.json').read_text())
        row=next(x for x in rows if x.get('doi')=='10.3389/feduc.2026.1997466')
        row={**row,'reading':make_note(row)}
        row=annotate(row)
        reading=row['reading']
        self.assertEqual(reading['research_type'],'editorial')
        self.assertEqual(reading['findings'],'')
        self.assertEqual(reading['sample'],'')
        self.assertFalse(reading['reported_findings'])
        self.assertEqual(reading['digest']['finding'],'')
        argument=reading['digest']['longform']
        self.assertIn('Danny Glick',argument['thesis'])
        self.assertIn('planning',argument['reasoning'])
        self.assertIn('Hong Kong',argument['examples'])
        for field in ('thesis','reasoning','examples'):
            self.assertNotIn(argument[field],row['abstract_text'])
        packet=evidence([row])
        self.assertEqual(len(packet),1)
        self.assertEqual(packet[0]['level'],'abstract')
        self.assertEqual(packet[0]['research_type'],'editorial')

    def test_uncurated_editorial_does_not_relabel_passages_as_a_summary(self):
        abstract='A contributor discusses how to give feedback when learners use AI.'
        row={'kind':'scholarly','title':'Editorial: Feedback and learning',
             'doi':'10.1234/feedback','abstract_text':abstract,
             'reading':{'level':'abstract','research_type':'editorial','interpretation':abstract}}
        result=annotate(row)
        self.assertEqual(result['abstract_text'],abstract)
        digest=result['reading']['digest']
        self.assertEqual(digest['status'],'journal_abstract_preview')
        self.assertFalse(digest['interpretation'] or digest['finding'] or digest['explain'])

    def test_title_without_source_material_stays_ineligible(self):
        row={'kind':'scholarly','title':'Editorial: AI learning','doi':'10.1234/editorial'}
        row['reading']=make_note(row)
        self.assertEqual(row['reading']['level'],'citation_only')
        self.assertEqual(evidence([row]),[])

    def test_ordinary_study_keeps_actual_results(self):
        row={'kind':'scholarly','title':'An experiment with learning tools',
             'abstract_text':'We recruited 100 students for a randomized experiment. Results showed that retrieval practice improved test accuracy in the sample.'}
        reading=make_note(row)
        self.assertIn('improved test accuracy',reading['findings'])
        self.assertNotEqual(reading['research_type'],'editorial')


if __name__=='__main__':unittest.main()

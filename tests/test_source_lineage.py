"""Verified research–commentary lineage and conceptual evidence classification."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import source_lineage
import build_readings
import build_public
import condense_readings

ARTICLE="https://theconversation.com/are-you-using-ai-to-study-heres-how-to-do-it-well-294453"
DOI="10.3390/educsci16081291"


def explainer():
    return {"title":"Are you using AI to study? Here’s how to do it well",
            "kind":"nonacademic","doi":"","url":ARTICLE,"published":"2026-10-21",
            "venue":"The Conversation","lane":"AI & cognition",
            "reading":{"level":"curated","overview":"Think before relying on AI when studying."}}


class SourceLineageTests(unittest.TestCase):
    def test_index_original_and_attach_commentary_once(self):
        data=[explainer()]
        source_lineage.prepare(data)
        source_lineage.prepare(data)
        papers=[x for x in data if x.get("doi")==DOI]
        self.assertEqual(len(papers),1)
        self.assertEqual(papers[0]["research_type"],"conceptual_framework")
        self.assertEqual(data[0]["companion_to"],DOI)
        self.assertIn("Author-written",data[0]["companion_relation"])
        self.assertNotIn("analysis",papers[0]) # No pretend full-text extraction.

    def test_no_inference_from_topic_or_author(self):
        data=[{"kind":"nonacademic","title":"An AI learning guide by Luke Rowe",
               "url":"https://example.org/not-the-original-article"}]
        source_lineage.prepare(data)
        self.assertEqual(len(data),1)
        self.assertNotIn("companion_to",data[0])

    def test_conceptual_is_not_empirical_finding(self):
        rows=[explainer()]
        source_lineage.prepare(rows)
        paper=next(x for x in rows if x.get("doi")==DOI)
        note=build_readings.make_note(paper)
        self.assertEqual(note["level"],"abstract")
        self.assertEqual(note["findings"],"")
        self.assertFalse(note["reported_findings"])
        paper["reading"]=note
        digest=condense_readings.annotate(paper)["reading"]["digest"]
        self.assertEqual(digest["status"],"conceptual_framework")
        self.assertEqual(digest["finding"],"")
        self.assertIn("AI",digest["idea"])

    def test_weekly_has_one_primary_and_preserves_legacy_route_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/"library.json").write_text(json.dumps([explainer()]))
            (folder/"weekly.json").write_text(json.dumps({
                "run":{"date":"2026-10-22","total":1}, "items":[explainer()]}))
            with patch.object(build_public,"DATA",folder):
                library,week=build_public.build()
            primary=next(x for x in library if x.get("doi")==DOI)
            companion=next(x for x in library if x.get("url")==ARTICLE)
        self.assertTrue(primary["reading"]["digest"]["status"]=="conceptual_framework")
        self.assertEqual(companion["companion_to"],DOI)
        self.assertEqual(week["run"]["total"],1)
        self.assertEqual(week["run"]["companion_count"],1)
        self.assertEqual(len(week["items"]),1)
        self.assertEqual(week["items"][0]["doi"],DOI)


if __name__=="__main__":
    unittest.main()

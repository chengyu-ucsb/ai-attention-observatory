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
from publication_fixtures import article_covers_ready
import condense_readings
from collection_window import window_metadata

ARTICLE="https://theconversation.com/are-you-using-ai-to-study-heres-how-to-do-it-well-294453"
DOI="10.3390/educsci16081291"


def reviewed_headlines(folder):
    # These lineage fixtures use real source metadata; retain the corresponding
    # reviewed title so the independent heading gate does not hold the primary.
    registered=json.loads((ROOT/"data/reading-headlines.json").read_text())
    (folder/"reading-headlines.json").write_text(json.dumps({
        key:registered[key] for key in (DOI,ARTICLE) if key in registered}))


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

    def test_older_primary_stays_out_of_weekly_but_preserves_legacy_route_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            reviewed_headlines(folder)
            (folder/"library.json").write_text(json.dumps([explainer()]))
            (folder/"weekly.json").write_text(json.dumps({
                "run":{"date":"2026-10-22","total":1}, "items":[explainer()]}))
            with patch.object(build_public,"DATA",folder), article_covers_ready():
                library,week=build_public.build()
            primary=next(x for x in library if x.get("doi")==DOI)
            companion=next(x for x in library if x.get("url")==ARTICLE)
        self.assertTrue(primary["reading"]["digest"]["status"]=="conceptual_framework")
        self.assertEqual(companion["companion_to"],DOI)
        self.assertEqual(week["run"]["total"],1)
        self.assertEqual(week["run"]["companion_count"],1)
        self.assertEqual(week["items"], [])
        self.assertEqual(week['run']['publication_window'], window_metadata('2026-10-22'))

    def test_queued_display_title_cannot_break_a_verified_companion_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            register = json.loads((ROOT / "data/reading-headlines.json").read_text())
            (folder / "reading-headlines.json").write_text(json.dumps({DOI: register[DOI]}))
            source = dict(explainer(), title="A detailed discussion of handling AI study aids in a classroom while maintaining student autonomy")
            (folder / "library.json").write_text(json.dumps([source]))
            (folder / "weekly.json").write_text(json.dumps({"run": {}, "items": [source]}))
            with patch.object(build_public, "DATA", folder), article_covers_ready():
                public, weekly = build_public.build()
            companion = next(x for x in public if x.get("companion_to") == DOI)
            self.assertEqual(companion["title"], source["title"])
            self.assertEqual(companion["display_headline"], "Read the article in The Conversation")
            self.assertEqual(weekly["run"]["total"], 1)
            self.assertEqual(json.loads((folder / "headline-review-queue.json").read_text())["items"][0]["id"], ARTICLE)

    def test_eligible_primary_and_explainer_count_once(self):
        config = source_lineage.load()
        primary = next(x for x in config['primary_publications'] if x['doi'] == DOI)
        primary.update(published='2026-10-20', historical_backfill=False, publication_date_provenance={
            'status': 'day_known', 'source': 'Crossref publisher metadata',
            'field': 'published-online', 'value': '2026-10-20'})
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            reviewed_headlines(folder)
            (folder / 'library.json').write_text(json.dumps([explainer()]))
            (folder / 'weekly.json').write_text(json.dumps({
                'run': {'date': '2026-10-26'}, 'items': [explainer()]}))
            with patch.object(build_public, 'DATA', folder), patch.object(source_lineage, 'load', return_value=config), article_covers_ready():
                library, week = build_public.build()
        self.assertEqual(week['run']['total'], 1)
        self.assertEqual(week['run']['companion_count'], 1)
        self.assertEqual([x['doi'] for x in week['items']], [DOI])
        self.assertEqual(sum(x.get('companion_to') == DOI for x in library), 1)


if __name__=="__main__":
    unittest.main()


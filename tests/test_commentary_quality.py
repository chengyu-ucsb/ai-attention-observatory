"""Shallow RSS entries must never masquerade as full analytical readings."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_public
import editorial_source_reviews
import news_quality
from condense_readings import annotate
from enrich_deep_readings import refreshable

KILL="https://theconversation.com/why-calling-for-a-kill-switch-is-the-wrong-way-to-think-about-reining-in-ai-293329"
THIN="https://theconversation.com/what-happens-to-language-when-machines-start-talking-back-293554"

def feed(url,title,overview):
    return {"kind":"nonacademic","source":"Publisher RSS / Google News RSS",
            "url":url,"title":title,"preview":overview,
            "content_access":"feed_description","published":"2026-10-19",
            "venue":"The Conversation","first_seen":"2026-10-23",
            "lane":"Technology & society",
            "reading":{"level":"curated","overview":overview}}

class EditorialIntegrityTests(unittest.TestCase):
    def test_full_source_review_is_specific_grounded_and_idempotent(self):
        item=feed(KILL,"Why calling for a ‘kill switch’ is the wrong way to think about reining in AI",
                  "A kill switch may not be a sufficient way to control advanced AI. Infrastructure and people are part of the story.")
        editorial_source_reviews.apply([item])
        editorial_source_reviews.apply([item])
        d=annotate(item)["reading"]["digest"]
        self.assertEqual(d["status"],"edited_perspective")
        self.assertEqual(d["longform"]["source_depth"],"read_article")
        self.assertIn("distributed infrastructure",d["longform"]["thesis"])
        self.assertIn("black box",d["longform"]["reasoning"])
        self.assertIn("Hugging Face",d["longform"]["examples"])
        self.assertIn("Emergency interruption",d["longform"]["tension"])
        self.assertTrue(news_quality.substantive_article(annotate(item)))
        self.assertFalse(refreshable(item,"2026-10-23"))
        self.assertEqual(item["url"],KILL)
        self.assertIn("inkl.com",item["source_review"]["source_url"])

    def test_long_rss_description_is_still_not_analysis(self):
        item=feed(THIN,"What happens to language when machines start talking back?",
                  "Researchers discuss whether the rise of interactive AI will alter communication, dialogue, human identity, social relations, and the roles of speakers and listeners in a rapidly changing media environment.")
        p=annotate(item)
        self.assertGreater(len(item["reading"]["overview"]),90)
        self.assertEqual(p["reading"]["digest"]["longform"]["source_depth"],"publisher_synopsis")
        self.assertFalse(news_quality.substantive_article(p))

    def test_companion_is_kept_as_related_work_not_independent_study(self):
        parent=feed(THIN,"An explanation of a primary source","This is commentary on a research paper.")
        parent["companion_to"]="10.1111/example"
        self.assertTrue(news_quality.substantive_article(parent))

    def test_projection_retains_deep_link_for_unread_source_but_not_research_count(self):
        reviewed=feed(KILL,"Why calling for a ‘kill switch’ is the wrong way to think about reining in AI",
                      "A kill switch is not a substitute for infrastructure and oversight.")
        shallow=feed(THIN,"What happens to language when machines start talking back?",
                     "A published commentary discusses how AI changes the relationship between speakers, listeners and conversation.")
        rows=[reviewed,shallow]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"library.json").write_text(json.dumps(rows))
            (root/"weekly.json").write_text(json.dumps({"run":{},"items":rows}))
            with patch.object(build_public,"DATA",root):
                selected,week=build_public.build()
            pending=json.loads((root/"public-pending-sources.json").read_text())
            audit=json.loads((root/"source-quality-audit.json").read_text())
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]["url"],KILL)
        self.assertEqual(len(week["items"]),1)
        self.assertEqual(len(pending),1)
        self.assertEqual(pending[0]["url"],THIN)
        self.assertEqual(pending[0]["source_quality"]["decision"],"awaiting_full_article_reading")
        self.assertEqual(audit["journalism_awaiting_reading"],1)
        self.assertNotIn("reading",pending[0]) # no fake excerpts on the fallback page

    def test_later_weekly_discovery_retains_source_checked_essay(self):
        # The original article is policy/rhetoric-focused, so the older
        # keyword-only eligibility test would have deleted it every Monday.
        import discover_editorial as ed
        row=feed(KILL,"Why calling for a ‘kill switch’ is the wrong way to think about reining in AI",
                 "A kill switch makes control of AI look like a simple emergency button.")
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"library.json").write_text(json.dumps([row]))
            (root/"weekly.json").write_text(json.dumps({"run":{},"items":[]}))
            with patch.object(ed,"DIR",root),patch.object(ed,"FEEDS",[]),patch.object(ed,"GOOGLE_SEARCHES",[]):
                ed.run()
            retained=json.loads((root/"library.json").read_text())
        self.assertEqual(len(retained),1)
        self.assertEqual(retained[0]["url"],KILL)
        self.assertIn("black box",retained[0]["source_review"]["reasoning"])

    def test_deep_source_analysis_must_have_examples_and_tension(self):
        row=feed(THIN,"An analysis of AI","An article argues that automation reshapes our cognitive priorities.")
        row["deep_analysis"]={"kind":"nonacademic","source_depth":"source_html",
                              "thesis":"The author makes a general point about attention and AI systems in society.",
                              "reasoning":"A"*220,"examples":"","tension":"","qualification":"This is a viewpoint.","basis":"source HTML"}
        self.assertFalse(news_quality.substantive_article(annotate(row)))

if __name__=="__main__":
    unittest.main()

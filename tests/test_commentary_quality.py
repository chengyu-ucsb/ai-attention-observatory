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
from publication_fixtures import article_covers_ready
import editorial_source_reviews
import news_quality
from condense_readings import annotate
from compose_issue import evidence
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
            with patch.object(build_public,"DATA",root), article_covers_ready():
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

    def test_scope_uses_the_checked_argument_not_examples_or_editorial_labels(self):
        family = {"kind": "nonacademic", "title": "A shared family safety plan",
                  "lane": "AI & cognition", "source_quality": {"decision": "include"},
                  "preview": "Read more about artificial intelligence and human attention.",
                  "reading": {"digest": {"longform": {
                      "thesis": "Families can agree on a plan to protect children's privacy online.",
                      "examples": "Examples include push notifications, autoplay and attention capture."}}}}
        self.assertIsNone(news_quality.commentary_topic(family))
        article = family["reading"]["digest"]["longform"]
        article["thesis"] = "The authors found that batching notifications reduced interruptions at work."
        self.assertEqual(news_quality.commentary_topic(family), "adjacent")
        article["thesis"] = "Clinicians using AI on hospital wards describe alert fatigue."
        self.assertEqual(news_quality.commentary_topic(family), "direct")
        article["thesis"] = "The report draws attention to growing revenue for self-attention model chips."
        self.assertIsNone(news_quality.commentary_topic(family))
        for subject in ("Prices rose after supply interruptions at the refinery.",
                        "The AI model achieves faster reasoning on a benchmark."):
            article["thesis"] = subject
            self.assertIsNone(news_quality.commentary_topic(family))

    def test_checked_explanation_can_clarify_the_buyers_role(self):
        url = "https://www.techpolicy.press/when-an-ai-agent-says-i-agree-whos-consenting/"
        rows = json.loads((ROOT / "data/library.json").read_text())
        record = next(row for row in rows if row.get("url") == url)
        reviewed = editorial_source_reviews.apply([record])[0]
        reviewed["source_review"]["thesis"] = (
            "An AI shopping assistant clicks to buy something. What shows that the buyer "
            "authorized that particular purchase and what can the merchant check?")
        published = annotate(reviewed)
        self.assertEqual(news_quality.commentary_topic(published), "direct")
        published["source_review"]["reasoning"] = "Companies build commercial platforms for online sales."
        self.assertIsNone(news_quality.commentary_topic(published))
        published["source_review"]["reasoning"] = "A buyer delegates a spending decision to the software."
        published["reading"]["digest"]["longform"]["thesis"] = (
            "The AI chip manufacturer announced new quarterly revenue targets.")
        self.assertIsNone(news_quality.commentary_topic(published))

    def test_official_feature_name_supports_a_plain_language_guide(self):
        rows = json.loads((ROOT / "data/library.json").read_text())
        apple = next(row for row in rows if row.get("url") ==
                     "https://developer.apple.com/documentation/appintents/focus/")
        published = annotate(apple)
        self.assertEqual(news_quality.commentary_topic(published), "adjacent")
        published["source"] = "Publisher RSS / Google News RSS"
        self.assertIsNone(news_quality.commentary_topic(published))

    def test_real_family_article_stays_private_on_rebuild_and_in_stale_issue_input(self):
        publication = json.loads((ROOT / 'data/original-readings.json').read_text())['articles']
        notes = {n['id']: n for n in publication if n['id'].startswith('checked-eff-')}
        library = json.loads((ROOT / 'data/library.json').read_text())
        urls = {n['record_url'] for n in notes.values()}
        rows = [r for r in library if r.get('url') in urls]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"library.json").write_text(json.dumps(rows))
            (root/"weekly.json").write_text(json.dumps({"run":{},"items":rows}))
            with patch.object(build_public,"DATA",root), article_covers_ready():
                selected,week=build_public.build()
            audit=json.loads((root/"source-quality-audit.json").read_text())
            pending=json.loads((root/"public-pending-sources.json").read_text())
        family=notes['checked-eff-parenting-2026-10-29']['record_url']
        self.assertEqual({r["url"] for r in selected}, urls - {family})
        self.assertEqual({r["url"] for r in week["items"]}, urls - {family})
        self.assertEqual({r["source_group"] for r in selected}, {"AI-specific"})
        self.assertEqual(audit["withheld_by_reason"]["commentary_outside_editorial_scope"], 1)
        self.assertFalse(any(r["url"]==family for r in pending))
        raw=next(r for r in rows if r["url"]==family)
        self.assertEqual(evidence([raw]), [])

    def test_human_practice_and_control_are_distinct_from_generic_ai_mentions(self):
        row = {"kind": "nonacademic", "title": "AI and society",
               "reading": {"digest": {"longform": {}}}}
        thesis = row["reading"]["digest"]["longform"]
        for argument in (
            "An AI tutor may leave teenagers fewer opportunities to develop their own judgments.",
            "The guide asks when AI can support a developing skill and when it can displace practice.",
            "Schools ask whether students can access search without enabling AI features.",
            "A review of generative AI in education examines the limits of evidence available to schools.",
        ):
            with self.subTest(argument=argument):
                thesis["thesis"] = argument
                self.assertEqual(news_quality.commentary_topic(row), "direct")
        for argument in (
            "Families can develop a plan to protect children's online privacy.",
            "Families can develop their own skills to protect children's online privacy.",
            "Schools ask families to review passwords and account security.",
            "The company expanded access to AI models with faster inference speed.",
            "The supplier forecasts growing sales of AI chips to schools.",
        ):
            with self.subTest(argument=argument):
                thesis["thesis"] = argument
                thesis["examples"] = "One example discusses AI tutors and independent judgments."
                self.assertIsNone(news_quality.commentary_topic(row))

    def test_ai_headline_cannot_relabel_an_adjacent_attention_argument(self):
        row = {"kind": "nonacademic", "title": "Living in an AI age",
               "reading": {"digest": {"longform": {
                   "thesis": "Workers can batch notifications to reduce interruptions during focused work."}}}}
        self.assertEqual(news_quality.commentary_topic(row), "adjacent")
        row["reading"]["digest"]["longform"]["thesis"] = (
            "An automated agent can make choices on a person's behalf, complicating meaningful consent.")
        self.assertEqual(news_quality.commentary_topic(row), "direct")

    def test_current_correction_sources_survive_fresh_public_projection(self):
        """The real reviewed issue must rebuild after the relevance gate changes."""
        import build_issue
        date = "2026-11-16"
        packet = json.loads((ROOT / 'data/edition-corrections' / (date + '.json')).read_text())
        library = json.loads((ROOT / 'data/library.json').read_text())
        additions = {entry['source']['id'] for entry in packet['reviewed_additions']}
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / 'library.json').write_text(json.dumps(library))
            (data / 'weekly.json').write_text(json.dumps({"run": {}, "items": library}))
            (data / 'reading-headlines.json').write_text((ROOT / 'data/reading-headlines.json').read_text())
            for folder in ('approved-issues', 'edition-corrections'):
                (data / folder).mkdir()
                (data / folder / (date + '.json')).write_text((ROOT / 'data' / folder / (date + '.json')).read_text())
            (data / 'issue-editorial.json').write_text((ROOT / 'data/issue-editorial.json').read_text())
            with patch.object(build_public, 'DATA', data), article_covers_ready():
                selected, _ = build_public.build()
            public_ids = {build_public.record_id(row) for row in selected}
            self.assertTrue(additions <= public_ids, additions - public_ids)
            for row in selected:
                if row.get('kind') == 'nonacademic' and build_public.record_id(row) in additions:
                    self.assertEqual(news_quality.commentary_topic(row), 'direct')
            with patch.object(build_issue, 'DATA', data):
                issue = build_issue.build(date, reviewed_correction=True, check_only=True)
            self.assertEqual(issue['source_count'], len(packet['baseline_source_ids']) + len(additions))
            self.assertEqual({row['id'] for row in issue['sources']}, set(packet['baseline_source_ids']) | additions)
            self.assertFalse((data / 'public-issue.json').exists())

    def test_deep_source_analysis_must_have_examples_and_tension(self):
        row=feed(THIN,"An analysis of AI","An article argues that automation reshapes our cognitive priorities.")
        row["deep_analysis"]={"kind":"nonacademic","source_depth":"source_html",
                              "thesis":"The author makes a general point about attention and AI systems in society.",
                              "reasoning":"A"*220,"examples":"","tension":"","qualification":"This is a viewpoint.","basis":"source HTML"}
        self.assertFalse(news_quality.substantive_article(annotate(row)))

if __name__=="__main__":
    unittest.main()

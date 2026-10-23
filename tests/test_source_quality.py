"""Article authenticity and scholarly publication triage regression tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import news_quality
import source_quality
import editorial_corrections
import build_public
import build_readings

TITLE="Faster! Louder! Brighter! How the attention economy overwhelmed children’s TV - The Guardian"
GOOGLE="https://news.google.com/rss/articles/abcdef?oc=5"

class NewsIntegrityTests(unittest.TestCase):
 def test_google_news_headline_is_not_article_synopsis(self):
  self.assertFalse(news_quality.useful_description(TITLE,TITLE))
  self.assertFalse(news_quality.useful_description(TITLE,TITLE+" The Guardian"))
  self.assertFalse(news_quality.publisher_url(GOOGLE))
  self.assertFalse(news_quality.substantive_article({
   "kind":"nonacademic","source":"Publisher RSS / Google News RSS",
   "title":TITLE,"url":GOOGLE,
   "reading":{"level":"curated","overview":TITLE}}))

 def test_real_publisher_synopsis_is_distinguishable(self):
  desc="A group of educators examines how learners decide when to use AI and when to do the reasoning themselves, exploring support and independent thinking."
  self.assertTrue(news_quality.useful_description("How to study with AI",desc))
  self.assertTrue(news_quality.publisher_url("https://theconversation.com/research-article"))

 def test_guardian_correction_has_original_url_and_source_analysis(self):
  rows=[{"kind":"nonacademic","title":TITLE,"venue":"The Guardian",
         "url":GOOGLE,"source":"Publisher RSS / Google News RSS",
         "reading":{"level":"curated","overview":TITLE}}]
  editorial_corrections.apply(rows)
  editorial_corrections.apply(rows)
  paper=rows[0]
  self.assertEqual(paper["authors"],["Natalia Kucirkova"])
  self.assertIn("/news/2026/sep/17/",paper["url"])
  from condense_readings import annotate
  self.assertTrue(news_quality.substantive_article(annotate(paper)))
  self.assertIn("pace",paper["reading"]["overview"])
  self.assertIn("not an experiment",paper["editorial_notes"]["caveat"])
  self.assertNotIn("news.google.com",paper["url"])
  self.assertIn(GOOGLE,paper.get("legacy_urls",[]))

 def test_headline_only_cannot_survive_as_existing_reading(self):
  row={"kind":"nonacademic","title":TITLE,"venue":"The Guardian",
       "source":"Publisher RSS / Google News RSS","preview":TITLE,
       "reading":{"level":"curated","overview":TITLE}}
  self.assertEqual(build_readings.make_note(row)["level"],"citation_only")


class QualityScreenTests(unittest.TestCase):
 def study(self,venue="Computers in Human Behavior", title="Generative AI use and cognitive offloading in learning"):
  return {"kind":"scholarly","title":title,"venue":venue,
          "abstract_text":"This study investigates generative AI and its relation to critical thinking, metacognitive monitoring, and cognitive offloading among students."}

 def test_field_venues_are_strong_prior_not_study_quality_certificates(self):
  x=source_quality.screen(self.study())
  self.assertEqual(x["decision"],"include")
  self.assertEqual(x["venue_level"],"priority")
  self.assertEqual(source_quality.screen(self.study("Frontiers in Psychology"))["venue_level"],"specialist")

 def test_metadata_provider_is_not_journal(self):
  self.assertEqual(source_quality.screen(self.study("Crossref"))["reason"],"publication_venue_unverified")
  self.assertEqual(source_quality.screen(self.study("OpenAlex"))["decision"],"hold")

 def test_preprint_must_be_reviewed(self):
  self.assertEqual(source_quality.screen(self.study("arXiv (Cornell University)"))["reason"],"preprint_requires_article_screen")

 def test_engineering_cross_attention_is_not_human_attention(self):
  x=self.study("Scientific Reports","GRU TabTransformer with cross-attention for image classification")
  x["abstract_text"]="The proposed model improves classification accuracy on an image dataset."
  self.assertEqual(source_quality.screen(x)["reason"],"computational_attention_not_human_attention")

 def test_venue_alone_does_not_override_weak_topic_match(self):
  x=self.study("Journal of Communication","A history of local radio policy")
  x["abstract_text"]="This piece examines public broadcasting licensing and regulatory institutions."
  self.assertEqual(source_quality.screen(x)["decision"],"hold")

 def test_manual_original_paper_is_preserved(self):
  x=self.study("Education Sciences","From Gradual Release of Responsibility to Gradual Release of Technology")
  x["source"]="Publisher article and abstract (editorially verified)"
  x["research_type"]="conceptual_framework"
  self.assertEqual(source_quality.screen(x)["decision"],"include")


if __name__=="__main__":
 unittest.main()

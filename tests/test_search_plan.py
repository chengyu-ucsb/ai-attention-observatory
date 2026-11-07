"""Search strategy and the distinction between core AI findings and foundations."""
import datetime as dt
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from search_plan import plan,source_class,LANES
from enrich import extract_sections
from enrich_openalex_fulltext import extract as extract_grobid,eligible as grobid_eligible

class SearchScopeTests(unittest.TestCase):
 def test_history_backfill_covers_every_early_year_across_four_themes(self):
  tasks=plan(dt.date(2026,10,21),"backfill")
  self.assertGreaterEqual(len(tasks),28)
  for theme in LANES:
   for year in (2023,2024,2025):
    matches=[x for x in tasks if x[0]==theme and x[4]==f"historical:{year}"]
    self.assertEqual(len(matches),2 if year in (2023,2024) else 1,(theme,year))
  self.assertTrue(all(start<=end for _,_,start,end,_ in tasks))
  self.assertTrue(all(start[:4]>="2023" for _,_,start,_,_ in tasks))

 def test_weekly_run_only_searches_previous_completed_publication_week(self):
  for day in range(2,9):
   tasks=plan(dt.date(2026,11,day),"weekly")
   self.assertEqual(len(tasks),sum(len(q) for q in LANES.values()))
   self.assertEqual({t[0] for t in tasks},set(LANES))
   self.assertTrue(all(t[2:]==("2026-10-26","2026-11-01","previous_publication_week") for t in tasks))
  self.assertTrue(all(t[2:4]==("2026-11-02","2026-11-08") for t in plan("2026-11-09")))

 def test_older_attention_foundation_cannot_be_called_genai_study(self):
  old={"title":"The cost of interrupted work: More speed and stress","published":"2008-04-06"}
  self.assertEqual(source_class(old),"Earlier digital-attention foundation")
  ai={"title":"ChatGPT effects on cognitive skills of undergraduate students","published":"2024-06-01"}
  self.assertEqual(source_class(ai),"AI-specific")
  adjacent={"title":"Smartphone notifications and sustained attention","published":"2025-03-01"}
  self.assertEqual(source_class(adjacent),"Adjacent digital-attention evidence")

 def test_europe_pmc_full_text_sections_preserve_multiple_paragraphs(self):
  root=ET.fromstring("<article><body><sec><title>Methods</title>"
   "<p>We recruited 125 university participants to complete a comparative study of generative AI learning conditions.</p>"
   "<p>Participants completed two repeated tasks using guided support and unassisted working conditions.</p></sec>"
   "<sec><title>Results</title>"
   "<p>The analyses revealed associations between repeated offloading and reported confidence in independent performance.</p>"
   "<p>Participants also described variation in how they verified computer-generated answers and reflected on the task.</p>"
   "</sec></body></article>")
  parts=extract_sections(root)
  self.assertIn("125 university participants",parts["methods"])
  self.assertIn("two repeated tasks",parts["methods"])
  self.assertIn("verified computer-generated answers",parts["results"])

 def test_openalex_full_text_long_results_are_not_cut_at_1100_characters(self):
  p="Participants showed associations between AI reliance and reasoning quality under the intervention setting. "
  xml="<TEI><text><body><div><head>Results</head>"+("<p>"+p+"</p>")*20+"</div></body></text></TEI>"
  sections=extract_grobid(ET.fromstring(xml))
  self.assertGreater(len(sections["results"]),1100)
  self.assertLessEqual(len(sections["results"]),4500)

 def test_old_retry_queue_is_revisited_once_after_pipeline_improvement(self):
  item={"kind":"scholarly","doi":"10.1016/sample","fulltext_attempt":{"status":"waiting_for_license","next_at":"2026-12-01T00:00:00+00:00","attempts":1}}
  self.assertTrue(grobid_eligible(item,dt.datetime(2026,10,21,tzinfo=dt.timezone.utc)))
  item["fulltext_attempt"]["pipeline_version"]=3
  self.assertFalse(grobid_eligible(item,dt.datetime(2026,10,21,tzinfo=dt.timezone.utc)))

if __name__=="__main__":unittest.main()


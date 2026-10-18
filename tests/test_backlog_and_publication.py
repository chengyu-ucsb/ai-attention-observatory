"""Source-backed publication and full-text queue regression tests (offline)."""
import datetime
import json
import os
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_public
import enrich_openalex_fulltext as fulltext

class PublicReadingTests(unittest.TestCase):
 def test_citation_only_never_published(self):
  self.assertFalse(build_public.readable({"kind":"scholarly","doi":"10.1000/sample","reading":{"level":"citation_only"}}))
  self.assertFalse(build_public.readable({"kind":"nonacademic","reading":{"level":"citation_only"},"preview":"A headline"}))
 def test_scholarly_curated_title_is_not_evidence(self):
  self.assertFalse(build_public.readable({"kind":"scholarly","reading":{"level":"curated","overview":"A source-free blurb"}}))
 def test_actual_abstract_or_fulltext_is_source_backed(self):
  self.assertTrue(build_public.readable({"kind":"scholarly","abstract_text":"a"*120,"reading":{"level":"abstract"}}))
  self.assertTrue(build_public.readable({"kind":"scholarly","analysis":{"fulltext_url":"https://example.org/oa"},"reading":{"level":"full_text"}}))
 def test_publisher_synopsis_requires_content(self):
  self.assertTrue(build_public.readable({"kind":"nonacademic","reading":{"level":"curated","overview":"Editorial synopsis from its source"}}))
  self.assertFalse(build_public.readable({"kind":"nonacademic","reading":{"level":"curated"}}))
 def test_projection_excludes_citations_from_counts_and_week(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=pathlib.Path(tmp)
   rows=[
    {"kind":"scholarly","title":"Report","doi":"10.1/report","abstract_text":"a"*140,"reading":{"level":"abstract","overview":"Overview"}},
    {"kind":"scholarly","title":"Citation","doi":"10.1/cite","reading":{"level":"citation_only"}}]
   (folder/"library.json").write_text(json.dumps(rows))
   (folder/"weekly.json").write_text(json.dumps({"run":{"total":2},"items":rows}))
   with patch.object(build_public,"DATA",folder):
    public,weekly=build_public.build()
   self.assertEqual(len(public),1)
   self.assertEqual(len(weekly["items"]),1)
   self.assertEqual(weekly["run"]["total"],1)
   self.assertEqual(weekly["run"]["last_seven_days"],1)

class FullTextQueueTests(unittest.TestCase):
 def test_429_pauses_resumable_queue_without_consuming_all_papers(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp)
   items=[{"kind":"scholarly","doi":"10.1000/one","title":"AI attention study"},{"kind":"scholarly","doi":"10.1000/two","title":"AI cognition study"}]
   lib=p/"library.json";status=p/"fulltext-backfill-state.json"
   lib.write_text(json.dumps(items))
   err=urllib.error.HTTPError("https://api.openalex.org",429,"Too Many Requests",{"X-RateLimit-Reset":"7200"},None)
   with patch.object(fulltext,"LIB",lib),patch.object(fulltext,"STATE",status),patch.dict(os.environ,{"OPENALEX_API_KEY":"sample-key"}),patch.object(fulltext,"get",side_effect=err) as get:
    first=fulltext.run()
    self.assertEqual(first["attempted"],1)
    self.assertEqual(first["status"],"waiting_for_budget")
    second=fulltext.run()
    self.assertEqual(second["attempted"],0)
    self.assertEqual(get.call_count,1)
   self.assertTrue(status.exists())
   stored=json.loads(lib.read_text())
   self.assertEqual(sum(bool(x.get("fulltext_attempt")) for x in stored),1)
 def test_licensed_xml_becomes_reusable_evidence(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp);lib=p/"library.json";status=p/"fulltext-backfill-state.json"
   lib.write_text(json.dumps([{"kind":"scholarly","doi":"10.1000/three","title":"AI and cognitive attention"}]))
   work={"id":"https://openalex.org/W123","best_oa_location":{"license":"cc-by","landing_page_url":"https://example.org/oa"},"content_urls":{"grobid_xml":"https://content.openalex.org/works/W123.grobid-xml"}}
   xml=b'<TEI><text><body><div><head>Results</head><p>In this experimental comparison, the participants in condition A reported lower distraction than those in condition B.</p></div></body></text></TEI>'
   def fetch(url,key):return (json.dumps(work).encode() if "api.openalex.org" in url else xml),{}
   with patch.object(fulltext,"LIB",lib),patch.object(fulltext,"STATE",status),patch.dict(os.environ,{"OPENALEX_API_KEY":"sample-key"}),patch.object(fulltext,"get",side_effect=fetch):
    result=fulltext.run()
   self.assertEqual(result["extracted_this_run"],1)
   record=json.loads(lib.read_text())[0]
   self.assertIn("lower distraction",record["analysis"]["results"])
   self.assertEqual(record["fulltext_attempt"]["status"],"full_text")

if __name__=="__main__":unittest.main()

"""Offline checks for weekly DOI verification, venue targeting and safety."""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import priority_research as pr
import update
TODAY=dt.date(2026,10,22)
DOI="10.1016/j.compedu.2026.105576"


def work(doi=DOI,venue="Computers & Education",title="The effects of critical thinking intervention on reliance behaviors during human-Generative AI learning"):
 return {"DOI":doi,"title":[title],"type":"journal-article",
         "container-title":[venue],"published":{"date-parts":[[2026,7,1]]},
         "author":[{"given":"Research","family":"Author"}],
         "abstract":"Generative AI collaboration raises questions about cognitive offloading and critical thinking. This experimental intervention evaluates student reliance on AI and problem-solving."}

def manifest():
 return {
  "papers":[{"doi":DOI,"venue":"Computers & Education","lane":"Interventions","research_type":"empirical_intervention",
             "rationale":"Publisher-verified intervention","url":"https://www.sciencedirect.com/science/article/pii/S036013152600014X"}],
  "venue_queries":[{"venue":"Computers & Education","lane":"Interventions","q":"generative AI"}]
 }

class PriorityLiteratureTests(unittest.TestCase):
 def test_seed_is_accepted_only_on_exact_doi_and_venue(self):
  good=pr.crossref_article(work(),lane="Interventions",scope="editorial_priority",query="DOI",today=TODAY,expected_venue="Computers & Education",editor_seed=True)
  self.assertEqual(good["doi"],DOI)
  self.assertFalse(good["curated"])
  self.assertFalse(pr.crossref_article(work(venue="Unknown Review"),lane="Interventions",scope="editorial_priority",query="DOI",today=TODAY,expected_venue="Computers & Education",editor_seed=True))
  self.assertFalse(pr.crossref_article(work(doi=""),lane="Interventions",scope="editorial_priority",query="DOI",today=TODAY,expected_venue="Computers & Education",editor_seed=True))
  future=work();future["published"]["date-parts"]=[[2026,12,1]]
  self.assertIsNone(pr.crossref_article(future,lane="Interventions",scope="editorial_priority",query="DOI",today=TODAY,expected_venue="Computers & Education",editor_seed=True))

 def test_journal_query_rejects_near_match_and_irrelevant_study(self):
  good=work()
  wrong=work(doi="10.1016/j.example.2026.000001",venue="Computers & Education: Other Journal")
  irrelevant=work(doi="10.1016/j.example.2026.000002",title="Thermal performance of refrigeration devices")
  irrelevant["abstract"]="Heating and refrigerant systems were benchmarked in a laboratory."
  result=pr.discover(lambda url:{"message":good} if "/works/10." in url else {"message":{"items":[wrong,irrelevant,good]}},
                     TODAY,manifest=manifest())
  rows,errors,stats=result
  self.assertEqual(len(rows),1) # DOI deduplication across priority and targeted journal
  self.assertEqual(rows[0]["doi"],DOI)
  self.assertEqual(stats["journal_queries_succeeded"],1)
  self.assertEqual(stats["journal_relevant"],0)
  self.assertFalse(errors)

 def test_missing_registry_does_not_manufacture_paper(self):
  rows,errors,stats=pr.discover(lambda url:{"message":{}},TODAY,manifest=manifest())
  self.assertEqual(rows,[])
  self.assertEqual(stats["priority_dois_found"],0)
  self.assertTrue(errors)

 def test_search_has_publication_boundaries_and_venue_parameters(self):
  urls=[]
  def fake(url):
   urls.append(url)
   return {"message":work()} if "/works/10." in url else {"message":{"items":[]}}
  pr.discover(fake,TODAY,manifest=manifest())
  target=next(u for u in urls if "query.container-title" in u)
  params=parse_qs(urlparse(target).query)
  self.assertEqual(params["query.container-title"],["Computers & Education"])
  self.assertIn("until-pub-date:2026-10-22",params["filter"][0])
  self.assertIn("from-pub-date:2026-06-24",params["filter"][0])

 def test_weekly_index_does_not_delete_unverified_old_scholarship(self):
  old={"title":"Unverified journal but promising human attention study","kind":"scholarly",
       "doi":"10.1111/study.2015.111","venue":"Unverified",
       "published":"2015-01-01","first_seen":"2026-10-18"}
  with tempfile.TemporaryDirectory() as tmp:
   dest=Path(tmp)
   (dest/"library.json").write_text(json.dumps([old]))
   with patch.object(update,"DIR",dest),patch.object(update,"TODAY","2026-10-22"),\
        patch.object(update,"discover",return_value=([],[],{"openalex":0,"crossref":0})),\
        patch.object(update,"discover_priority",return_value=([],[],{"priority_dois_requested":0})):
    update.main()
   stored=json.loads((dest/"library.json").read_text())
  self.assertEqual(len(stored),1)
  self.assertEqual(stored[0]["doi"],old["doi"])

if __name__=="__main__":
 unittest.main()

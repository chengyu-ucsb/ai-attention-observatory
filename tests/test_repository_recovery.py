"""Repository-first retrieval must fail closed on licenses, DOI and hosts."""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import enrich_repository_fulltext as repo

class RepositoryRecoveryTests(unittest.TestCase):
 def test_licensed_version_only(self):
  self.assertEqual(repo.license_name("CCBY"),"cc-by")
  self.assertEqual(repo.license_name("CCBYSA"),"cc-by-sa")
  self.assertEqual(repo.license_name("CC BY 4.0"),"cc-by")
  self.assertEqual(repo.license_name("https://creativecommons.org/licenses/by/4.0/"),"cc-by")
  self.assertEqual(repo.license_name("CC0"),"cc0")
  self.assertEqual(repo.license_name("CC BY-NC"),"")
  self.assertEqual(repo.license_name("CC BY-ND 4.0"),"")
  self.assertEqual(repo.license_name(""),"")
  self.assertEqual(repo.license_name("OA"),"")
 def test_no_arbitrary_or_non_https_pdf_fetching(self):
  self.assertTrue(repo.supported_pdf("https://aclanthology.org/2020.acl-main.447.pdf"))
  self.assertFalse(repo.supported_pdf("http://aclanthology.org/paper.pdf"))
  self.assertFalse(repo.supported_pdf("https://127.0.0.1/article.pdf"))
  self.assertFalse(repo.supported_pdf("https://aclanthology.org.evil.test/article.pdf"))
  self.assertFalse(repo.supported_pdf("https://someone:password@aclanthology.org/x.pdf"))
  self.assertFalse(repo.supported_pdf("https://aclanthology.org:444/article.pdf"))
 def test_no_source_is_not_a_full_text(self):
  record={"doi":"10.1000/abc","kind":"scholarly"}
  with patch.object(repo,"pdf_bytes") as get:
   self.assertEqual(repo.recover(record,[],dt.date(2026,10,22)),"no_oa_pdf_reported")
   self.assertEqual(repo.recover(record,[{"url":"https://aclanthology.org/test.pdf","license":None}],dt.date(2026,10,22)),"license_unverified")
   self.assertEqual(repo.recover(record,[{"url":"https://evil.example/test.pdf","license":"CC BY"}],dt.date(2026,10,22)),"pdf_host_unapproved")
   get.assert_not_called()
  self.assertNotIn("analysis",record)
 def test_sections_from_licensed_pdf_only(self):
  row={"doi":"10.1000/paper","kind":"scholarly"}
  loc={"url":"https://aclanthology.org/2020.acl-main.447.pdf","license":"CCBY","provider":"Semantic Scholar"}
  with patch.object(repo,"pdf_bytes",return_value=b"%PDF-1.7 mock"),patch.object(repo,"extract_pdf",
   return_value={"methods":"We recruited 100 participants.","results":"The analysis showed more task switching.",
    "discussion":"This may depend on task complexity."}):
   status=repo.recover(row,[loc],dt.date(2026,10,22))
  self.assertEqual(status,"full_text_recovered")
  self.assertIn("Semantic Scholar",row["analysis"]["provenance"])
  self.assertEqual(row["analysis"]["license"],"cc-by")
  self.assertIn("results",row["analysis"]["sections_available"])
 def test_batch_rejects_wrong_doi_even_if_pdf_is_public(self):
  results=[{"externalIds":{"DOI":"10.1000/notrequested"},"openAccessPdf":{"url":"https://aclanthology.org/a.pdf","license":"CCBY"}},
   {"externalIds":{"DOI":"10.1000/second"},"openAccessPdf":{"url":"https://aclanthology.org/b.pdf","license":"CCBY"}}]
  with patch.object(repo,"metadata_request",return_value=results):
   found=repo.s2_batch(["10.1000/first","10.1000/second"])
  self.assertNotIn("10.1000/first",found)
  self.assertEqual(found["10.1000/second"]["provider"],"Semantic Scholar")
 def test_unpaywall_only_accepts_exact_doi(self):
  with patch.object(repo,"metadata_request",return_value={"doi":"10.1000/wrong","oa_locations":[{"url_for_pdf":"https://aclanthology.org/file.pdf","license":"cc-by"}]}):
   self.assertEqual(repo.unpaywall_doi("10.1000/right"),[])
 def test_retry_queue_and_no_download_when_license_missing(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"library.json"
   path.write_text(json.dumps([{"kind":"scholarly","doi":"10.1000/paper","title":"Attention study"}]))
   with patch.object(repo,"LIB",path),patch.object(repo,"s2_batch",
       return_value={"10.1000/paper":{"url":"https://aclanthology.org/paper.pdf",
       "license":"","provider":"Semantic Scholar"}}),patch.object(repo,"unpaywall_doi",return_value=[]),patch.object(repo,"pdf_bytes") as download,patch.object(repo.time,"sleep"):
    stats=repo.run()
   self.assertEqual(stats["license_unverified"],1)
   self.assertEqual(stats["fulltexts_recovered"],0)
   self.assertNotIn("analysis",json.loads(path.read_text())[0])
   download.assert_not_called()
 def test_missing_api_does_not_abort_alternative_provider(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"library.json"
   path.write_text(json.dumps([{"kind":"scholarly","doi":"10.1000/paper","title":"Attention study"}]))
   with patch.object(repo,"LIB",path),patch.object(repo,"s2_batch",side_effect=ValueError("rate limit")):
    with patch.object(repo,"unpaywall_doi",return_value=[]),patch.object(repo.time,"sleep"):
     result=repo.run()
   self.assertEqual(result["no_oa_pdf_reported"],1)
 def test_retry_waits_for_due_date(self):
  row={"kind":"scholarly","doi":"10.1000/test"}
  t=dt.date(2026,10,22)
  repo.checkpoint(row,"license_unverified",30,t)
  self.assertFalse(repo.eligible(row,t))
  self.assertTrue(repo.eligible(row,t+dt.timedelta(days=30)))

if __name__=="__main__":unittest.main()

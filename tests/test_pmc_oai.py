"""Official PMC fallback and richer XML coverage; no network calls in tests."""
import datetime as dt
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import enrich_pmc_oai as pmc
import enrich_openalex_fulltext as alex
import enrich as epmc

def body(license_uri="https://creativecommons.org/licenses/by/4.0/"):
 return (f'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
         f'<GetRecord><record><metadata><article xmlns="http://jats.nlm.nih.gov" '
         f'xmlns:xlink="http://www.w3.org/1999/xlink">'
         f'<front><article-meta><permissions><license xlink:href="{license_uri}">'
         f'<license-p>Available with attribution.</license-p></license></permissions></article-meta></front>'
         f'<body><sec><title>Methods</title><p>We surveyed 310 participants about generative AI habits and how they managed distractions during everyday work.</p></sec>'
         f'<sec><title>Results</title><p>More frequent interruptions were associated with lower self-reported ability to sustain attention during work.</p></sec>'
         f'<sec><title>Discussion</title><p>The pattern may be related to work context and independent learning practices, but directionality is not established.</p></sec>'
         f'</body></article></metadata></record></GetRecord></OAI-PMH>').encode()

class PMCOAITests(unittest.TestCase):
 def test_namespaced_reusable_full_text_preserves_method_and_result(self):
  result,error=pmc.jats_and_rights(body())
  self.assertIsNone(error)
  self.assertIn("310 participants",result["sections"]["methods"])
  self.assertIn("lower self-reported ability",result["sections"]["results"])
  self.assertIn("directionality",result["sections"]["discussion"])
 def test_rights_and_missing_sections_fail_closed(self):
  for uri in ("https://creativecommons.org/licenses/by-nc/4.0/",
              "https://creativecommons.org/licenses/by-nd/4.0/",
              "https://some-publisher.org/copyright"):
   info,error=pmc.jats_and_rights(body(uri))
   self.assertIsNone(info);self.assertEqual(error,"reuse_license_not_verified")
  self.assertEqual(pmc.jats_and_rights(b"<OAI-PMH><error code='cannotDisseminateFormat'>no</error></OAI-PMH>")[1],
                   "oai_no_reusable_record")
 def test_no_pmc_identifier_gets_backoff_without_false_full_text(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"library.json"
   rows=[{"kind":"scholarly","title":"New focus study","doi":"10.1000/not-in-pmc","abstract_text":"Results concerning interruption."*10}]
   path.write_text(json.dumps(rows))
   def lookup(_dois):return {}
   with patch.object(pmc,"LIB",path),patch.object(pmc,"resolve_ids",side_effect=lookup):
    state=pmc.run()
   self.assertEqual(state["new_fulltexts"],0)
   self.assertEqual(state["no_pmc_record"],1)
   updated=json.loads(path.read_text())[0]
   self.assertEqual(updated["pmc_oai_attempt"]["status"],"no_pmc_record")
   self.assertNotIn("analysis",updated)
 def test_doi_batch_retrieval_builds_source_backed_sections(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"library.json"
   path.write_text(json.dumps([{"kind":"scholarly","title":"Focus study","doi":"10.1000/study","published":"2026-05-01"}]))
   with patch.object(pmc,"LIB",path),patch.object(pmc,"resolve_ids",return_value={"10.1000/study":"PMC4321"}),patch.object(pmc,"fetch",return_value=body()),patch.object(pmc.time,"sleep"):
    result=pmc.run()
   self.assertEqual(result["new_fulltexts"],1)
   rec=json.loads(path.read_text())[0]
   self.assertEqual(rec["pmcid"],"PMC4321")
   self.assertEqual(rec["analysis"]["extraction_version"],3)
   self.assertEqual(rec["analysis"]["sections_available"],["methods","results","discussion"])
   self.assertIn("PMC OAI-PMH",rec["analysis"]["provenance"])
   self.assertTrue(rec["analysis"]["fulltext_url"].endswith("/PMC4321/"))
 def test_converter_returns_only_proper_ids(self):
  data=json.dumps({"records":[{"doi":"10.1000/a","pmcid":"PMC888"},{"doi":"10.1000/b","errmsg":"not in PMC"}]}).encode()
  with patch.object(pmc,"fetch",return_value=data),patch.object(pmc.time,"sleep"):
   value=pmc.resolve_ids(["10.1000/a","10.1000/b"])
  self.assertEqual(value,{"10.1000/a":"PMC888"})

class OtherFullTextTests(unittest.TestCase):
 def test_openalex_collects_multiple_results_sections_not_just_diagnostics(self):
  xml=("<TEI><text><body><div><head>Results</head><p>"
       "The reliability estimate passed several instrument checks for the sample.</p></div>"
       "<div><head>Results: outcome model</head><p>"
       "The attention outcome was associated with fewer notifications and more active verification of AI outputs.</p></div>"
       "<div><head>Methods</head><p>We collected repeated daily observations from 207 participants.</p></div>"
       "</body></text></TEI>")
  result=alex.extract(alex.ET.fromstring(xml))
  self.assertIn("fewer notifications",result["results"])
  self.assertIn("reliability estimate",result["results"])
  self.assertIn("207 participants",result["methods"])
 def test_europe_pmc_namespaced_jats_is_not_empty(self):
  root=epmc.ET.fromstring('<article xmlns="urn:test"><body><sec><title>Results</title>'
    '<p>Participants in the AI-assisted group reported more cognitive switching than controls.</p>'
    '</sec></body></article>')
  sections=epmc.extract_sections(root)
  self.assertIn("AI-assisted group",sections["results"])

if __name__=="__main__":unittest.main()

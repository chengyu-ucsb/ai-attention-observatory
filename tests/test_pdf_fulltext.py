"""Licensed PDF fallback tests. PDFs themselves are never saved in the repo."""
import contextlib
import datetime as dt
import io
import os
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import enrich_pdf_fulltext as pdf

class PDFRecoveryTests(unittest.TestCase):
 def test_pdf_text_does_not_turn_references_into_results(self):
  lines=[
   "1. Introduction","The field of AI and attention is expanding rapidly.",
   "2. Methods","We recruited 130 students to investigate task-switching with an AI assistant.",
   "3. Results","AI-assisted participants reported more changes of task and less sustained attention.",
   "Additional findings indicated the relationship depended on the kind of AI assistance provided.",
   "4. Discussion","We cannot rule out differences in participant study habits as an alternative explanation.",
   "References","A cited article has many large effects which must not be attached to this study."
  ]
  sections=pdf.collect_sections(lines)
  self.assertIn("130 students",sections["methods"])
  self.assertIn("less sustained attention",sections["results"])
  self.assertNotIn("many large effects",str(sections))
 def test_only_known_openalex_ids_are_accepted_when_doi_missing(self):
  self.assertEqual(pdf.work_url({"url":"https://openalex.org/W7421"}),"https://api.openalex.org/works/W7421")
  self.assertEqual(pdf.work_url({"url":"https://evil.example/W7421"}),"")
  self.assertIn("doi.org",pdf.work_url({"doi":"10.1000/abc"}))
 def test_no_licensed_pdf_does_not_claim_full_text(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/"library.json"
   path.write_text(json.dumps([{"kind":"scholarly","doi":"10.1000/nolic","title":"AI attention study"}]))
   work={"best_oa_location":{"license":"other-oa"},"content_urls":{"pdf":"https://content.openalex.org/works/W1.pdf"}}
   with patch.object(pdf,"LIB",path),patch.object(pdf,"fetch",return_value=json.dumps(work).encode()),patch.object(pdf.time,"sleep"):
    result=pdf.run()
   self.assertEqual(result["fulltexts_recovered"],0)
   record=json.loads(path.read_text())[0]
   self.assertNotIn("analysis",record)
   self.assertEqual(record["pdf_fulltext_attempt"]["status"],"no_licensed_machine_pdf")
 def test_licensed_pdf_is_extracted_into_index_and_never_stored_as_pdf(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);path=root/"library.json"
   path.write_text(json.dumps([{"kind":"scholarly","doi":"10.1000/yes","title":"AI attention study"}]))
   work={"best_oa_location":{"license":"cc-by","landing_page_url":"https://doi.org/10.1000/yes"},
         "content_urls":{"pdf":"https://content.openalex.org/works/W123.pdf"}}
   data=[json.dumps(work).encode(),b"%PDF-1.7 example"]
   sections={"methods":"We surveyed 130 students using a new AI tool.",
             "results":"Students described increased interruptions during the AI condition.",
             "limitations":"Associations are not causal."}
   with patch.object(pdf,"LIB",path),patch.object(pdf,"fetch",side_effect=data),patch.object(pdf,"extract_pdf",return_value=sections),patch.object(pdf.time,"sleep"):
    result=pdf.run()
   self.assertEqual(result["fulltexts_recovered"],1)
   record=json.loads(path.read_text())[0]
   self.assertEqual(record["analysis"]["results"],sections["results"])
   self.assertIn("pypdf",record["analysis"]["pdf_text_extraction"])
   self.assertEqual(list(root.glob("*.pdf")),[])
 def test_no_results_fails_closed(self):
  self.assertEqual(pdf.extract_pdf(b"not a pdf"),{})
  self.assertEqual(pdf.collect_sections(["Introduction","Research topic","References","The previous literature had large effects."]),{})

class UnicodeCheckpointTests(unittest.TestCase):
 def setUp(self):
  self.stack=contextlib.ExitStack()
  self.addCleanup(self.stack.close)
  self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
  self.path=self.root/"library.json"
  self.status=self.root/"fulltext-backfill-state.json"
  self.today=dt.datetime(2026,11,10,21,tzinfo=dt.timezone.utc)
  self.rows=[{"kind":"scholarly","doi":f"10.1000/{i}","title":"Synthetic study"} for i in range(3)]
  self.path.write_text(json.dumps(self.rows),encoding="utf-8")
  self.stack.enter_context(patch.object(pdf.openalex,"now",side_effect=lambda:self.today))
  self.stack.enter_context(patch.object(pdf.time,"sleep"))
  self.stack.enter_context(patch.dict(os.environ,{"PDF_FULLTEXT_LOOKUPS":"3","PDF_FULLTEXT_DOWNLOADS":"3"}))
  self.output=self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

 def work(self):
  return json.dumps({"best_oa_location":{"license":"cc-by","landing_page_url":"https://example.org/paper"},
   "content_urls":{"pdf":"https://content.openalex.org/works/W123.pdf"}}).encode()

 def read(self):return json.loads(self.path.read_text(encoding="utf-8"))

 def test_unicode_preserves_scalars_pairs_and_combining_marks(self):
  source="é e\u0301 中文 𝑥 😀 \ud835\udc65 \ud83d\ude00"
  self.assertEqual(pdf.unicode_text(source,"test"),"é e\u0301 中文 𝑥 😀 𝑥 😀")
  self.assertEqual(pdf.unicode_text("\ud800\udc00 \udbff\udfff","test"),"\U00010000 \U0010ffff")

 def test_unpaired_surrogates_are_rejected_without_lossy_replacement(self):
  for text in ("claim \ud835 value","claim \udf14 value","\udc00\ud800","\ud835x\udc65"):
   with self.subTest(text=repr(text)),self.assertRaises(pdf.PDFTextEncodingError) as caught:
    pdf.unicode_text(text,"page 2")
   self.assertEqual(caught.exception.diagnostic["reason"],"unpaired_surrogate")
   self.assertNotIn("claim",str(caught.exception))

 def test_normalizes_before_section_and_key_idea_caps(self):
  lines=["Results"]+["a"*99]*67+["b"*99+"\ud835\udc65"+"c"*50]
  result=pdf.collect_sections(lines)["results"]
  self.assertEqual(len(result),6800)
  self.assertTrue(result.endswith("𝑥"))
  self.path.write_text(json.dumps(self.rows[:1]))
  sections={"results":"x"*279+"\ud835\udc65"+" tail"}
  with patch.object(pdf,"fetch",side_effect=[self.work(),b"%PDF"]),patch.object(pdf,"extract_pdf",return_value=sections):
   pdf.run(self.path)
  self.assertEqual(self.read()[0]["analysis"]["key_idea"],"x"*279+"𝑥")

 def test_page_normalization_precedes_splitting_and_shared_extractor_rejects_bad_text(self):
  for tail,valid in (("\ud835\udc65",True),("\ud835",False),("\udf14",False)):
   page=SimpleNamespace(extract_text=lambda **kw:"Results\nSynthetic long source result with parameter "+tail)
   reader=SimpleNamespace(is_encrypted=False,pages=[page])
   module=SimpleNamespace(PdfReader=lambda *a,**kw:reader)
   with self.subTest(tail=repr(tail)),patch.dict(sys.modules,{"pypdf":module}):
    if valid:self.assertTrue(pdf.extract_pdf(b"%PDF-example")["results"].endswith("𝑥"))
    else:
     with self.assertRaises(pdf.PDFTextEncodingError) as caught:pdf.extract_pdf(b"%PDF-example")
     self.assertEqual(caught.exception.diagnostic["field"],"page 1")

 def test_bad_article_is_diagnosed_and_other_outcomes_survive_replay(self):
  with patch.object(pdf,"fetch",side_effect=[self.work(),b"%PDF",self.work(),b"%PDF",b"{}"]),patch.object(pdf,"extract_pdf",side_effect=[
   {"results":"Synthetic protected result \udf14 must not be stored."},{"results":"Synthetic intact result 𝑥."}]):
   stats=pdf.run(self.path)
  rows=self.read()
  self.assertEqual((stats["invalid_unicode"],stats["fulltexts_recovered"]),(1,1))
  self.assertNotIn("analysis",rows[0])
  self.assertEqual(rows[0]["pdf_fulltext_attempt"]["status"],"pdf_invalid_unicode")
  self.assertEqual(rows[0]["pdf_fulltext_attempt"]["next_at"],"2026-12-10")
  self.assertEqual(rows[0]["pdf_fulltext_attempt"]["text_error"]["codepoint"],"U+DF14")
  self.assertEqual(rows[0]["pdf_fulltext_attempt"]["text_error"]["source_pdf"],"https://content.openalex.org/works/W123.pdf")
  self.assertNotIn("protected result",self.output.getvalue())
  self.assertNotIn("protected result",self.path.read_text())
  self.assertEqual(rows[1]["analysis"]["results"],"Synthetic intact result 𝑥.")
  self.assertEqual(rows[2]["pdf_fulltext_attempt"]["status"],"no_licensed_machine_pdf")
  before=self.path.read_bytes()
  with patch.object(pdf,"fetch") as fetch:
   self.assertEqual(pdf.run(self.path)["request_attempts"],0)
   fetch.assert_not_called()
  self.assertEqual(self.path.read_bytes(),before)
  self.assertFalse(pdf.eligible(rows[0],self.today.date()+dt.timedelta(days=29)))
  self.assertTrue(pdf.eligible(rows[0],self.today.date()+dt.timedelta(days=30)))

 def test_completed_record_checkpoint_survives_later_process_failure(self):
  with patch.object(pdf,"fetch",side_effect=[b"{}",RuntimeError("unexpected failure")]):
   with self.assertRaises(RuntimeError):pdf.run(self.path)
  self.assertEqual(self.read()[0]["pdf_fulltext_attempt"]["attempts"],1)
  self.assertEqual(self.read()[1:],self.rows[1:])
  with patch.object(pdf,"fetch",return_value=b"{}") as fetch:
   self.assertEqual(pdf.run(self.path)["lookup_attempts"],2)
   self.assertEqual(fetch.call_count,2)
  self.assertEqual(self.read()[0]["pdf_fulltext_attempt"]["attempts"],1)

 def test_successful_later_attempt_clears_old_diagnostic_without_resetting_counter(self):
  self.rows[0]["pdf_fulltext_attempt"]={"version":1,"status":"pdf_invalid_unicode","next_at":"2026-11-01", "attempts":3,
    "text_error":{"reason":"unpaired_surrogate"}}
  self.path.write_text(json.dumps(self.rows[:1]))
  with patch.object(pdf,"fetch",side_effect=[self.work(),b"%PDF"]),patch.object(pdf,"extract_pdf",return_value={"results":"Synthetic intact result."}):
   pdf.run(self.path)
  attempt=self.read()[0]["pdf_fulltext_attempt"]
  self.assertEqual(attempt["attempts"],4)
  self.assertEqual(attempt["status"],"full_text")
  self.assertNotIn("text_error",attempt)

 def test_existing_invalid_input_fails_before_requests_without_truncation(self):
  for value in ([{"title":"bad \ud835"}],[]):
   with self.subTest(value=repr(value)):
    self.path.write_text(json.dumps(value))
    if not value:self.status.write_text(json.dumps({"diagnostic":"bad \udf14"}))
    before=self.path.read_bytes()
    with patch.object(pdf,"fetch") as fetch,self.assertRaises(UnicodeEncodeError):pdf.run(self.path)
    fetch.assert_not_called()
    self.assertEqual(self.path.read_bytes(),before)

 def test_corrupt_existing_json_never_silently_discards_provider_controls(self):
  before=self.path.read_bytes()
  for data in ('{"quota_pause_until":', '[]', '{"quota_pause_until":"2099-01-01T00:00:00Z","quota_pause_until":null}', '{"count":NaN}'):
   self.status.write_text(data)
   with self.subTest(data=data),patch.object(pdf,"fetch") as fetch,self.assertRaises(ValueError):pdf.run(self.path)
   fetch.assert_not_called()
   self.assertEqual(self.path.read_bytes(),before)
   self.assertEqual(self.status.read_text(),data)

 def test_duplicate_library_keys_are_rejected_before_requests(self):
  self.path.write_text('[{"kind":"scholarly","doi":"10.1000/synthetic","analysis":{},"analysis":null}]')
  before=self.path.read_bytes()
  with patch.object(pdf,"fetch") as fetch,self.assertRaises(ValueError):pdf.run(self.path)
  fetch.assert_not_called()
  self.assertEqual(self.path.read_bytes(),before)

 def test_bad_checkpoint_encoding_preserves_outputs_unless_saving_active_pause(self):
  self.status.write_text('{"status":"original"}\n')
  before=self.path.read_bytes(),self.status.read_bytes()
  for rows,state in (([{"claim":"bad \udf14"}],{}),([],{"diagnostic":"bad \ud835"})):
   with self.subTest(rows=repr(rows)),self.assertRaises(UnicodeEncodeError):
    pdf.save_checkpoint(self.path,rows,self.status,state,True)
   self.assertEqual((self.path.read_bytes(),self.status.read_bytes()),before)
  self.assertEqual(list(self.root.glob(".*.tmp")),[])

 def test_active_pause_survives_library_encoding_failure(self):
  before=self.path.read_bytes()
  with self.assertRaises(UnicodeEncodeError):
   pdf.save_checkpoint(self.path,[{"results":"bad \udf14"}],self.status,
                       {"quota_pause_until":"2026-11-11T01:00:00Z"},True)
  self.assertEqual(self.path.read_bytes(),before)
  with patch.object(pdf,"fetch") as fetch:
   self.assertEqual(pdf.run(self.path)["status"],"waiting_for_budget")
   fetch.assert_not_called()

 def test_write_and_replace_failures_preserve_original_and_remove_temporary(self):
  before=self.path.read_bytes()
  for operation in ("fsync","replace"):
   with self.subTest(operation=operation),patch.object(pdf.os,operation,side_effect=OSError("disk failure")),self.assertRaises(OSError):
    pdf.atomic_write(self.path,b"[]\n")
   self.assertEqual(self.path.read_bytes(),before)
   self.assertEqual(list(self.root.glob(".*.tmp")),[])

 def test_provider_pause_survives_failed_library_replace(self):
  before=self.path.read_bytes()
  replace=pdf.os.replace
  def fail_library(source,target):
   if target==self.path:raise OSError("disk failure")
   return replace(source,target)
  with patch.object(pdf.os,"replace",side_effect=fail_library),self.assertRaises(OSError):
   pdf.save_checkpoint(self.path,[],self.status,{"quota_pause_until":"2026-11-11T01:00:00Z"},True)
  self.assertEqual(self.path.read_bytes(),before)
  with patch.object(pdf,"fetch") as fetch:
   self.assertEqual(pdf.run(self.path)["status"],"waiting_for_budget")
   fetch.assert_not_called()

 def test_state_cannot_overwrite_library(self):
  before=self.path.read_bytes()
  with self.assertRaisesRegex(ValueError,"must differ"):pdf.run(self.path,self.path)
  self.assertEqual(self.path.read_bytes(),before)

if __name__=="__main__":unittest.main()

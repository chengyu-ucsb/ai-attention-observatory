"""Checks exercise the normal model calls using explicit, repeatable model outputs."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import comprehensive_readings as reader
from full_document_access import Document
from reading_evidence_context import edit_article


class EditorialClaimTests(unittest.TestCase):
    def test_survey_and_experiment_readings_bind_distinct_sentences_to_their_own_spans(self):
        for label, design, finding in (
            ("survey", "Preservice teachers filled in questionnaires about tool use and perceived achievement.",
             "Higher reported achievement was associated with more frequent reported tool use."),
            ("experiment", "Students were assigned to compare worked examples with or without computer hints.",
             "On the later independent test the two groups earned similar scores."),
        ):
            with self.subTest(label=label):
                document = Document([
                    {"location": "paragraph:1", "role": "methods", "text": design},
                    {"location": "paragraph:2", "role": "results", "text": finding},
                    {"location": "paragraph:3", "role": "references", "text": "A cited author reported markedly stronger effects in a different sample."},
                ], "https://example.org/article")
                claims = [
                    {"field": "study_design", "text": ("Teachers described their own technology use and achievement in a questionnaire." if label == "survey"
                        else "The class compared examples with and without access to computer hints."), "source_span": "C0001:S001"},
                    {"field": "reported_results", "text": ("Teachers who reported more use also reported higher achievement." if label == "survey"
                        else "The groups finished the later independent test with comparable scores."), "source_span": "C0001:S002"}]
                calls = []
                def model(_model, instruction, *args, **kwargs):
                    calls.append(instruction)
                    if len(calls) == 1:
                        self.assertNotIn("C0001:S003", kwargs["source_span_ids"])
                        return {"claims": claims, "no_claim_reason": ""}
                    if len(calls) == 2:
                        return {"supported": [0, 1], "rejected": []}
                    return {"order": [1, 0]}
                with patch.object(reader, "model_json", side_effect=model):
                    got = reader.synthesize(document, object(), "scholarly", label)
                self.assertEqual(len(calls), 3)
                self.assertIn("self-report", calls[1])
                self.assertIn('"role": "references"', calls[0])
                self.assertEqual(got["reported_results"], claims[1]["text"])
                self.assertEqual(got["narrative_order"], [1, 0])
                self.assertEqual(got["claim_evidence"][1]["locations"], [
                    {"location": "paragraph:2", "start": 0, "end": len(finding)}])

    def test_prior_work_and_methods_cannot_establish_the_current_papers_result(self):
        for role in ("prior_work", "hypotheses", "caption"):
            doc = Document([{"location": "page:1", "role": role,
                             "text": "An earlier cohort reported better attention after completing the assigned writing task."}],
                           "https://example.org/note")
            chunk = reader.chunk_document(doc)[0]
            claim = {"field": "reported_results", "text": "Assigned writing improved attention in the authors' study cohort.", "source_span": "C0001:S001"}
            with patch.object(reader, "model_json", return_value={"claims": [claim], "no_claim_reason": ""}):
                with self.assertRaisesRegex(ValueError, "claim_source_role_mismatch"):
                    reader.read_chunk(object(), chunk, "scholarly", "A review")

    def test_method_can_be_reclassified_once_but_never_be_published_as_a_result(self):
        doc = Document([{"location":"page:1","role":"methods",
            "text":"Respondents described their everyday study habits using online questionnaires."}],"https://example.org/paper")
        chunk=reader.chunk_document(doc)[0]
        proposed={"field":"reported_results","text":"Respondents provided online accounts of their usual study habits.","source_span":"C0001:S001"}
        with patch.object(reader,"model_json",side_effect=[
            {"claims":[proposed],"no_claim_reason":""},
            {"0":"Researchers used an online questionnaire to ask about usual study habits."},
            {"supported":[0],"rejected":[]}]):
            notes=reader.read_chunk(object(),chunk,"scholarly","Study habits")
        self.assertEqual(notes[0]["field"],"study_design")
        self.assertEqual(notes[0]["source_span"],"C0001:S001")

    def test_page_offsets_preserve_reference_and_hypothesis_boundaries(self):
        paper = "Respondents answered a survey about their confidence. "
        reference = "An older article describes a different classroom experiment."
        chunk = reader.chunk_document(Document([{"text": paper+reference, "location": "page:7", "role": "page",
            "sections": [{"start": 0, "end": len(paper), "role": "methods", "headings": ["Method"]},
                         {"start": len(paper), "end": len(paper+reference), "role": "references", "headings": ["References"]}]}],
            "https://example.org/paper"))[0]
        spans = reader.source_spans(chunk)
        self.assertEqual([s["citable"] for s in spans], [True,False])
        self.assertEqual(chunk["ranges"][1]["start"], len(paper))

    def test_retained_evidence_is_not_a_substantive_account_by_default(self):
        from reading_evidence_context import account_status
        self.assertEqual(account_status("scholarly", ["study_design"]), "checked_evidence_only")
        self.assertEqual(account_status("scholarly", ["study_design", "reported_results"]), "article_account")
        self.assertEqual(account_status("scholarly", ["research_question", "authors_interpretation"]), "article_account")
        self.assertEqual(account_status("nonacademic", ["thesis"]), "checked_evidence_only")
        self.assertEqual(account_status("nonacademic", ["thesis", "examples"]), "article_account")

    def test_editor_cannot_replace_the_outcome_with_setup(self):
        claims = [{"field": "study_design", "text": "The team compared an assisted and an independent writing task."},
                  {"field": "reported_results", "text": "Only the participants' assisted task scores improved after training."}]
        with self.assertRaisesRegex(ValueError, "incomplete_article_selection"):
            edit_article(claims, "scholarly", "Transfer", lambda *args: {"order": [0]})

    def test_current_and_stale_complete_machine_readings(self):
        for ver, eligible in ((3, True), (reader.READER_VERSION, False)):
            row = {"deep_analysis": {"version": ver, "account_status": "article_account", "coverage": {"all_retrieved_text_processed": True,
                   "evidence_status": "full_document_retrieved"}}}
            self.assertEqual(reader.due(row,"2026-11-20"), eligible)
            row["deep_analysis"]["account_status"] = "checked_evidence_only"
            row["complete_reading_attempt"] = {"next_at":"2026-11-21"}
            self.assertFalse(reader.due(row,"2026-11-20"))
            self.assertTrue(reader.due(row,"2026-11-21"))
            row["source_review"] = {"status": "checked"}
            self.assertFalse(reader.due(row,"2026-11-20"))

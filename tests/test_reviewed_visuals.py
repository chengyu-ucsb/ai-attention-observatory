"""A checked figure may not migrate to an unreviewed source or edited payload."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_visuals import reviewed_visual, reviewed_visuals, visual_assessment, visual_digest, visual_spec
from verified_full_article_notes import apply


class ReviewedVisualTests(unittest.TestCase):
    def setUp(self):
        self.visual = deepcopy(reviewed_visuals()[0])
        source = self.visual['source']
        self.record = {'kind': 'scholarly', 'doi': self.visual['doi'], 'reading': {
            'original_summary': True, 'original_summary_id': self.visual['reading_id'],
            **{'source_' + key: source[key] for key in ('url', 'version', 'sha256')}}}

    def test_manifest_binds_to_current_approved_reading(self):
        originals = json.loads((ROOT / 'data/original-readings.json').read_text())['articles']
        original = next(item for item in originals if item['id'] == self.visual['reading_id'])
        for key in ('url', 'version', 'sha256'):
            self.assertEqual(self.visual['source'][key], original['source']['source_sha256' if key == 'sha256' else key])
        self.assertEqual(reviewed_visual(self.record), self.visual)

    def test_different_source_version_url_hash_or_reading_is_hidden(self):
        for key in ('source_url', 'source_version', 'source_sha256', 'original_summary_id'):
            record = deepcopy(self.record)
            record['reading'][key] += '-changed'
            self.assertIsNone(reviewed_visual(record), key)

    def test_edited_visual_requires_renewed_source_check(self):
        visual = deepcopy(self.visual)
        visual['rows'][0][2] = 'AI improves learning'
        self.assertIsNone(reviewed_visual(self.record, [visual]))

    def test_unchecked_or_copied_image_does_not_enter_factual_display(self):
        for key, value in (('rights', 'unknown'), ('kind', 'source_image')):
            visual = deepcopy(self.visual)
            visual[key] = value
            visual['review']['payload_sha256'] = visual_digest(visual)
            self.assertIsNone(reviewed_visual(self.record, [visual]))
        self.record['reading']['original_summary'] = False
        self.assertIsNone(reviewed_visual(self.record))

    def test_missing_cells_and_malformed_candidates_fail_closed(self):
        visual = deepcopy(self.visual)
        visual['rows'][0].pop()
        visual['review']['payload_sha256'] = visual_digest(visual)
        for candidate in (visual, {}, None, 'caption alone'):
            self.assertIsNone(reviewed_visual(self.record, [candidate]))

    def test_tutoring_visual_retains_section_specific_comparisons_and_limits(self):
        self.assertEqual(self.visual['rows'], [
            ['Reported effort', 'No clear difference', 'AI tutor higher than human'],
            ['Perceived difficulty', 'Search higher than human', 'AI tutor and search higher than human'],
            ['Questions started', 'Human higher than AI tutor', 'Human higher than search']])
        self.assertIn('exploratory', self.visual['description'])
        self.assertIn('did not assess answer accuracy or lasting learning', self.visual['caption'])

    def test_manual_note_correction_reopens_visual_review(self):
        visual = next(v for v in reviewed_visuals() if v["reading_id"] == "verified-notes")
        record = {"kind": "scholarly", "doi": visual["doi"]}
        apply([record])
        record["visual"] = visual_spec(record)
        self.assertEqual(visual_assessment(record)["status"], "ready")
        record["verified_article_review"]["results"] += " Corrected value."
        record["visual"] = visual_spec(record)
        self.assertEqual(visual_assessment(record)["reason"], "recheck_registered_adaptation")

    def test_new_figure_caption_creates_candidate_without_drawing_chart(self):
        record = {"url": "https://example.org/reading",
                  "analysis": {"figures": [{"label": "Fig. 10", "caption": "A 99% difference"}]}}
        result = visual_assessment(record)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["locators"], ["Fig. 10"])
        self.assertNotIn("99", str(result))
        self.assertNotEqual(visual_spec(record)["kind"], "reviewed_comparison")

    def test_prose_decision_is_bound_to_the_current_source(self):
        url = "https://example.org/proposal"
        record = {"url": url, "analysis": {"figures": [{"label": "Fig. 2", "caption": "Proposed model."}]}}
        candidate = visual_assessment(record)
        decisions = {"url:" + url: {"source_fingerprint": candidate["source_fingerprint"],
                                    "reason": "The conceptual drawing repeats the description."}}
        self.assertEqual(visual_assessment(record, decisions)["reason"], "editor_selected_prose")
        record["analysis"]["figures"][0]["caption"] = "Revised framework."
        self.assertEqual(visual_assessment(record, decisions)["status"], "needs_review")

    def test_checked_commentary_is_bound_to_its_canonical_url(self):
        visual = next(v for v in reviewed_visuals() if v.get("record_url"))
        record = {"kind": "nonacademic", "url": visual["record_url"], "reading": {
            "original_summary": True, "original_summary_id": visual["reading_id"],
            **{"source_" + k: visual["source"][k] for k in ("url","version","sha256")}}}
        self.assertEqual(reviewed_visual(record), visual)
        record["url"] += "-another-article"
        self.assertIsNone(reviewed_visual(record))

    def test_chart_cannot_draw_values_beyond_checked_common_scale(self):
        visual = deepcopy(next(v for v in reviewed_visuals() if v.get("chart")))
        record = {"doi": visual["doi"], "reading": {
            "original_summary": True, "original_summary_id": visual["reading_id"],
            **{"source_" + k: visual["source"][k] for k in ("url", "version", "sha256")}}}
        self.assertEqual(reviewed_visual(record), visual)
        for invalid in ("NaN", "-1", "unreported", "999"):
            visual["rows"][0][1] = invalid
            visual["review"]["payload_sha256"] = visual_digest(visual)
            self.assertIsNone(reviewed_visual(record, [visual]))


if __name__ == '__main__':
    unittest.main()

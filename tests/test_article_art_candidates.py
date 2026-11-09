"""Bounded source-grounded alternatives and stable allocation regression tests."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import article_art as art
from art_similarity import compare, decode_signature, is_near_twin


def article(identity="a", title="Cognitive offloading in undergraduate mathematical learning"):
    return {"doi": "10.1234/" + identity, "title": title,
            "reading": {"digest": {"idea": title, "explain": "Examining how people use tools."}}}


class CandidateRetryTests(unittest.TestCase):
    def assert_grounded(self, row, spec):
        inputs = art.public_inputs(row)
        self.assertEqual(len(spec["source_grounding"]), 2)
        for ground in spec["source_grounding"]:
            self.assertIn(ground["subject"], spec["visual_subjects"])
            self.assertIn(ground["field"], {"title", "source_context"})
            self.assertTrue(ground["phrases"])
            self.assertTrue(art.matches(inputs[ground["field"]], tuple(ground["phrases"])))

    def test_collision_selects_a_different_grounded_dominant_pair(self):
        rows = [article("a"), article("b")]
        original = copy.deepcopy(rows)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            art.attach_art(rows, root)
            a, b = (row["editorial_art"] for row in rows)
            self.assertEqual([a["status"], b["status"]], ["ready", "ready"])
            self.assertEqual(a["candidate_index"], 0)
            self.assertGreater(b["candidate_index"], 0)
            self.assertEqual(b["attempt_count"], 2)
            self.assertEqual(b["retry_status"], "accepted")
            self.assertIn("duplicate_foreground_subjects", b["retry_attempts"][0]["review_reasons"])
            self.assertEqual(b["retry_attempts"][-1]["status"], "ready")
            for key in ("foreground_signature", "foreground_geometry_fingerprint", "composition_fingerprint", "asset_fingerprint"):
                self.assertNotEqual(a[key], b[key])
            self.assertFalse(is_near_twin(compare(decode_signature(a["coarse_raster_signature"]), decode_signature(b["coarse_raster_signature"]))))
            self.assertEqual(len(list((root / art.GENERATED_DIR).glob("*.svg"))), 2)
        for before, row in zip(original, rows):
            self.assert_grounded(row, row["editorial_art"])
            row.pop("editorial_art")
            self.assertEqual(row, before)

    def test_plan_is_built_once_per_record_and_never_reused_after_source_changes(self):
        rows = [article(str(i)) for i in range(7)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(art, "candidate_specs", wraps=art.candidate_specs) as plan:
                art.attach_art(rows, root)
            self.assertEqual(plan.call_count, len(rows))
            prior_key = rows[0]["editorial_art"]["candidate_pool_fingerprint"]
            rows[0]["reading"]["methods"] = "Interviews with music teachers."
            with patch.object(art, "candidate_specs", wraps=art.candidate_specs) as plan:
                art.attach_art(rows, root, reuse_exhausted=True)
            self.assertEqual(plan.call_count, len(rows))
            self.assertNotEqual(prior_key, rows[0]["editorial_art"]["candidate_pool_fingerprint"])

    def test_source_vocabulary_bounds_candidates_and_never_reorders_same_pair(self):
        row = article(title="Critical thinking in doctoral academic writing with mathematical learning and music practice")
        specs = art.candidate_specs(art.public_inputs(row))
        self.assertEqual(len(specs), art.MAX_ART_CANDIDATES)
        self.assertEqual(specs[0], art.choose_concept(art.public_inputs(row)))
        pairs = [tuple(sorted(spec["visual_subjects"])) for spec in specs]
        self.assertEqual(len(pairs), len(set(pairs)))
        for spec in specs:
            self.assert_grounded(row, spec)
        with self.assertRaises(ValueError):
            art.create_art(row, write_asset=False, candidate_index=art.MAX_ART_CANDIDATES)
        with self.assertRaises(ValueError):
            art.create_art(row, write_asset=False, candidate_index=True)

    def test_exhaustion_is_bounded_and_hold_has_no_cover(self):
        rows = [article(str(i)) for i in range(art.MAX_ART_CANDIDATES + 1)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            art.attach_art(rows, root)
            held = rows[-1]["editorial_art"]
            self.assertEqual(held["status"], "needs_review")
            self.assertEqual(held["retry_status"], "exhausted")
            self.assertEqual(held["attempt_count"], art.MAX_ART_CANDIDATES)
            self.assertEqual(len({x["candidate_fingerprint"] for x in held["retry_attempts"]}), art.MAX_ART_CANDIDATES)
            self.assertTrue(all(x["status"] == "needs_review" and x["review_reasons"] for x in held["retry_attempts"]))
            self.assertNotIn("src", held)
            self.assertNotIn("thumbnail_src", held)
            self.assertEqual(len(list((root / art.GENERATED_DIR).glob("*.svg"))), sum(r["editorial_art"]["status"] == "ready" for r in rows))

    def test_no_invented_context_from_tags_or_negated_topics(self):
        row = article(title="A new perspective")
        row["reading"]["digest"] = {"idea": "Questions worth asking", "tags": ["Mathematics", "Metacognition", "Writing"],
                                    "explain": "Not music. Never programming. Rather than writing."}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            art.attach_art([row], root)
            held = row["editorial_art"]
            self.assertEqual(held["retry_status"], "insufficient_context")
            self.assertEqual(held["attempt_count"], 1)
            self.assertEqual(held["candidate_count"], 1)
            self.assertEqual(held["visual_subjects"], [])
            self.assertNotIn("src", held)
            self.assertFalse((root / art.GENERATED_DIR).exists())

    def test_ambiguous_extra_keywords_do_not_invent_retry_subjects(self):
        row = article()
        row["reading"]["methods"] = "People exercise agency. The rest of the text examines use at scale and waits for answers."
        specs = art.candidate_specs(art.public_inputs(row))
        subjects = {subject for spec in specs for subject in spec["visual_subjects"]}
        self.assertFalse(subjects.intersection({"physical", "sleep", "measurement", "time"}))

    def test_pool_fingerprint_tracks_source_policy_and_not_collection_noise(self):
        row = article()
        first = art.candidate_pool_fingerprint(row)
        row.update(published="2099-01-01", citation_count=991)
        self.assertEqual(first, art.candidate_pool_fingerprint(row))
        row["reading"]["methods"] = "Interviews with music teachers."
        self.assertNotEqual(first, art.candidate_pool_fingerprint(row))
        current = art.candidate_pool_fingerprint(row)
        with patch.object(art, "CANDIDATE_POLICY_VERSION", "test-next"):
            self.assertNotEqual(current, art.candidate_pool_fingerprint(row))

    def test_accepted_alternative_survives_blocker_removal_and_new_duplicate(self):
        rows = [article("a"), article("z")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            art.attach_art(rows, root)
            accepted = copy.deepcopy(rows[1]["editorial_art"])
            self.assertGreater(accepted["candidate_index"], 0)
            path = root / accepted["src"]
            mtime = path.stat().st_mtime_ns
            art.attach_art([rows[1]], root)
            self.assertEqual(rows[1]["editorial_art"], accepted)
            newcomer = article("0-new")
            art.attach_art([newcomer, rows[1]], root)
            self.assertEqual(rows[1]["editorial_art"], accepted)
            self.assertEqual(path.stat().st_mtime_ns, mtime)

    def test_legacy_v2_primary_allocation_keeps_priority(self):
        existing, newcomer = article("z"), article("a")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = art.create_art(existing, root)
            existing["editorial_art"] = {key: value for key, value in original.items()
                                         if not key.startswith("candidate_")}
            art.attach_art([newcomer, existing], root)
            self.assertEqual(existing["editorial_art"]["src"], original["src"])
            self.assertEqual(existing["editorial_art"]["candidate_index"], 0)
            self.assertGreater(newcomer["editorial_art"]["candidate_index"], 0)

    def test_unchanged_exhausted_pool_is_reused_without_rendering_or_fake_attempts(self):
        rows = [article(str(i)) for i in range(7)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            art.attach_art(rows, root)
            prior = copy.deepcopy(rows)
            with patch.object(art, "create_art", wraps=art.create_art) as create:
                art.attach_art(rows, root, reuse_exhausted=True)
            held_ids = {art.canonical_identity(r) for r in prior if r["editorial_art"]["status"] == "needs_review"}
            self.assertTrue(held_ids)
            self.assertFalse(held_ids.intersection(art.canonical_identity(call.args[0]) for call in create.call_args_list))
            self.assertEqual(rows, prior)

    def test_bad_accepted_allocation_invalidates_exhausted_cache(self):
        rows = [article(str(i)) for i in range(7)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            art.attach_art(rows, root)
            held_ids = {art.canonical_identity(r) for r in rows if r["editorial_art"]["status"] == "needs_review"}
            rows[0]["editorial_art"]["asset_fingerprint"] = "f" * 64
            with patch.object(art, "create_art", wraps=art.create_art) as create:
                art.attach_art(rows, root, reuse_exhausted=True)
            self.assertTrue(held_ids.issubset({art.canonical_identity(call.args[0]) for call in create.call_args_list}))

    def test_malformed_cached_candidate_index_is_recomputed(self):
        row = article(title="A new perspective")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            art.attach_art([row], root)
            for bad in (99, -1, "0", True):
                row["editorial_art"]["candidate_index"] = bad
                with patch.object(art, "create_art", wraps=art.create_art) as create:
                    art.attach_art([row], root, reuse_exhausted=True)
                self.assertTrue(create.called)
                self.assertEqual(row["editorial_art"]["candidate_index"], 0)
                self.assertNotIn("src", row["editorial_art"])

    def test_corrupt_exhaustion_and_accepted_ledgers_are_not_reused(self):
        rows = [article(str(i)) for i in range(7)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            art.attach_art(rows, root)
            baseline = copy.deepcopy(rows)
            held_index = next(i for i, row in enumerate(rows) if row["editorial_art"]["status"] == "needs_review")
            for corruption in ("empty", "wrong_fingerprint", "duplicate_index", "missing_attempt", "wrong_final", "nonexistent_owner"):
                rows = copy.deepcopy(baseline)
                held = rows[held_index]["editorial_art"]
                if corruption == "empty":
                    held.update(retry_attempts=[], attempt_count=0)
                elif corruption == "wrong_fingerprint":
                    held["retry_attempts"][0]["candidate_fingerprint"] = "0" * 64
                elif corruption == "duplicate_index":
                    held["retry_attempts"][0] = copy.deepcopy(held["retry_attempts"][1])
                elif corruption == "missing_attempt":
                    held["retry_attempts"].pop(0)
                    held["attempt_count"] -= 1
                elif corruption == "wrong_final":
                    held["candidate_fingerprint"] = "0" * 64
                else:
                    for attempt in held["retry_attempts"]:
                        for collision in attempt["review_collisions"]:
                            collision["identity"] = "doi:10.1234/nonexistent"
                    held["review_collisions"] = copy.deepcopy(held["retry_attempts"][-1]["review_collisions"])
                with patch.object(art, "create_art", wraps=art.create_art) as create:
                    art.attach_art(rows, root, reuse_exhausted=True)
                self.assertTrue(any(art.canonical_identity(call.args[0]) == art.canonical_identity(rows[held_index]) for call in create.call_args_list), corruption)
                self.assertEqual(rows[held_index]["editorial_art"], baseline[held_index]["editorial_art"])
            chosen = next(row for row in baseline if row["editorial_art"]["status"] == "ready" and row["editorial_art"]["candidate_index"] > 0)
            chosen = copy.deepcopy(chosen)
            src = chosen["editorial_art"]["src"]
            chosen["editorial_art"]["retry_attempts"][0]["candidate_fingerprint"] = "0" * 64
            art.attach_art([chosen], root)
            self.assertEqual(chosen["editorial_art"]["src"], src)
            self.assertEqual(chosen["editorial_art"]["attempt_count"], 1)

    def test_actual_public_corpus_preserves_accepted_images_and_all_guards(self):
        rows = json.loads((ROOT / "data/public-library.json").read_text())
        original = copy.deepcopy(rows)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            shutil.copy(ROOT / "data/article-art-overrides.json", root / "data/article-art-overrides.json")
            shutil.copytree(ROOT / "assets/editorial-covers", root / "assets/editorial-covers")
            art.attach_art(rows, root)
            ready = [r["editorial_art"] for r in rows if r["editorial_art"]["status"] == "ready"]
            for key in ("semantic_signature", "foreground_signature", "foreground_geometry_fingerprint", "composition_fingerprint", "asset_fingerprint"):
                values = [a[key] for a in ready if a.get(key)]
                self.assertEqual(len(values), len(set(values)), key)
            pixels = [decode_signature(a["coarse_raster_signature"]) for a in ready if a.get("coarse_raster_signature")]
            for i, left in enumerate(pixels):
                self.assertTrue(all(not is_near_twin(compare(left, right)) for right in pixels[i+1:]))
            for before, row in zip(original, rows):
                a = row.pop("editorial_art")
                previous = before.pop("editorial_art")
                self.assertEqual(row, before)
                if previous["status"] == "ready":
                    self.assertEqual(a["status"], "ready")
                    self.assertEqual(a["src"], previous["src"])
                self.assertLessEqual(a["attempt_count"], art.MAX_ART_CANDIDATES)
                if a["status"] == "needs_review":
                    self.assertNotIn("src", a)
                elif a["semantic_basis"] != "editor_selected":
                    self.assert_grounded(row, a)


if __name__ == "__main__":
    unittest.main()

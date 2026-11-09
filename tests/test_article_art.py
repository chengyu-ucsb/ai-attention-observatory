"""Offline regression checks for editorial art, separate from evidence graphics."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import article_art as art
import build_public
from build_visuals import visual_spec


def public_records():
    return json.loads((ROOT / "data/public-library.json").read_text())


def article(title="Cognitive offloading in undergraduate mathematical learning", doi="10.1234/example"):
    return {"doi": doi, "title": title, "kind": "scholarly", "reading": {"level": "abstract",
        "digest": {"idea": title, "explain": "Examining how people use tools."}}}


def png(width=12, height=8):
    def chunk(kind, value):
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress((b"\x00" + b"\xe0\x01\x22" * width) * height)) + chunk(b"IEND", b""))


class ArticleArtTests(unittest.TestCase):
    def test_context_cues_do_not_confuse_substrings_or_unrelated_subjects(self):
        self.assertFalse(art.matches("restrictions for students", ("rest", "or ")))
        self.assertFalse(art.matches("rather than treating constant monitoring as the default", ("monitoring",)))
        self.assertTrue(art.matches("mathematical learning", ("mathemat",)))
        self.assertTrue(art.matches("reflective learning dashboards", ("dashboard",)))
        spec = art.choose_concept(art.public_inputs(article(
            "Metacognitive disengagement and knowledge innovation quality in human–AI collaboration")))
        self.assertIn("knowledge", spec["visual_subjects"])
        self.assertNotIn("art", spec["visual_subjects"])
        spec = art.choose_concept(art.public_inputs(article("Siri app access and intention tracking")))
        self.assertNotIn("inequality", spec["visual_subjects"])

    def test_actual_public_records_publish_distinct_grounded_art_or_explicit_review(self):
        records = public_records()
        self.assertGreater(len(records), 50)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            art.attach_art(records, root)
            ready = [r for r in records if r["editorial_art"]["status"] == "ready"]
            self.assertGreater(len(ready), len(records) // 2)
            paths = [r["editorial_art"]["src"] for r in ready]
            contents = [(root / p).read_bytes() for p in paths]
            self.assertEqual(len(paths), len(set(paths)))
            self.assertEqual(len(contents), len(set(contents)))
            self.assertEqual(len(ready), len({r["editorial_art"]["composition_fingerprint"] for r in ready}))
            self.assertEqual(len(ready), len({r["editorial_art"]["foreground_signature"] for r in ready}))
            self.assertLess(sum(map(len, contents)), 600_000)
            self.assertLess(max(map(len, contents)), art.MAX_SVG_BYTES)
            self.assertGreaterEqual(len({r["editorial_art"]["motif"] for r in records}), 12)
            for r in records:
                a = r["editorial_art"]
                self.assertEqual(a["kind"], "editorial_illustration")
                self.assertIn("Not a depiction of study results", a["alt"])
                self.assertIn(r["title"], a["concept"])
                if a["status"] == "needs_review":
                    self.assertTrue(a["review_reasons"])
                    self.assertNotIn("src", a)
                    self.assertNotIn("thumbnail_src", a)
                    continue
                self.assertFalse(a["review_reasons"])
                self.assertEqual(len(a["source_grounding"]), 2)
                inputs = art.public_inputs(r)
                for ground in a["source_grounding"]:
                    self.assertIn(ground["subject"], a["visual_subjects"])
                    self.assertIn(ground["field"], ("title", "source_context"))
                    self.assertTrue(ground["phrases"])
                    for phrase in ground["phrases"]:
                        self.assertIn(phrase.casefold().strip(), inputs[ground["field"]].casefold())
                self.assertRegex(a["src"], r"^assets/article-art/[a-f0-9]{20}-[a-f0-9]{24}\.svg$")

    def test_synthetic_topics_select_concrete_different_families(self):
        examples = {
            "reconstruction": "Learning without AI after gradual release",
            "offloading": "Delegating tasks through cognitive offloading",
            "verification": "Critical thinking and verification",
            "reflection": "Metacognition and reflective practice",
            "collaboration": "Shared control with an AI peer",
            "interruptions": "Digital notifications and interruptions",
            "switching": "Task switching and switch readiness",
            "autonomy": "Autonomy through user-controlled focus filters",
            "governance": "Governance, consent and democracy",
            "language": "Foreign language instruction and translanguaging",
            "writing": "Writing, composing and authorship",
            "creative": "Creativity and art education",
            "music": "Music, singing and vocal practice",
            "wellbeing": "Wellbeing and emotional stress",
            "memory": "Transactive memory and working memory",
            "scaffolding": "Scaffolding and support mechanisms",
            "inquiry": "Scientific inquiry and problem solving",
            "attention": "Sustained attention and attending",
            "learning": "Literacy in education",
            "reading": "A new perspective",
        }
        with tempfile.TemporaryDirectory() as d:
            images = []
            for family, title in examples.items():
                with self.subTest(family=family):
                    record = article(title, "10.1234/" + family)
                    a = art.create_art(record, Path(d))
                    self.assertEqual(a["motif"], family)
                    if a["status"] == "needs_review":
                        self.assertEqual(a["review_reasons"], ["insufficient_specific_context"])
                        self.assertNotIn("src", a)
                        continue
                    images.append((Path(d) / a["src"]).read_bytes())
            self.assertTrue(images)
            self.assertEqual(len(images), len(set(images)))

    def test_deterministic_and_write_if_unchanged_preserves_mtime(self):
        record = article()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first = art.create_art(record, root)
            path = root / first["src"]
            before = path.stat().st_mtime_ns
            second = art.create_art(copy.deepcopy(record), root)
            self.assertEqual(first, second)
            self.assertEqual(before, path.stat().st_mtime_ns)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), first["asset_fingerprint"])

    def test_record_order_does_not_change_art(self):
        records = [article(doi="10.1234/a"), article(doi="10.1234/b")]
        with tempfile.TemporaryDirectory() as d:
            forward = art.attach_art(copy.deepcopy(records), Path(d))
            backward = art.attach_art(list(reversed(copy.deepcopy(records))), Path(d))
            self.assertEqual([r["editorial_art"] for r in forward], list(reversed([r["editorial_art"] for r in backward])))
            self.assertEqual([r["editorial_art"]["status"] for r in forward], ["ready", "ready"])
            self.assertGreater(forward[1]["editorial_art"]["candidate_index"], 0)

    def test_primary_repeated_source_concept_is_held_without_decorative_variation(self):
        rows = [article("Cognitive offloading in mathematical learning among undergraduate students", "10.1234/a"),
                article("Cognitive offloading in undergraduate mathematical learning: a replication", "10.1234/b")]
        before = copy.deepcopy(rows)
        for row in rows:
            row["visual"] = visual_spec(row)
        with tempfile.TemporaryDirectory() as d, patch.object(art, "candidate_specs", side_effect=lambda inputs: [art.choose_concept(inputs)]):
            root = Path(d)
            art.attach_art(rows, root)
            accepted, held = (row["editorial_art"] for row in rows)
            self.assertEqual(accepted["status"], "ready")
            self.assertEqual(held["status"], "needs_review")
            self.assertIn("duplicate_semantic_concept", held["review_reasons"])
            self.assertIn("duplicate_foreground_subjects", held["review_reasons"])
            self.assertIn("duplicate_composition", held["review_reasons"])
            self.assertNotIn("src", held)
            self.assertNotIn("thumbnail_src", held)
            self.assertEqual(len(list((root / "assets/article-art").glob("*.svg"))), 1)
            for prior, row in zip(before, rows):
                self.assertEqual(row["reading"], prior["reading"])
                self.assertEqual(row["visual"], visual_spec(prior))
            summary = art.report(rows, root)
            self.assertEqual(summary["ready_count"], 1)
            self.assertEqual(summary["needs_review_count"], 1)
            self.assertTrue(summary["semantic_collision_groups"])
            self.assertTrue(summary["composition_collision_groups"])

    def test_same_foreground_pair_is_held_even_with_a_different_motif(self):
        rows = [article("Cognitive offloading in doctoral academic writing", "10.1234/a"),
                article("Reflective learning in doctoral academic writing", "10.1234/b")]
        with tempfile.TemporaryDirectory() as d, patch.object(art, "candidate_specs", side_effect=lambda inputs: [art.choose_concept(inputs)]):
            art.attach_art(rows, Path(d))
        a, b = (row["editorial_art"] for row in rows)
        self.assertNotEqual(a["motif"], b["motif"])
        self.assertNotEqual(a["composition_fingerprint"], b["composition_fingerprint"])
        self.assertEqual(b["status"], "needs_review")
        self.assertIn("duplicate_foreground_subjects", b["review_reasons"])
        self.assertIn("duplicate_foreground_geometry", b["review_reasons"])
        self.assertNotIn("src", b)

    def test_equivalent_glyph_labels_cannot_evade_foreground_geometry_guard(self):
        rows = [article("Cognitive offloading in doctoral work", "10.1234/a"),
                article("Reflective learning in doctoral work", "10.1234/b")]
        choose = art.choose_concept
        draw = art.draw_subject
        def alias_pair(inputs):
            spec = choose(inputs)
            # Simulate equivalent glyphs. Keep different semantic signatures
            # and motif frames to isolate the independent geometry gate.
            spec["visual_subjects"] = ["doctoral", "language" if spec["motif"] == "offloading" else "interview"]
            spec["semantic_signature"] = "|".join([spec["motif"]] + spec["visual_subjects"])
            spec["review_reasons"] = []
            return spec
        def alias_glyph(canvas, spec, **kwargs):
            if spec["secondary_subject"] == "interview":
                spec = {**spec, "secondary_subject": "language"}
            return draw(canvas, spec, **kwargs)
        with tempfile.TemporaryDirectory() as d, patch.object(art, "choose_concept", side_effect=alias_pair), \
                patch.object(art, "candidate_specs", side_effect=lambda inputs: [art.choose_concept(inputs)]), \
                patch.object(art, "draw_subject", side_effect=alias_glyph):
            art.attach_art(rows, Path(d))
        a, b = (row["editorial_art"] for row in rows)
        self.assertNotEqual(a["foreground_signature"], b["foreground_signature"])
        self.assertNotEqual(a["composition_fingerprint"], b["composition_fingerprint"])
        self.assertEqual(a["foreground_geometry_fingerprint"], b["foreground_geometry_fingerprint"])
        self.assertIn("duplicate_foreground_geometry", b["review_reasons"])
        self.assertNotIn("src", b)

    def test_geometry_guard_is_independent_of_semantic_labels(self):
        rows = [article(doi="10.1234/a"), article("Clinical stress and insomnia", "10.1234/b")]
        with tempfile.TemporaryDirectory() as d, patch.object(art, "render_svg", return_value=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 760"><rect x="200" y="100" width="800" height="550" fill="#171714"/></svg>'):
            art.attach_art(rows, Path(d))
        a, b = (row["editorial_art"] for row in rows)
        self.assertNotEqual(a["semantic_signature"], b["semantic_signature"])
        self.assertNotEqual(a["foreground_signature"], b["foreground_signature"])
        self.assertEqual(b["status"], "needs_review")
        self.assertIn("duplicate_composition", b["review_reasons"])
        self.assertNotIn("src", b)

    def test_tiny_decorative_difference_cannot_evade_coarse_visual_twin_guard(self):
        rows = [article(doi="10.1234/a"), article("Clinical stress and insomnia", "10.1234/b")]
        def almost_same_scene(identity, inputs, spec, **kwargs):
            extra = '<rect x="1100" y="700" width="12" height="12" fill="#E00122"/>' if identity.endswith("/b") else ""
            return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 760">'
                    '<rect x="200" y="100" width="800" height="550" fill="#171714"/>' + extra + '</svg>').encode()
        with tempfile.TemporaryDirectory() as d, patch.object(art, "render_svg", side_effect=almost_same_scene):
            art.attach_art(rows, Path(d))
            summary = art.report(rows, Path(d))
        a, b = (row["editorial_art"] for row in rows)
        self.assertNotEqual(a["semantic_signature"], b["semantic_signature"])
        self.assertNotEqual(a["foreground_geometry_fingerprint"], b["foreground_geometry_fingerprint"])
        self.assertNotEqual(a["composition_fingerprint"], b["composition_fingerprint"])
        self.assertIn("near_visual_twin", b["review_reasons"])
        self.assertNotIn("src", b)
        self.assertEqual(summary["needs_review_count"], 1)
        self.assertTrue(summary["near_visual_twin_candidates"])

    def test_known_v1_duplicate_scene_is_caught_despite_different_geometry_bytes(self):
        import art_similarity
        fixtures = ROOT / "tests/fixtures/article-art-duplicates"
        left = (fixtures / "baseline-offloading-framework.svg").read_bytes()
        right = (fixtures / "baseline-offloading-students.svg").read_bytes()
        self.assertNotEqual(left, right)
        scores = art_similarity.compare(art_similarity.rasterize(left), art_similarity.rasterize(right))
        self.assertTrue(art_similarity.is_near_twin(scores), scores)

    def test_distinct_dominant_scenes_pass_the_coarse_visual_guard(self):
        rows = [article(doi="10.1234/a"), article("Clinical stress and insomnia", "10.1234/b")]
        def distinct_scene(identity, inputs, spec, **kwargs):
            shape = ('<circle cx="900" cy="350" r="230" fill="#E00122"/>' if identity.endswith("/b") else
                     '<rect x="100" y="100" width="300" height="550" fill="#171714"/>')
            return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 760">' + shape + '</svg>').encode()
        with tempfile.TemporaryDirectory() as d, patch.object(art, "render_svg", side_effect=distinct_scene):
            art.attach_art(rows, Path(d))
        self.assertEqual([row["editorial_art"]["status"] for row in rows], ["ready", "ready"])

    def test_unsupported_similarity_rendering_is_held_instead_of_bypassing_guard(self):
        import art_similarity
        row = article()
        before = copy.deepcopy(row)
        with tempfile.TemporaryDirectory() as d, patch.object(art_similarity, "rasterize", side_effect=ValueError("Unsupported SVG command")):
            art.attach_art([row], Path(d))
        result = row.pop("editorial_art")
        self.assertEqual(row, before)
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("visual_similarity_unavailable", result["review_reasons"])
        self.assertNotIn("src", result)

    def test_insufficient_context_never_uses_a_tag_or_generic_cover(self):
        row = article("A new perspective on contemporary questions")
        row["reading"]["digest"] = {"idea": "A new perspective.", "tags": ["Metacognition", "Learning", "Mathematics"]}
        row["visual"] = {"kind": "source_figure", "src": "https://example.org/verified-figure.png", "provenance": "Verified permission"}
        row["source_quality"] = {"decision": "include", "evidence": "Preserve this source review"}
        before = copy.deepcopy(row)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            art.attach_art([row], root)
            result = row.pop("editorial_art")
            self.assertEqual(result["status"], "needs_review")
            self.assertIn("insufficient_specific_context", result["review_reasons"])
            self.assertNotIn("src", result)
            self.assertFalse((root / "assets/article-art").exists())
            self.assertEqual(row, before)

    def test_same_canonical_paper_can_appear_more_than_once(self):
        rows = [article(), article(doi="https://doi.org/10.1234/EXAMPLE")]
        with tempfile.TemporaryDirectory() as d:
            art.attach_art(rows, Path(d))
            self.assertEqual(rows[0]["editorial_art"], rows[1]["editorial_art"])
            self.assertEqual(rows[0]["editorial_art"]["status"], "ready")
            self.assertFalse(art.report(rows, Path(d))["semantic_collision_groups"])

    def test_unchanged_accepted_paper_keeps_art_when_a_later_duplicate_arrives(self):
        existing = article(doi="10.1234/z-existing")
        newcomer = article(doi="10.1234/a-new")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            art.attach_art([existing], root)
            accepted = copy.deepcopy(existing["editorial_art"])
            rows = art.attach_art([newcomer, existing], root)
            self.assertEqual(existing["editorial_art"], accepted)
            self.assertEqual(newcomer["editorial_art"]["status"], "ready")
            self.assertGreater(newcomer["editorial_art"]["candidate_index"], 0)
            again = art.attach_art(copy.deepcopy(list(reversed(rows))), root)
            self.assertEqual([row["editorial_art"] for row in rows], list(reversed([row["editorial_art"] for row in again])))

    def test_changed_public_text_regenerates_without_changing_evidence(self):
        record = article()
        record["visual"] = visual_spec(record)
        before = copy.deepcopy(record)
        with tempfile.TemporaryDirectory() as d:
            first = art.create_art(record, Path(d))
            self.assertEqual(record, before)
            record["title"] = "Critical thinking and verification in undergraduate mathematics"
            record["reading"]["digest"]["idea"] = record["title"]
            second = art.create_art(record, Path(d))
            self.assertNotEqual(first["input_fingerprint"], second["input_fingerprint"])
            self.assertNotEqual(first["src"], second["src"])
            self.assertEqual(record["visual"], before["visual"])

    def test_metadata_and_collection_date_changes_do_not_churn_art(self):
        record = article()
        with tempfile.TemporaryDirectory() as d:
            before = art.create_art(record, Path(d))
            record.update(first_seen="2099-01-01", published="2099-02-01", citation_count=200)
            record["analysis"] = {"statistics": "not an illustration instruction"}
            self.assertEqual(before, art.create_art(record, Path(d)))

    def test_changed_digest_invalidates_cache_but_does_not_draw_the_finding(self):
        record = article()
        with tempfile.TemporaryDirectory() as d:
            before = art.create_art(record, Path(d))
            record["reading"]["digest"]["finding"] = "An unverified claim of 99 percent improvement."
            after = art.create_art(record, Path(d))
            self.assertNotEqual(before["input_fingerprint"], after["input_fingerprint"])
            self.assertEqual(before["src"], after["src"])
            self.assertEqual(before["composition_fingerprint"], after["composition_fingerprint"])
            self.assertEqual(before["concept"], after["concept"])
            self.assertEqual(before["motif"], after["motif"])
            self.assertNotIn(b"percent", (Path(d) / after["src"]).read_bytes())

    def test_hash_never_selects_meaning(self):
        left, right = article(), article(doi="10.1234/other")
        a, b = art.choose_concept(art.public_inputs(left)), art.choose_concept(art.public_inputs(right))
        self.assertEqual(a, b)
        with tempfile.TemporaryDirectory() as d:
            aa, bb = art.create_art(left, Path(d)), art.create_art(right, Path(d))
            self.assertEqual((Path(d) / aa["src"]).read_bytes(), (Path(d) / bb["src"]).read_bytes())
            self.assertEqual(aa["composition_fingerprint"], bb["composition_fingerprint"])

    def test_context_and_relationship_change_objects_not_only_color(self):
        a = article("Critical thinking in students", "10.1234/context")
        b = article("Critical thinking in the workplace", "10.1234/context")
        sa, sb = art.choose_concept(art.public_inputs(a)), art.choose_concept(art.public_inputs(b))
        self.assertEqual(sa["motif"], sb["motif"])
        self.assertNotEqual(sa["context"], sb["context"])
        # Different scene structures, not an embedded title making bytes unique.
        xa = ET.fromstring(art.render_svg("same", art.public_inputs(a), sa))
        xb = ET.fromstring(art.render_svg("same", art.public_inputs(b), sb))
        self.assertNotEqual(sa["visual_subjects"], sb["visual_subjects"])
        self.assertNotEqual([node.get("d") for node in xa.iter()], [node.get("d") for node in xb.iter()])

    def test_topic_fallback_is_honestly_labeled(self):
        row = article("Some new paper")
        row["reading"]["digest"] = {"tags": ["Metacognition"]}
        spec = art.choose_concept(art.public_inputs(row))
        self.assertEqual(spec["semantic_basis"], "topic_fallback")
        self.assertEqual(spec["motif"], "reflection")
        self.assertTrue(spec["concept"].startswith("Topic-based illustration:"))
        self.assertIn(row["title"], spec["concept"])

    def test_newly_admitted_readings_have_valid_art_after_real_rebuild(self):
        # Test the current registry, not only the last checked-in projection.
        # Newly admitted commentary may need review rather than topic fallback
        # artwork. Keep the real build-before-validation production order.
        import original_readings
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            data = root / "data"
            shutil.copytree(ROOT / "data", data)
            shutil.copytree(ROOT / "assets/editorial-covers", root / "assets/editorial-covers")
            with patch.object(build_public, "DATA", data), patch.object(original_readings, "MANIFEST", data / "original-readings.json"):
                rebuilt, _ = build_public.build()
            self.assertTrue(rebuilt)
            for row in rebuilt:
                illustration = row["editorial_art"]
                if illustration["status"] == "ready":
                    self.assertTrue((root / illustration["src"]).is_file())
                else:
                    self.assertEqual(illustration["status"], "needs_review")
                    self.assertTrue(illustration["review_reasons"])
                    self.assertNotIn("src", illustration)
                    self.assertNotIn("thumbnail_src", illustration)
                if illustration["semantic_basis"] != "editor_selected":
                    self.assertIn(row["title"], illustration["concept"])
                    self.assertIn("Not a depiction of study results", illustration["alt"])

    def test_canonical_identity_normalizes_doi_tracking_but_not_meaningful_urls(self):
        variants = ({"doi": "10.1234/ABC"}, {"doi": "https://doi.org/10.1234/abc"},
                    {"url": "https://dx.doi.org/10.1234/ABC"}, {"doi": "DOI:10.1234/Abc"})
        self.assertEqual({art.canonical_identity(v) for v in variants}, {"doi:10.1234/abc"})
        a = art.canonical_identity({"url": "https://EXAMPLE.com:443/Path?utm_source=x&item=1#section"})
        self.assertEqual(a, "url:https://example.com/Path?item=1")
        self.assertNotEqual(a, art.canonical_identity({"url": "https://example.com/path?item=1"}))
        self.assertNotEqual(a, art.canonical_identity({"url": "https://example.com/Path?item=2"}))

    def test_untrusted_identifiers_cannot_inject_paths_or_svg(self):
        row = article('<script>alert(1)</script> ../../bad " <image href="https://evil.test"> Mathematical learning in undergraduate students', "../../../../bad<script>")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a = art.create_art(row, root)
            path = root / a["src"]
            self.assertTrue(path.resolve().is_relative_to(root / "assets/article-art"))
            self.assertNotIn(b"script", path.read_bytes())
            self.assertNotIn(b"evil.test", path.read_bytes())
        for url in ("javascript:alert(1)", "file:///etc/passwd", "https://user:secret@example.org"):
            with self.assertRaises(ValueError):
                art.canonical_identity({"url": url})
        with self.assertRaises(ValueError):
            art.canonical_identity({})

    def test_generated_svg_vocabulary_has_no_script_text_external_refs_or_data_charts(self):
        allowed = {"svg", "g", "path", "rect", "circle"}
        with tempfile.TemporaryDirectory() as d:
            rows = public_records()
            art.attach_art(rows, Path(d))
            for row in rows:
                if row["editorial_art"]["status"] == "needs_review":
                    self.assertNotIn("src", row["editorial_art"])
                    continue
                data = (Path(d) / row["editorial_art"]["src"]).read_bytes()
                root = ET.fromstring(data)
                for node in root.iter():
                    self.assertIn(node.tag.split("}")[-1], allowed)
                    for key, value in node.attrib.items():
                        self.assertFalse(key.lower().startswith("on"))
                        self.assertNotIn("href", key)
                        self.assertNotIn("url(", value)
                self.assertNotIn(b"<text", data)
                self.assertNotIn(b"<title", data)
                self.assertNotIn(b"foreignObject", data)

    def test_title_fallback_is_distinct_safe_and_stable(self):
        a, b = {"title": "No DOI / one"}, {"title": "No DOI / two"}
        self.assertTrue(art.canonical_identity(a).startswith("title:"))
        self.assertNotEqual(art.canonical_identity(a), art.canonical_identity(b))
        self.assertEqual(art.canonical_identity(a), art.canonical_identity(copy.deepcopy(a)))

    def test_generated_directory_cannot_escape_via_symlink(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            root = Path(d)
            (root / "assets").mkdir()
            (root / "assets/article-art").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                art.create_art(article(), root)


class OverrideTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "assets/editorial-covers").mkdir(parents=True)
        (self.root / "assets/editorial-covers/cover.png").write_bytes(png())
        (self.root / "assets/editorial-covers/small.png").write_bytes(png(6, 4))
        self.value = {"src": "assets/editorial-covers/cover.png", "alt": "A hand arranging pages.",
                      "concept": "Reconstructing ideas.", "provenance": "Original commissioned editorial illustration.",
                      "width": 12, "height": 8, "thumbnail_src": "assets/editorial-covers/small.png"}

    def manifest(self, value=None, identity="doi:10.1234/example"):
        p = self.root / "data/article-art-overrides.json"
        p.write_text(json.dumps({"version": 1, "overrides": {identity: self.value if value is None else value}}))
        return p

    def test_valid_override_retains_real_provenance_dimensions_thumbnail(self):
        self.manifest()
        row = article()
        art.attach_art([row], self.root)
        out = row["editorial_art"]
        for key in ("src", "alt", "concept", "provenance", "width", "height", "thumbnail_src"):
            self.assertEqual(out[key], self.value[key])
        self.assertEqual(out["semantic_basis"], "editor_selected")
        self.assertEqual(out["status"], "ready")
        self.assertEqual(out["source_grounding"][0]["phrases"], [self.value["concept"]])
        self.assertEqual(out["thumbnail_width"], 6)
        self.assertFalse((self.root / "assets/article-art").exists())

    def test_explicit_editorial_override_survives_missing_keyword_context(self):
        self.manifest()
        row = article("A new perspective")
        art.attach_art([row], self.root)
        self.assertEqual(row["editorial_art"]["status"], "ready")
        self.assertEqual(row["editorial_art"]["src"], self.value["src"])
        self.assertEqual(row["editorial_art"]["review_reasons"], [])
        self.assertEqual(row["editorial_art"]["visual_subjects"], [])

    def test_identical_raster_bytes_under_different_names_are_held(self):
        renamed = "assets/editorial-covers/renamed.png"
        (self.root / renamed).write_bytes((self.root / self.value["src"]).read_bytes())
        self.manifest().write_text(json.dumps({"version": 1, "overrides": {
            "doi:10.1234/example": self.value,
            "doi:10.1234/second": {**self.value, "src": renamed, "concept": "A different declared concept."}}}))
        rows = [article(), article("A second paper", "10.1234/second")]
        art.attach_art(rows, self.root)
        a, b = (row["editorial_art"] for row in rows)
        self.assertEqual(a["status"], "ready")
        self.assertEqual(b["status"], "needs_review")
        self.assertIn("duplicate_asset_bytes", b["review_reasons"])
        self.assertEqual(b["retry_status"], "editorial_review")
        self.assertEqual(b["attempt_count"], 1)
        self.assertEqual(b["candidate_count"], 1)
        self.assertFalse((self.root / art.GENERATED_DIR).exists())
        self.assertEqual(a["asset_fingerprint"], b["asset_fingerprint"])
        self.assertNotIn("src", b)
        self.assertNotIn("thumbnail_src", b)

    def test_reused_path_is_reviewable_rather_than_a_malformed_manifest(self):
        self.manifest().write_text(json.dumps({"version": 1, "overrides": {
            "doi:10.1234/example": self.value,
            "doi:10.1234/second": {**self.value, "concept": "A different declared concept."}}}))
        rows = [article(), article("A second paper", "10.1234/second")]
        art.attach_art(rows, self.root)
        self.assertEqual(rows[0]["editorial_art"]["status"], "ready")
        self.assertEqual(rows[1]["editorial_art"]["status"], "needs_review")
        self.assertIn("duplicate_asset_bytes", rows[1]["editorial_art"]["review_reasons"])

    def test_distinct_covers_cannot_hide_a_duplicated_card_thumbnail(self):
        other = "assets/editorial-covers/other.png"
        (self.root / other).write_bytes(png(24, 16))
        self.manifest().write_text(json.dumps({"version": 1, "overrides": {
            "doi:10.1234/example": self.value,
            "doi:10.1234/second": {**self.value, "src": other, "width": 24, "height": 16,
                                   "concept": "A different declared concept."}}}))
        rows = [article(), article("A second paper", "10.1234/second")]
        art.attach_art(rows, self.root)
        a, b = (row["editorial_art"] for row in rows)
        self.assertNotEqual(a["asset_fingerprint"], b["asset_fingerprint"])
        self.assertEqual(b["status"], "needs_review")
        self.assertIn("duplicate_thumbnail_bytes", b["review_reasons"])
        self.assertNotIn("src", b)
        self.assertNotIn("thumbnail_src", b)

    def test_absent_override_generates_safe_existing_svg(self):
        row = article()
        art.attach_art([row], self.root)
        self.assertTrue((self.root / row["editorial_art"]["src"]).is_file())
        self.assertEqual(row["editorial_art"]["format"], "svg")

    def test_invalid_paths_missing_files_and_metadata_fail_before_publication(self):
        for change in ({"src": "https://example.com/cover.webp"}, {"src": "assets/../cover.png"},
                       {"src": "/assets/editorial-covers/cover.png"}, {"src": "assets/editorial-covers/nope.png"},
                       {"src": "assets/editorial-covers/cover.svg"}, {"src": "assets/editorial-covers//cover.png"},
                       {"src": "assets/editorial-covers/%2e%2e/cover.png"}, {"src": "assets/editorial-covers/bad_name.png"},
                       {"src": "assets/editorial-covers/sub/cover.png"}, {"src": "assets/editorial-covers/cover.jpeg"}, {"alt": ""}, {"provenance": ""},
                       {"concept": ""}, {"width": 1200}, {"thumbnail_src": "https://example.org/thumb.webp"}):
            with self.subTest(change=change):
                self.manifest({**self.value, **change})
                row = article()
                with self.assertRaises(ValueError):
                    art.attach_art([row], self.root)
                self.assertNotIn("editorial_art", row)

    def test_fake_image_oversize_and_symlink_escape_rejected(self):
        p = self.root / "assets/editorial-covers/cover.png"
        for content in (b"not an image", b"x" * (art.MAX_OVERRIDE_BYTES + 1)):
            p.write_bytes(content)
            self.manifest()
            with self.assertRaises(ValueError):
                art.load_overrides(self.root)
        p.unlink()
        with tempfile.TemporaryDirectory() as d:
            outside = Path(d) / "cover.png"
            outside.write_bytes(png())
            p.symlink_to(outside)
            with self.assertRaises(ValueError):
                art.load_overrides(self.root)

    def test_bad_manifest_schema_and_noncanonical_key_rejected(self):
        p = self.manifest()
        for content in ([], {"version": 2, "overrides": {}}, {"version": 1, "overrides": []}):
            p.write_text(json.dumps(content))
            with self.assertRaises(ValueError):
                art.load_overrides(self.root)
        for identity in ("10.1234/example", "doi:10.1234/EXAMPLE", "url:https://example.org/?utm_source=x"):
            self.manifest(identity=identity)
            with self.assertRaises(ValueError):
                art.load_overrides(self.root)


class PublicationBoundaryTests(unittest.TestCase):
    def test_full_build_preserves_all_evidence_when_art_is_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d) / "data"
            data.mkdir()
            for name in ("library.json", "weekly.json"):
                (data / name).write_bytes((ROOT / "data" / name).read_bytes())
            with patch.object(build_public, "DATA", data):
                with patch.object(build_public, "attach_art", lambda *args, **kwargs: None):
                    baseline, baseline_week = build_public.build()
                decorated, decorated_week = build_public.build()
            for row in decorated:
                row.pop("editorial_art", None)
            self.assertEqual(baseline, decorated)
            self.assertEqual(baseline_week, decorated_week)

    def test_checked_in_featured_overrides_resolve_to_real_assets(self):
        overrides = art.load_overrides(ROOT)
        for identity, override in overrides.items():
            self.assertEqual(override["width"], 1200)
            self.assertEqual(override["height"], 800)
            self.assertTrue((ROOT / override["src"]).is_file())
            if "thumbnail_src" in override:
                self.assertEqual(override["thumbnail_width"], 320)
                self.assertTrue((ROOT / override["thumbnail_src"]).is_file())

    def test_art_runs_after_publication_gates_and_never_promotes_pending_records(self):
        valid = public_records()[0]
        citation = {"kind": "scholarly", "doi": "10.1234/citation-only", "title": "Generative AI and critical thinking",
                    "venue": "Computers in Human Behavior", "reading": {"level": "citation_only"}}
        engineering = {"kind": "scholarly", "doi": "10.1234/computational", "title": "Cross-attention image classification",
                       "venue": "Scientific Reports", "abstract_text": "Image model architecture." * 20}
        pending = {"kind": "nonacademic", "url": "https://example.org/pending-news", "title": "AI and attention",
                   "source": "Publisher RSS", "reading": {"level": "source_preview", "overview": "A short headline."}}
        rows = [valid, citation, engineering, pending]
        with tempfile.TemporaryDirectory() as d:
            data = Path(d) / "data"
            data.mkdir()
            (data / "library.json").write_text(json.dumps(rows))
            (data / "weekly.json").write_text(json.dumps({"run": {}, "items": rows}))
            with patch.object(build_public, "DATA", data):
                selected, week = build_public.build()
            self.assertEqual(len(selected), 1)
            self.assertEqual(len(week["items"]), 1)
            a = selected[0]["editorial_art"]
            self.assertTrue((Path(d) / a["src"]).is_file())
            self.assertEqual(len(list((Path(d) / "assets/article-art").glob("*.svg"))), 1)
            self.assertEqual(selected[0]["visual"], visual_spec(selected[0]))
            hidden = json.loads((data / "public-pending-sources.json").read_text())
            self.assertTrue(hidden)
            self.assertTrue(all("editorial_art" not in r for r in hidden))

    def test_contact_sheet_and_report_are_safe_repeatable_deliverables(self):
        row = article('<script>alert("x")</script> critical thinking in undergraduate mathematics')
        pending = article("A new perspective", "10.1234/pending")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            art.attach_art([row, pending], root)
            target = root / "review/contact.html"
            art.contact_sheet([row, pending], root, target)
            self.assertNotIn('<script>', target.read_text())
            self.assertIn('&lt;script&gt;', target.read_text())
            self.assertIn('Artwork needs review', target.read_text())
            self.assertEqual(target.read_text().count('<img '), 1)
            first = target.read_bytes()
            art.contact_sheet([row, pending], root, target)
            self.assertEqual(first, target.read_bytes())
            summary = art.report([row, pending], root)
            self.assertEqual(summary["article_count"], 2)
            self.assertEqual(summary["unique_asset_count"], 1)
            self.assertEqual(summary["ready_count"], 1)
            self.assertEqual(summary["needs_review_count"], 1)
            self.assertEqual(summary["review_reasons"], {"insufficient_specific_context": 1})
            self.assertNotIn("generated_at", summary)

    def test_cli_refuses_internal_acquisition_index(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/article_art.py"),
                                 "--public-library", str(ROOT / "data/library.json")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already-gated", result.stderr)


if __name__ == "__main__":
    unittest.main()

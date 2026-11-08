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


def article(title="Cognitive offloading in learning", doi="10.1234/example"):
    return {"doi": doi, "title": title, "kind": "scholarly", "reading": {"level": "abstract",
        "digest": {"idea": title, "explain": "Examining how people use tools."}}}


def png(width=12, height=8):
    def chunk(kind, value):
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress((b"\x00" + b"\xe0\x01\x22" * width) * height)) + chunk(b"IEND", b""))


class ArticleArtTests(unittest.TestCase):
    def test_actual_public_records_have_unique_existing_assets_and_small_budget(self):
        records = public_records()
        self.assertGreater(len(records), 50)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            art.attach_art(records, root)
            paths = [r["editorial_art"]["src"] for r in records]
            contents = [(root / p).read_bytes() for p in paths]
            self.assertEqual(len(paths), len(set(paths)))
            self.assertEqual(len(contents), len(set(contents)))
            # Real shape/object/setting differences, with all identity-based
            # rotation/position/print microvariation disabled in this digest.
            self.assertEqual(len(records), len({r["editorial_art"]["composition_fingerprint"] for r in records}))
            self.assertLess(sum(map(len, contents)), 600_000)
            self.assertLess(max(map(len, contents)), art.MAX_SVG_BYTES)
            self.assertGreaterEqual(len({r["editorial_art"]["motif"] for r in records}), 12)
            for r in records:
                a = r["editorial_art"]
                self.assertEqual(a["kind"], "editorial_illustration")
                self.assertIn("Not a depiction of study results", a["alt"])
                self.assertIn(r["title"], a["concept"])
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
                    images.append((Path(d) / a["src"]).read_bytes())
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
        records = [article("Cognitive offloading", "10.1234/a"), article("Metacognition", "10.1234/b")]
        with tempfile.TemporaryDirectory() as d:
            forward = art.attach_art(copy.deepcopy(records), Path(d))
            backward = art.attach_art(list(reversed(copy.deepcopy(records))), Path(d))
            self.assertEqual([r["editorial_art"] for r in forward], list(reversed([r["editorial_art"] for r in backward])))

    def test_changed_public_text_regenerates_without_changing_evidence(self):
        record = article()
        record["visual"] = visual_spec(record)
        before = copy.deepcopy(record)
        with tempfile.TemporaryDirectory() as d:
            first = art.create_art(record, Path(d))
            self.assertEqual(record, before)
            record["reading"]["digest"]["idea"] = "Accountable reconstruction without AI."
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
            self.assertNotEqual(before["src"], after["src"])
            self.assertEqual(before["concept"], after["concept"])
            self.assertEqual(before["motif"], after["motif"])
            self.assertNotIn(b"percent", (Path(d) / after["src"]).read_bytes())

    def test_hash_never_selects_meaning(self):
        left, right = article(), article(doi="10.1234/other")
        a, b = art.choose_concept(art.public_inputs(left)), art.choose_concept(art.public_inputs(right))
        self.assertEqual(a, b)
        with tempfile.TemporaryDirectory() as d:
            aa, bb = art.create_art(left, Path(d)), art.create_art(right, Path(d))
            self.assertNotEqual((Path(d) / aa["src"]).read_bytes(), (Path(d) / bb["src"]).read_bytes())

    def test_context_and_relationship_change_objects_not_only_color(self):
        a = article("Critical thinking in students", "10.1234/context")
        b = article("Critical thinking in the workplace", "10.1234/context")
        sa, sb = art.choose_concept(art.public_inputs(a)), art.choose_concept(art.public_inputs(b))
        self.assertEqual(sa["motif"], sb["motif"])
        self.assertNotEqual(sa["context"], sb["context"])
        # Different scene structures, not an embedded title making bytes unique.
        xa = ET.fromstring(art.render_svg("same", art.public_inputs(a), sa))
        xb = ET.fromstring(art.render_svg("same", art.public_inputs(b), sb))
        self.assertNotEqual(len(list(xa.iter())), len(list(xb.iter())))

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
        # Newly admitted commentary can use a topic fallback absent from that
        # older file. Keep the real build-before-validation production order.
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
                self.assertTrue((root / illustration["src"]).is_file())
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
        row = article('<script>alert(1)</script> ../../bad " <image href="https://evil.test">', "../../../../bad<script>")
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
        self.assertEqual(out["thumbnail_width"], 6)
        self.assertFalse((self.root / "assets/article-art").exists())

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
        row = article('<script>alert("x")</script> critical thinking')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            art.attach_art([row], root)
            target = root / "review/contact.html"
            art.contact_sheet([row], root, target)
            self.assertNotIn('<script>', target.read_text())
            self.assertIn('&lt;script&gt;', target.read_text())
            first = target.read_bytes()
            art.contact_sheet([row], root, target)
            self.assertEqual(first, target.read_bytes())
            summary = art.report([row], root)
            self.assertEqual(summary["article_count"], 1)
            self.assertEqual(summary["unique_asset_count"], 1)
            self.assertNotIn("generated_at", summary)

    def test_cli_refuses_internal_acquisition_index(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/article_art.py"),
                                 "--public-library", str(ROOT / "data/library.json")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already-gated", result.stderr)


if __name__ == "__main__":
    unittest.main()

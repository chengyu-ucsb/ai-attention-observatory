"""Offline durable allocation/retry and publication boundary regressions."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import article_art as art
import article_art_queue as queue
import build_public


def article(doi="10.1234/a", title="Cognitive offloading in doctoral work"):
    return {"doi": doi, "title": title, "kind": "scholarly",
            "reading": {"level": "abstract", "digest": {"idea": title,
                         "explain": "Examining how people use tools."}}}


def png():
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 12, 8, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress((b"\x00" + b"\xe0\x01\x22" * 12) * 8)) + chunk(b"IEND", b""))


def approved_pair(root, identity, registry):
    """Register an actual previously inspected issue cover under the test identity."""
    import shutil
    cover = dict(next(iter(json.loads((ROOT / "data/article-art-overrides.json").read_text())["overrides"].values())))
    for key in ("src", "thumbnail_src"):
        target = root / cover[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / cover[key], target)
    validated = art.validated_override(root.resolve(), identity, cover)
    cover["commission_review"] = {"method": queue.COMMISSION_METHOD,
                                  "sha256": queue.review_fingerprint(identity, validated)}
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({"version": 1, "overrides": {identity: cover}}))
    return cover


class ArticleArtQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state_path = self.root / "data" / queue.STATE_FILENAME

    def run_art(self, rows, **kwargs):
        return queue.attach_persistent_art(rows, self.root, **kwargs)

    def stored(self):
        return json.loads(self.state_path.read_text())

    def test_unchanged_exhausted_pool_skips_candidates_and_has_no_fake_progress(self):
        rows = [article(), article("10.1234/b")]
        before_sources = copy.deepcopy(rows)
        self.run_art(rows)
        self.assertEqual(rows[1]["editorial_art"]["retry_status"], "exhausted")
        before = copy.deepcopy(rows)
        state = self.state_path.read_bytes()
        mtime = self.state_path.stat().st_mtime_ns
        # Fresh source records, not mutated public records, reproduce actual builds.
        with patch.object(art, "create_art", wraps=art.create_art) as create:
            again = self.run_art(copy.deepcopy(before_sources))
        self.assertEqual(create.call_count, 1)  # Accepted owner is revalidated.
        self.assertEqual(again, before)
        self.assertEqual(state, self.state_path.read_bytes())
        self.assertEqual(mtime, self.state_path.stat().st_mtime_ns)
        held = self.stored()["articles"]["doi:10.1234/b"]
        self.assertEqual(held["attempt_count"], 1)
        self.assertNotIn("src", held)
        self.assertNotIn("thumbnail_src", held)
        for original, decorated in zip(before_sources, rows):
            self.assertEqual(original, {key: value for key, value in decorated.items() if key != "editorial_art"})

    def test_new_grounded_context_resolves_prior_collision(self):
        rows = [article(), article("10.1234/b")]
        self.run_art(rows)
        prior = self.stored()["articles"]["doi:10.1234/b"]
        self.assertEqual(prior["retry_status"], "exhausted")
        rows[1]["abstract_text"] = "Doctoral researchers completed mathematical learning activities and conducted interviews in a workplace setting."
        self.run_art(rows)
        accepted = rows[1]["editorial_art"]
        self.assertEqual(accepted["status"], "ready")
        self.assertGreater(accepted["candidate_index"], 0)
        self.assertNotEqual(accepted["candidate_pool_fingerprint"], prior["candidate_pool_fingerprint"])
        self.assertTrue((self.root / accepted["src"]).is_file())
        self.assertEqual(self.stored()["articles"]["doi:10.1234/b"]["retry_status"], "accepted")

    def test_accepted_alternative_survives_clean_rebuild_reorder_and_newcomer(self):
        title = "Doctoral academic writing"
        sources = [article("10.1234/b-existing", title), article("10.1234/z-alternative", title)]
        rows = self.run_art(copy.deepcopy(sources))
        accepted = copy.deepcopy(rows[1]["editorial_art"])
        self.assertGreater(accepted["candidate_index"], 0)
        again = self.run_art(list(reversed(copy.deepcopy(sources))))
        self.assertEqual(again[0]["editorial_art"], accepted)
        again = self.run_art([article("10.1234/a-new", title)] + copy.deepcopy(sources))
        self.assertEqual(again[2]["editorial_art"], accepted)
        self.assertEqual(self.stored()["articles"]["doi:10.1234/z-alternative"]["retry_attempts"], accepted["retry_attempts"])

    def test_removed_owner_releases_collision_and_is_pruned(self):
        rows = [article(), article("10.1234/b")]
        self.run_art(rows)
        self.assertEqual(rows[1]["editorial_art"]["status"], "needs_review")
        remaining = self.run_art([article("10.1234/b")])
        self.assertEqual(remaining[0]["editorial_art"]["status"], "ready")
        self.assertEqual(set(self.stored()["articles"]), {"doi:10.1234/b"})
        self.run_art([])
        self.assertEqual(self.stored()["articles"], {})

    def test_missing_context_is_not_retried_without_changed_input(self):
        source = article(title="A new perspective")
        self.run_art([copy.deepcopy(source)])
        before = self.state_path.read_bytes()
        with patch.object(art, "create_art", side_effect=AssertionError("No changed candidates")):
            self.run_art([copy.deepcopy(source)])
        self.assertEqual(before, self.state_path.read_bytes())
        self.assertEqual(self.stored()["retry_status_counts"], {"insufficient_context": 1})

    def test_previous_public_projection_seeds_only_current_verified_allocations(self):
        previous = self.run_art([article("10.1234/z-existing")])
        public = self.root / "public-library.json"
        public.write_text(json.dumps(previous + [{"doi": "10.1234/removed", "editorial_art": previous[0]["editorial_art"]}]))
        self.state_path.unlink()
        rows = self.run_art([article("10.1234/a-new"), article("10.1234/z-existing")], previous_public=public)
        self.assertEqual(rows[0]["editorial_art"]["status"], "needs_review")
        self.assertEqual(rows[1]["editorial_art"], previous[0]["editorial_art"])
        self.assertNotIn("doi:10.1234/removed", self.stored()["articles"])

    def test_malformed_and_stale_state_rebuild_safely(self):
        cases = ["{bad json", "[]", '{"version":999,"articles":{}}',
                 '{"version":1,"articles":{"doi:10.1234/a":{"status":[]}}}',
                 '{"version":1,"articles":{"doi:10.1234/a":{"status":"ready","candidate_index":"oops","retry_status":{}}}}']
        self.state_path.parent.mkdir()
        for bad in cases:
            with self.subTest(bad=bad):
                self.state_path.write_text(bad)
                row = self.run_art([article()])[0]
                self.assertEqual(row["editorial_art"]["status"], "ready")
                self.assertEqual(set(queue.load_state(self.state_path)["articles"]), {"doi:10.1234/a"})

    def test_malformed_exhaustion_ledgers_cannot_suppress_real_candidate_search(self):
        self.run_art([article()])
        original = self.stored()
        for mutation in (
            {"attempt_count": 0, "retry_attempts": []},
            {"candidate_fingerprint": "0" * 64},
            {"candidate_index": 6},
            {"candidate_count": 6},
            {"retry_attempts": [{"candidate_index": 6, "candidate_fingerprint": "0" * 64,
                                 "status": "needs_review", "review_reasons": ["duplicate_foreground_subjects"]}]},
        ):
            with self.subTest(mutation=mutation):
                state = copy.deepcopy(original)
                value = state["articles"]["doi:10.1234/a"]
                value.update(status="needs_review", retry_status="exhausted", review_reasons=["duplicate_foreground_subjects"])
                value.update(mutation)
                self.state_path.write_text(json.dumps(state))
                with patch.object(art, "create_art", wraps=art.create_art) as create:
                    rows = self.run_art([article()])
                self.assertGreater(create.call_count, 0)
                self.assertEqual(rows[0]["editorial_art"]["status"], "ready")

    def test_invalid_accepted_allocation_prevents_stale_hold_reuse(self):
        self.run_art([article(), article("10.1234/b")])
        state = self.stored()
        state["articles"]["doi:10.1234/a"]["asset_fingerprint"] = "0" * 64
        self.state_path.write_text(json.dumps(state))
        with patch.object(art, "create_art", wraps=art.create_art) as create:
            rows = self.run_art([article(), article("10.1234/b")])
        self.assertGreaterEqual(create.call_count, 2)
        self.assertEqual(rows[0]["editorial_art"]["status"], "ready")
        self.assertEqual(rows[1]["editorial_art"]["status"], "needs_review")

    def test_curated_rejection_never_falls_back_and_source_prose_is_not_cached(self):
        covers = self.root / "assets/editorial-covers"
        covers.mkdir(parents=True)
        (covers / "same.png").write_bytes(png())
        self.state_path.parent.mkdir()
        manifest = self.state_path.parent / "article-art-overrides.json"
        concept = "Private prose sentinel about the editor's concept."
        override = {"src": "assets/editorial-covers/same.png", "alt": "Private alt sentinel.",
                    "concept": concept, "provenance": "Original editorial art."}
        manifest.write_text(json.dumps({"version": 1, "overrides": {"doi:10.1234/a": override, "doi:10.1234/b": override}}))
        rows = [article(), article("10.1234/b")]
        self.run_art(rows)
        held = rows[1]["editorial_art"]
        self.assertEqual(held["retry_status"], "editorial_review")
        self.assertEqual(held["attempt_count"], 1)
        self.assertNotIn("src", held)
        self.assertFalse((self.root / "assets/article-art").exists())
        saved = self.state_path.read_text()
        for phrase in (concept, override["alt"], rows[0]["title"], "Examining how people use tools."):
            self.assertNotIn(phrase, saved)
        for key in ("source_grounding", "concept", "alt", "source_context", "abstract_text", "reading", "matched_cues", "semantic_signature"):
            self.assertNotIn('"' + key + '"', saved)
        # Even an override-related review may not replace a human's selected art.
        with patch.object(art, "create_art", wraps=art.create_art) as create:
            self.run_art([article(), article("10.1234/b")])
        self.assertEqual(create.call_count, 1)
        self.assertEqual(saved, self.state_path.read_text())

    def test_atomic_write_failure_preserves_last_state_and_cleans_temporary_file(self):
        self.run_art([article()])
        saved = self.state_path.read_bytes()
        with patch.object(queue.os, "replace", side_effect=OSError("simulated replacement failure")):
            with self.assertRaisesRegex(OSError, "replacement failure"):
                queue.write_state(self.state_path, {"version": 1, "articles": {}})
        self.assertEqual(saved, self.state_path.read_bytes())
        self.assertEqual(list(self.state_path.parent.glob(".*.tmp")), [])

    def test_policy_change_reconsiders_exhaustion_without_cumulative_attempts(self):
        self.run_art([article(), article("10.1234/b")])
        old = self.stored()["corpus_fingerprint"]
        with patch.object(art, "CANDIDATE_POLICY_VERSION", "test-policy-2"), patch.object(art, "create_art", wraps=art.create_art) as create:
            rows = self.run_art([article(), article("10.1234/b")])
        self.assertGreaterEqual(create.call_count, 2)
        self.assertNotEqual(old, self.stored()["corpus_fingerprint"])
        self.assertEqual(rows[1]["editorial_art"]["attempt_count"], 1)


class ArtQueuePublicationTests(unittest.TestCase):
    def test_citation_quarantine_prunes_stale_queue_and_fixture_path_stays_local(self):
        public = article()
        public.update(venue="Computers in Human Behavior", abstract_text="A study of generative AI use and cognitive offloading, critical thinking and metacognition among university students. The research examines how thinking changes with repeated AI assistance.")
        citation = article("10.1234/citation", "Generative AI and critical thinking")
        citation["reading"] = {"level": "citation_only"}
        citation["venue"] = "Computers in Human Behavior"
        for dirname in ("data", "fixture-files"):
            with self.subTest(dirname=dirname), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                data = root / dirname
                data.mkdir()
                (data / "library.json").write_text(json.dumps([public, citation]))
                (data / "weekly.json").write_text(json.dumps({"run": {}, "items": [public, citation]}))
                source_bytes = (data / "library.json").read_bytes()
                art_root = root if dirname == "data" else data
                approved_pair(art_root, art.canonical_identity(public), data / "article-art-overrides.json")
                # Previously accepted art is not authority to re-admit a citation.
                queue.attach_persistent_art([article("10.1234/citation")], root,
                                            state_path=data / queue.STATE_FILENAME)
                with patch.object(build_public, "DATA", data):
                    selected, weekly = build_public.build()
                self.assertEqual(len(selected), 1)
                self.assertEqual(len(weekly["items"]), 1)
                state = json.loads((data / queue.STATE_FILENAME).read_text())
                self.assertEqual(set(state["articles"]), {art.canonical_identity(public)})
                self.assertEqual(source_bytes, (data / "library.json").read_bytes())
                self.assertFalse((root / queue.STATE_FILENAME).exists())
                if dirname != "data":
                    self.assertFalse((root / "data" / queue.STATE_FILENAME).exists())
                for name in ("public-library.json", "public-weekly.json", "public-pending-sources.json"):
                    text = (data / name).read_text()
                    self.assertNotIn('"corpus_fingerprint"', text)
                    self.assertNotIn(queue.STATE_FILENAME, text)

    def test_new_card_is_queued_before_publication_and_released_on_review(self):
        from build_reader import build as build_reader
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            source = article()
            source.update(venue="Computers in Human Behavior", abstract_text="A study of generative AI use and cognitive offloading, critical thinking and metacognition among university students. The research examines how thinking changes with repeated AI assistance.")
            identity = art.canonical_identity(source)
            (data / "library.json").write_text(json.dumps([source]))
            (data / "weekly.json").write_text(json.dumps({"run": {}, "items": [source]}))
            for name in ("public-issue.json", "public-featured-issue.json"):
                (data / name).write_text('{"status":"awaiting_publication"}')
            def build():
                with patch.object(build_public, "DATA", data):
                    return build_public.build()
            selected, weekly = build()
            self.assertFalse(selected)
            self.assertFalse(weekly["items"])
            self.assertFalse((root / "assets/article-art").exists())
            self.assertEqual(json.loads((data / queue.STATE_FILENAME).read_text())["commissioning"]["pending"],
                             {identity: "needs_original"})
            destination = root / "website"
            build_reader(root, pages_data=destination)
            self.assertEqual(json.loads((destination / "art-commissions.json").read_text()),
                             {"pending": [identity]})
            manifest = data / "article-art-overrides.json"
            approved_pair(root, identity, manifest)
            selected, weekly = build()
            self.assertEqual([r["doi"] for r in selected], [source["doi"]])
            self.assertEqual([r["doi"] for r in weekly["items"]], [source["doi"]])
            self.assertFalse(json.loads((data / queue.STATE_FILENAME).read_text())["commissioning"]["pending"])
            build_reader(root, pages_data=destination)
            self.assertEqual(json.loads((destination / "art-commissions.json").read_text()), {"pending": []})
            tracked_library = data / "public-library.json"
            good_content = tracked_library.read_bytes()
            tampered = json.loads(good_content)
            tampered[0]["editorial_art"]["concept"] = "Different picture."
            tracked_library.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError, "reader_requires_reviewed_commission"):
                build_reader(root, pages_data=destination)
            tracked_library.write_bytes(good_content)
            # A changed description needs review. Retain the previously reviewed
            # public file/description during that replacement and while text is corrected.
            edited = json.loads(manifest.read_text())
            previous_alt = edited["overrides"][identity]["alt"]
            edited["overrides"][identity]["alt"] = "Changed artwork description."
            manifest.write_text(json.dumps(edited))
            source["abstract_text"] += " This paper includes an additional classroom practice task."
            (data / "library.json").write_text(json.dumps([source]))
            selected, _ = build()
            self.assertEqual(selected[0]["editorial_art"]["alt"], previous_alt)
            self.assertIn("additional classroom", selected[0]["abstract_text"])
            self.assertEqual(json.loads((data / queue.STATE_FILENAME).read_text())["commissioning"]["pending"],
                             {identity: "needs_visual_review"})

    def test_missing_invalid_or_transplanted_pair_never_admits_a_companion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "data/article-art-overrides.json"
            record = article()
            record["companion_to"] = "10.1234/original"
            identity = art.canonical_identity(record)
            good = approved_pair(root, identity, manifest)
            cases = [(dict(good, thumbnail_src="assets/editorial-covers/absent.webp"), "invalid_registered_art"),
                     (dict(good, width=50), "invalid_registered_art"),
                     ({k: v for k, v in good.items() if k != "thumbnail_src"}, "needs_card_thumbnail"),
                     (dict(good, provenance="Source figure", commission_review={}), "needs_generation_provenance"),
                     (dict(good, commission_review={"method": queue.COMMISSION_METHOD, "sha256": "1"*64}), "needs_visual_review")]
            for override, reason in cases:
                with self.subTest(reason=reason):
                    manifest.write_text(json.dumps({"version": 1, "overrides": {identity: override}}))
                    rows = queue.attach_persistent_art([copy.deepcopy(record)], root, commissioned_only=True)
                    self.assertFalse(rows)
                    self.assertEqual(json.loads((root / "data" / queue.STATE_FILENAME).read_text())
                                     ["commissioning"]["pending"], {identity: reason})
            foreign = "doi:10.1234/different"
            manifest.write_text(json.dumps({"version": 1, "overrides": {foreign: good}}))
            other = article(doi=foreign.removeprefix("doi:"))
            self.assertFalse(queue.attach_persistent_art([other], root, commissioned_only=True))
            self.assertEqual(json.loads((root / "data" / queue.STATE_FILENAME).read_text())
                             ["commissioning"]["pending"], {foreign: "needs_visual_review"})

    def test_accepted_art_keeps_priority_after_source_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "data/article-art-overrides.json"
            old = article("10.1234/z")
            new = article("10.1234/a")
            old_id, new_id = map(art.canonical_identity, (old, new))
            override = approved_pair(root, old_id, manifest)
            output = root / "data/public-library.json"
            rows = queue.attach_persistent_art([copy.deepcopy(old)], root, commissioned_only=True)
            output.write_text(json.dumps(rows))
            prior_source = rows[0]["editorial_art"]["src"]
            new_override = copy.deepcopy(override)
            new_override["commission_review"]["sha256"] = queue.review_fingerprint(
                new_id, art.validated_override(root, new_id, new_override))
            manifest.write_text(json.dumps({"version": 1, "overrides": {old_id: override, new_id: new_override}}))
            old["abstract_text"] = "Newly corrected editorial context about doctoral work."
            rows = queue.attach_persistent_art([new, old], root, previous_public=output, commissioned_only=True)
            self.assertEqual([art.canonical_identity(row) for row in rows], [old_id])
            self.assertEqual(rows[0]["editorial_art"]["src"], prior_source)
            self.assertEqual(json.loads((root / "data" / queue.STATE_FILENAME).read_text())
                             ["commissioning"]["pending"], {new_id: "cover_rejected"})

    def test_workflows_persist_after_build_and_keep_queue_out_of_static_payload(self):
        workflows = ROOT / ".github/workflows"
        for name in ("refresh.yml", "backfill-fulltext.yml", "resume-weekly-discovery.yml", "weekly-edition.yml"):
            with self.subTest(workflow=name):
                text = (workflows / name).read_text()
                self.assertLess(text.index("python scripts/build_public.py"), text.index("git add data/"))
        publish = (workflows / "publish.yml").read_text()
        prepare = publish.split("- name: Prepare static website", 1)[1].split("- uses:", 1)[0]
        self.assertNotIn(queue.STATE_FILENAME, prepare)
        # Build reader payloads from the screened projection at the Pages boundary.
        self.assertNotRegex(prepare, r"cp -R data(?:/\.?)?\s")
        self.assertIn("python scripts/build_reader.py --pages-data _site/data", prepare)
        self.assertNotIn("cp data/public-library.json", prepare)
        self.assertNotIn("cp data/*", prepare)
        self.assertIn("contents: read", publish)
        self.assertNotIn("contents: write", publish)
        self.assertNotIn("git add", publish)
        self.assertIn("actions/upload-artifact@", publish)
        self.assertIn("path: data/" + queue.STATE_FILENAME, publish)
        self.assertIn("if-no-files-found: error", publish)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import replay_weekly_edition as release


class EditionReplayTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.original = Path(temporary.name) / "original"
        self.current = Path(temporary.name) / "current"
        self.monday = "2026-11-23"
        self.drafts = Path("data/issue-editorial.json")
        self.archive = self.current / "data/approved-issues/2026-11-23.json"
        self.audit = Path("data/edition-audits/2026-11-23.json")
        self.draft = {"headline": "Learning independently", "edition_format": "full"}
        release.write(self.original / "data/editorial-weekly.json", {"run": {"date": self.monday}})
        release.write(self.original / self.drafts, {self.monday: self.draft})
        release.write(self.original / self.audit, {"status": "validated", "source_hash": "checked"})
        release.write(self.current / self.drafts, {"2026-11-16": {"headline": "A corrected archive"}})
        release.write(self.archive, {"status": "published", "edition_format": "coverage"})
        self.policy = release.policy_signature()

    def test_unrelated_remote_changes_survive_coverage_upgrade(self):
        def build(command, **kwargs):
            if "scripts/build_newsletter.py" in command:
                current = release.read(self.current / self.drafts)
                release.write(self.archive, dict(current[self.monday], status="published"))
        with patch.object(release, "edition_ready", return_value={"ready": True}), \
             patch.object(release.subprocess, "run", side_effect=build), \
             patch.object(release, "verify_release") as verify:
            self.assertTrue(release.replay(self.original, self.current, self.policy))
        verify.assert_called_once_with(self.current)
        drafts = release.read(self.current / self.drafts)
        self.assertEqual(drafts[self.monday], self.draft)
        self.assertEqual(drafts["2026-11-16"]["headline"], "A corrected archive")

    def test_preserves_concurrent_synthesis_without_touching_any_files(self):
        release.write(self.archive, {"status": "published", "edition_format": "compact"})
        self.assertFalse(release.replay(self.original, self.current, self.policy))
        self.assertNotIn(self.monday, release.read(self.current / self.drafts))

    def test_policy_receipt_and_source_changes_stop_replay(self):
        with self.assertRaisesRegex(ValueError, "review policy"):
            release.replay(self.original, self.current, "old")
        with patch.object(release, "edition_ready", return_value={"ready": False, "status": "changed"}):
            with self.assertRaisesRegex(ValueError, "receipt changed"):
                release.replay(self.original, self.current, self.policy)
        with patch.object(release, "edition_ready", return_value={"ready": True}), \
             patch.object(release.subprocess, "run"), \
             patch.object(release, "verify_release", side_effect=ValueError("source hash changed")):
            with self.assertRaisesRegex(ValueError, "source hash changed"):
                release.replay(self.original, self.current, self.policy)
        self.assertNotIn(self.monday, release.read(self.current / self.drafts))
        self.assertEqual(release.read(self.archive)["edition_format"], "coverage")

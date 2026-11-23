"""Regression coverage for interrupted and corrupt model downloads."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import download_issue_model as model


class ModelDownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.name = "model.gguf"
        self.target = self.directory / self.name
        self.partial = self.directory / (self.name + ".part")
        self.payload = b"a small model for transfer tests"
        self.digest = hashlib.sha256(self.payload).hexdigest()
        self.offsets = []
        self.enterContext(patch.object(model.time, "sleep"))

    def fetch(self, responses):
        def transfer(command, **kwargs):
            self.assertIn("--http1.1", command)
            self.assertEqual(command[command.index("--continue-at") + 1], "-")
            self.assertEqual(Path(command[command.index("--output") + 1]), self.partial)
            self.offsets.append(self.partial.stat().st_size if self.partial.exists() else 0)
            code, status, chunk = next(responses)
            with self.partial.open("ab") as stream:
                stream.write(chunk)
            return subprocess.CompletedProcess(command, code, stdout=status)

        responses = iter(responses)
        with patch.object(model.subprocess, "run", side_effect=transfer):
            model.fetch_shard(self.directory, self.name, len(self.payload), self.digest,
                              time.monotonic() + 60)

    def test_interrupted_transfer_resumes_and_verified_file_is_reused(self):
        self.fetch([(92, "200", self.payload[:7]), (0, "206", self.payload[7:])])
        self.assertEqual(self.offsets, [0, 7])
        self.assertEqual(self.target.read_bytes(), self.payload)
        self.assertFalse(self.partial.exists())
        self.fetch([])

    def test_same_size_corruption_is_rejected_and_replaced(self):
        self.target.write_bytes(b"?" * len(self.payload))
        self.fetch([(0, "200", b"!" * len(self.payload)), (0, "200", self.payload)])
        self.assertEqual(self.offsets, [0, 0])
        self.assertEqual(self.target.read_bytes(), self.payload)

    def test_unsupported_range_restarts_download(self):
        self.partial.write_bytes(self.payload[:4])
        self.fetch([(33, "200", b""), (0, "200", self.payload)])
        self.assertEqual(self.offsets, [4, 0])
        self.assertEqual(self.target.read_bytes(), self.payload)

    def test_retries_are_bounded_and_never_publish_an_incomplete_file(self):
        with self.assertRaisesRegex(RuntimeError, "download budget"):
            self.fetch([(22, "503", b"")] * model.ATTEMPTS)
        self.assertEqual(len(self.offsets), model.ATTEMPTS)
        self.assertFalse(self.target.exists())

    def test_permanent_http_failure_stops_immediately(self):
        with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
            self.fetch([(22, "404", b"")])
        self.assertEqual(self.offsets, [0])
        self.assertFalse(self.target.exists())

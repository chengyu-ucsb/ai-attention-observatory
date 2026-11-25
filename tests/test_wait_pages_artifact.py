import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from wait_pages_artifact import artifact_visible, wait_for_artifact, artifact_request


class PagesArtifactVisibilityTests(unittest.TestCase):
    def test_runner_token_authenticates_metadata_only(self):
        url="https://api.github.com/repos/example/site/actions/runs/11/artifacts"
        request=artifact_request(url, "test-runner-token")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-runner-token")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, url)
        self.assertIsNone(artifact_request(url).get_header("Authorization"))

    def setUp(self):
        self.payload = {"artifacts": [{"id": 22, "name": "github-pages",
            "expired": False, "size_in_bytes": 100, "workflow_run": {"id": 11}}]}

    def test_immediately_visible_requires_stable_second_read(self):
        waits = []
        wait_for_artifact(lambda: self.payload, 22, 11, sleep=waits.append)
        self.assertEqual(waits, [5])

    def test_delayed_list_retries_only_reads(self):
        replies = iter([{"artifacts": []}, {"artifacts": []}, self.payload,
                        self.payload])
        waits = []
        wait_for_artifact(lambda: next(replies), 22, 11, sleep=waits.append)
        self.assertEqual(waits, [5, 5, 5])

    def test_visibility_must_remain_stable(self):
        replies = iter([self.payload, {"artifacts": []}, self.payload,
                        self.payload])
        waits = []
        wait_for_artifact(lambda: next(replies), 22, 11, sleep=waits.append)
        self.assertEqual(waits, [5, 5, 5])

    def test_requires_exact_run_id_name_and_unexpired_nonempty_artifact(self):
        for key, value in [("id", 23), ("name", "article-art-state"),
                           ("expired", True), ("size_in_bytes", 0),
                           ("workflow_run", {"id": 12})]:
            payload = copy.deepcopy(self.payload)
            payload["artifacts"][0][key] = value
            self.assertFalse(artifact_visible(payload, 22, 11), key)

    def test_exhaustion_is_bounded_and_fails_closed(self):
        calls, waits = [], []
        def fetch():
            calls.append(True)
            return {"artifacts": []}
        with self.assertRaisesRegex(RuntimeError, "deployment not attempted"):
            wait_for_artifact(fetch, 22, 11, sleep=waits.append)
        self.assertEqual(len(calls), 6)
        self.assertEqual(waits, [5] * 5)

    def test_http_errors_are_not_retried(self):
        calls, waits = [], []
        def fetch():
            calls.append(True)
            raise OSError("rate limited")
        with self.assertRaises(OSError):
            wait_for_artifact(fetch, 22, 11, sleep=waits.append)
        self.assertEqual(len(calls), 1)
        self.assertEqual(waits, [])

    def test_invalid_bounds_fail_before_network(self):
        def fetch():
            self.fail("unexpected network")
        for attempts in (0, 7):
            with self.assertRaises(ValueError):
                wait_for_artifact(fetch, 22, 11, attempts=attempts)
        with self.assertRaises(ValueError):
            wait_for_artifact(fetch, 0, 11)


if __name__ == "__main__":
    unittest.main()

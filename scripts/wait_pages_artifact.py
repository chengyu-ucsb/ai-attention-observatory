"""Wait briefly for a successfully uploaded Pages artifact to become list-visible.

Public metadata reads only: no token, upload, deletion or deployment retries.
"""
import argparse
import json
import re
import time
import urllib.request


def artifact_visible(payload, artifact_id, run_id):
    return any(
        row.get("id") == artifact_id
        and row.get("name") == "github-pages"
        and row.get("expired") is False
        and row.get("size_in_bytes", 0) > 0
        and row.get("workflow_run", {}).get("id") == run_id
        for row in payload.get("artifacts", [])
    )


def wait_for_artifact(fetch, artifact_id, run_id, *, attempts=6, sleep=time.sleep):
    if not 1 <= attempts <= 6 or artifact_id <= 0 or run_id <= 0:
        raise ValueError("invalid artifact visibility bounds")
    for attempt in range(attempts):
        # HTTP errors (including quotas) fail immediately, rather than retrying
        # denied requests. Only a successful but not-yet-visible list is retried.
        if artifact_visible(fetch(), artifact_id, run_id):
            return
        if attempt + 1 < attempts:
            sleep(5)
    raise RuntimeError("Uploaded Pages artifact is not list-visible; deployment not attempted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--artifact-id", required=True, type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("invalid repository")
    url = (f"https://api.github.com/repos/{args.repository}/actions/runs/"
           f"{args.run_id}/artifacts?per_page=100")
    def fetch():
        request = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "observatory-pages-visibility",
        })
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    wait_for_artifact(fetch, args.artifact_id, args.run_id)
    print("Uploaded Pages artifact is visible for this run.")


if __name__ == "__main__":
    main()

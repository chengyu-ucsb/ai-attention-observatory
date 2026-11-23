"""Reapply a validated draft after another workflow advances main.

Runs in a fresh checkout of main, retaining the original checkout for the
recovery artifact. Only the target week's editorial entry and audit travel
between checkouts. Regenerate the shelf and all publication files on main.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from compose_issue import verify_release
from edition_progress import policy_signature
from edition_schedule import canonical_edition_date
from preparation_pipeline import edition_ready


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def replay(original, root, checked_policy):
    weekly = read(original / "data/editorial-weekly.json")
    monday = canonical_edition_date(original, weekly["run"]["date"])
    archive_path = root / "data/approved-issues" / (monday + ".json")
    if archive_path.exists():
        archive = read(archive_path)
        if archive.get("status") == "published" and archive.get("edition_format", "full") != "coverage":
            print(f"A synthesis for {monday} is already saved on main.")
            return False
    if checked_policy != policy_signature():
        raise ValueError("Edition review policy changed during composition")
    receipt = edition_ready(root, reconcile_legacy=True, allow_partial=True)
    if not receipt["ready"]:
        raise ValueError("Final reading receipt changed: " + receipt["status"])

    draft_path = Path("data/issue-editorial.json")
    candidate = read(original / draft_path)[monday]
    drafts = read(root / draft_path)
    existing = drafts.get(monday)
    if existing and existing != candidate and existing.get("edition_format") != "coverage":
        raise ValueError("A different editorial draft already exists for " + monday)

    def run(script):
        subprocess.run([sys.executable, "scripts/" + script + ".py"], cwd=root, check=True)

    run("build_public")
    audit_path = Path("data/edition-audits") / (monday + ".json")
    write(root / audit_path, read(original / audit_path))
    # Recompute the whole source hash and date window from the latest shelf.
    verify_release(root)
    drafts[monday] = candidate
    write(root / draft_path, drafts)
    run("build_issue")
    run("build_newsletter")
    run("pipeline_status")
    rebuilt = read(archive_path)
    if (rebuilt.get("status") != "published" or rebuilt.get("edition_format") == "coverage"
            or rebuilt["headline"] != candidate["headline"]):
        raise ValueError("Rebuilt archive does not contain the checked synthesis")
    subprocess.run(["node", "tests/validate_weekly_issue.cjs"], cwd=root, check=True)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("policy")
    args = parser.parse_args()
    replay(args.original.resolve(), Path.cwd(), args.policy)

"""Plan missed-launch recovery without fetching sources or dispatching jobs.

Only a completely absent current-week discovery attempt can be recovered.
Failed/active attempts require inspection, not an automatic search replay.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from collection_window import window_metadata

UTC = dt.timezone.utc
PRIMARY_LOCAL = dt.time(0, 7, tzinfo=ZoneInfo('America/New_York'))
GRACE = dt.timedelta(hours=3)
WORKFLOW_PATH = ".github/workflows/refresh.yml"


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing Actions timestamp")
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Actions timestamps must include timezone")
    return result.astimezone(UTC)


def snapshot_state(weekly, now):
    if not isinstance(weekly, dict) or not isinstance(weekly.get("run"), dict):
        raise ValueError("Missing weekly snapshot metadata")
    run = weekly["run"]
    if run.get("mode") != "weekly":
        raise ValueError("Recovery requires a weekly snapshot, not a backfill or other mode")
    date = dt.date.fromisoformat(run["date"])
    if run["date"] != date.isoformat() or date > now.date():
        raise ValueError("Invalid or future discovery date")
    expected = window_metadata(date)
    actual = run.get("publication_window")
    if (type(actual) is not dict or actual.keys() != expected.keys()
            or any(type(actual[key]) is not type(value) or actual[key] != value
                   for key, value in expected.items())):
        raise ValueError("Snapshot must explicitly declare its exact publication window")
    monday = now.date() - dt.timedelta(days=now.weekday())
    return "current" if date >= monday else "stale"


def runs_from_pages(pages, workflow_id):
    if not isinstance(pages, list) or not pages:
        raise ValueError("Missing paginated Actions history")
    total, rows, seen = None, [], set()
    for page in pages:
        if not isinstance(page, dict) or type(page.get("total_count")) is not int:
            raise ValueError("Invalid Actions history page")
        if total is None:
            total = page["total_count"]
        if total < 0 or page["total_count"] != total or not isinstance(page.get("workflow_runs"), list):
            raise ValueError("Actions history changed during pagination; inspect again")
        for row in page["workflow_runs"]:
            if (not isinstance(row, dict) or type(row.get("id")) is not int
                    or row["id"] <= 0 or row["id"] in seen or row.get("workflow_id") != workflow_id):
                raise ValueError("Actions history has missing, duplicate or wrong-workflow rows")
            seen.add(row["id"])
            rows.append(row)
    if total != len(rows):
        raise ValueError("Incomplete Actions history; refusing recovery")
    return rows


def plan(weekly, workflow, pages, *, now=None, current_run_id=None):
    now = now or dt.datetime.now(UTC)
    if not isinstance(now, dt.datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Recovery planning requires an aware datetime")
    now = now.astimezone(UTC)
    monday = now.date() - dt.timedelta(days=now.weekday())
    start = dt.datetime.combine(monday, dt.time(tzinfo=UTC))
    due = (dt.datetime.combine(monday, PRIMARY_LOCAL) + GRACE).astimezone(UTC)
    result = {"dispatch": False, "status": "held", "expected_publication_window": window_metadata(now),
              "recovery_not_before": due.isoformat()}

    def held(status, reason):
        return dict(result, status=status, reason=reason)

    try:
        state = snapshot_state(weekly, now)
    except (TypeError, ValueError, KeyError):
        return held("invalid_snapshot", "Inspect the missing, malformed or future snapshot; do not rewrite its dates.")
    if state == "current":
        return held("current", "The current strict weekly window already exists.")
    if now < due:
        return held("not_due", "Wait until the primary weekly schedule and grace period have elapsed.")
    if (not isinstance(workflow, dict) or workflow.get("path") != WORKFLOW_PATH
            or type(workflow.get("id")) is not int or workflow["id"] <= 0):
        return held("invalid_workflow", "Workflow identity could not be verified.")
    if workflow.get("state") != "active":
        return held("workflow_inactive", "Inspect workflow settings; the watchdog must not enable a disabled workflow.")
    try:
        rows = runs_from_pages(pages, workflow["id"])
        if current_run_id is not None:
            own = next((r for r in rows if r["id"] == current_run_id), None)
            if (type(current_run_id) is not int or not own or own.get("event") != "workflow_dispatch"
                    or own.get("head_branch") != "main" or type(own.get("run_attempt")) is not int
                    or own["run_attempt"] != 1):
                raise ValueError("Recovery run identity is missing or unexpected")
        for row in rows:
            dates = [timestamp(row[key]) for key in ("created_at", "run_started_at", "updated_at")]
            if any(value > now + dt.timedelta(minutes=1) for value in dates):
                raise ValueError("Future Actions timestamps")
            if row["id"] == current_run_id:
                continue
            if row.get("status") != "completed":
                return held("existing_run", "A discovery run is queued, active or in an unrecognized state.")
            if max(dates) >= start:
                return held("already_attempted", "Discovery was already attempted this week. Inspect its logs and saved artifacts; do not replay it.")
    except (TypeError, ValueError, KeyError):
        return held("invalid_run_history", "Actions history is incomplete or inconsistent; no recovery is safe yet.")
    return dict(result, dispatch=True, status="missed_launch",
                reason="No current-week discovery attempt exists and the strict weekly snapshot is stale.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weekly", type=Path, default=Path("data/weekly.json"))
    parser.add_argument("--workflow", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--current-run-id", type=int)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = plan(read(args.weekly), read(args.workflow), read(args.runs), current_run_id=args.current_run_id)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write("dispatch=" + str(result["dispatch"]).lower() + "\n")
            out.write("status=" + result["status"] + "\n")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write("Weekly discovery recovery: " + result["status"] + "\n\n" + result["reason"] + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

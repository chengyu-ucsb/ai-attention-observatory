"""Offline missed-launch plans: no provider calls, dispatches or replay."""
import copy
import datetime as dt
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import discovery_watchdog as watchdog
from collection_window import window_metadata

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 9, 16, 41, tzinfo=UTC)
WORKFLOW = {"id": 388262803, "path": ".github/workflows/refresh.yml", "state": "active"}


def snapshot(date="2026-11-07"):
    return {"run": {"date": date, "mode": "weekly", "publication_window": window_metadata(date)}, "items": []}


def run(id=1, when="2026-11-08T12:00:00Z", **kwargs):
    return dict(id=id, workflow_id=WORKFLOW["id"], created_at=when, run_started_at=when,
                updated_at=when, status="completed", conclusion="success", event="schedule",
                head_branch="main", run_attempt=1, **kwargs)


def pages(*rows):
    return [{"total_count": len(rows), "workflow_runs": list(rows)}]


def plan(rows=None, weekly=None, workflow=None, **kwargs):
    return watchdog.plan(snapshot() if weekly is None else weekly,
                         WORKFLOW if workflow is None else workflow,
                         pages() if rows is None else rows, now=kwargs.pop("now", NOW), **kwargs)


class DiscoveryWatchdogTests(unittest.TestCase):
    def test_absent_overdue_launch_has_narrow_dispatch_plan(self):
        result = plan(pages(run()))
        self.assertTrue(result["dispatch"])
        self.assertEqual(result["status"], "missed_launch")
        self.assertEqual(result["recovery_not_before"], "2026-11-09T08:07:00+00:00")
        self.assertEqual(result["expected_publication_window"]["from"], "2026-11-02")
        self.assertEqual(result["expected_publication_window"]["to"], "2026-11-08")

    def test_primary_schedule_plus_grace_and_exact_boundary(self):
        for clock in (NOW.replace(hour=0, minute=0), NOW.replace(hour=5, minute=7),
                      NOW.replace(hour=8, minute=6, second=59)):
            self.assertEqual(plan(now=clock)["status"], "not_due")
        self.assertTrue(plan(now=NOW.replace(hour=8, minute=7))["dispatch"])

    def test_recovery_grace_tracks_eastern_daylight_saving_time(self):
        summer=plan(weekly=snapshot('2026-07-05'),now=dt.datetime(2026,7,6,8,tzinfo=UTC))
        self.assertEqual(summer['recovery_not_before'],'2026-07-06T07:07:00+00:00')

    def test_current_week_never_collects_again(self):
        for date in ("2026-11-09", "2026-11-10"):
            result = plan(weekly=snapshot(date), now=NOW+dt.timedelta(days=1))
            self.assertEqual(result["status"], "current")
            self.assertFalse(result["dispatch"])

    def test_active_or_unknown_run_from_any_week_blocks(self):
        for state in ("queued", "in_progress", "waiting", "requested", "pending", "unknown", None):
            row = run(); row["status"] = state
            self.assertFalse(plan(pages(row))["dispatch"])
            self.assertEqual(plan(pages(row))["status"], "existing_run")

    def test_any_current_week_attempt_blocks_regardless_of_result(self):
        for conclusion in ("success", "failure", "cancelled", "timed_out", "skipped", "action_required", None):
            row = run(when="2026-11-09T12:25:00Z"); row["conclusion"] = conclusion
            self.assertEqual(plan(pages(row))["status"], "already_attempted")

    def test_dispatch_from_another_ref_also_counts(self):
        row = run(when="2026-11-09T12:25:00Z")
        row.update(event="workflow_dispatch", head_branch="feature/other")
        self.assertEqual(plan(pages(row))["status"], "already_attempted")

    def test_previous_week_run_restarted_or_finished_now_also_counts(self):
        for field in ("run_started_at", "updated_at"):
            row = run(); row[field] = "2026-11-09T12:25:00Z"
            self.assertEqual(plan(pages(row))["status"], "already_attempted")

    def test_locked_recovery_excludes_only_verified_own_dispatch(self):
        own = run(id=9, when="2026-11-09T16:40:00Z")
        own.update(event="workflow_dispatch", status="in_progress")
        self.assertTrue(plan(pages(own), current_run_id=9)["dispatch"])
        self.assertFalse(plan(pages(own), current_run_id=8)["dispatch"])
        for change in ({"head_branch": "feature/other"}, {"event": "schedule"}):
            altered = dict(own, **change)
            self.assertEqual(plan(pages(altered), current_run_id=9)["status"], "invalid_run_history")

    def test_late_scheduled_success_failure_or_queued_run_wins_race(self):
        own = run(id=9, when="2026-11-09T16:40:00Z")
        own.update(event="workflow_dispatch", status="in_progress")
        for status, conclusion in (("completed", "failure"), ("completed", "success"), ("queued", None)):
            late = run(id=10, when="2026-11-09T16:39:00Z")
            late.update(status=status, conclusion=conclusion)
            result = plan(pages(own, late), current_run_id=9)
            self.assertFalse(result["dispatch"])
        self.assertFalse(plan(pages(own), weekly=snapshot("2026-11-09"), current_run_id=9)["dispatch"])

    def test_rerunning_a_recovery_is_not_a_new_missing_launch(self):
        own = run(id=9, when="2026-11-09T16:40:00Z")
        own.update(event="workflow_dispatch", status="in_progress")
        for attempt in (2, 3, 0, None, True, "1"):
            row = dict(own, run_attempt=attempt)
            self.assertEqual(plan(pages(row), current_run_id=9)["status"], "invalid_run_history")

    def test_invalid_snapshot_or_window_never_repaired_by_planner(self):
        malformed = [{}, {"run": {}}, {"run": {"date": "2026-11"}}, snapshot("2026-11-10")]
        for value in (1, 1.0, "true", None):
            row = snapshot(); row["run"]["publication_window"]["inclusive"] = value
            malformed.append(row)
        row = snapshot(); del row["run"]["publication_window"]
        malformed.append(row)
        row = snapshot(); row["run"]["publication_window"] = window_metadata(NOW)
        malformed.append(row)
        row = snapshot(); row["run"]["date"] = "20261107"
        malformed.append(row)
        row = snapshot(); row["run"]["mode"] = "backfill"
        malformed.append(row)
        for weekly in malformed:
            self.assertEqual(plan(weekly=weekly)["status"], "invalid_snapshot")

    def test_disabled_unknown_or_wrong_workflow_is_not_enabled(self):
        for state in ("disabled_manually", "disabled_inactivity", "deleted", "unknown", None):
            self.assertFalse(plan(workflow=dict(WORKFLOW, state=state))["dispatch"])
        self.assertEqual(plan(workflow=dict(WORKFLOW, path="other.yml"))["status"], "invalid_workflow")

    def test_complete_paginated_history_required(self):
        row = run()
        malformed = [[], {}, [{"total_count": 2, "workflow_runs": [row]}],
                     [{"total_count": 1, "workflow_runs": [row]}, {"total_count": 2, "workflow_runs": []}],
                     [{"total_count": 2, "workflow_runs": [row, row]}],
                     pages(dict(row, workflow_id=999)), pages(dict(row, created_at=None)),
                     pages(dict(row, updated_at="2026-11-09T20:00:00Z"))]
        for payload in malformed:
            self.assertEqual(plan(payload)["status"], "invalid_run_history")
        complete = [{"total_count": 2, "workflow_runs": [row]},
                    {"total_count": 2, "workflow_runs": [run(id=2)]}]
        self.assertTrue(plan(complete)["dispatch"])

    def test_utc_year_rollover_and_old_valid_snapshot(self):
        local = dt.datetime(2026, 11, 9, 8, 41, tzinfo=dt.timezone(dt.timedelta(hours=-8)))
        self.assertEqual(plan(now=local), plan())
        self.assertTrue(plan(weekly=snapshot("2026-10-26"))["dispatch"])
        next_year = dt.datetime(2027, 1, 4, 16, 41, tzinfo=UTC)
        self.assertTrue(plan(weekly=snapshot("2027-01-03"), now=next_year)["dispatch"])
        with self.assertRaises(ValueError):
            plan(now=NOW.replace(tzinfo=None))

    def test_read_only_plan_preserves_every_input(self):
        inputs = [snapshot(), WORKFLOW, pages(run())]
        before = copy.deepcopy(inputs)
        watchdog.plan(*inputs, now=NOW)
        self.assertEqual(inputs, before)

    def test_workflow_token_scope_pr_isolation_and_dispatch_contract(self):
        refresh = (ROOT / ".github/workflows/refresh.yml").read_text()
        recovery = (ROOT / ".github/workflows/discovery-watchdog.yml").read_text()
        for text in (refresh, recovery):
            self.assertIn("'observatory-discovery-watchdog'" if text == recovery else "group: observatory-index", text)
            self.assertIn("queue: max", text)
            self.assertIn("cancel-in-progress: false", text)
            self.assertIn("gh api --paginate --slurp", text)
        self.assertIn("if: github.event_name == 'pull_request'", recovery)
        verify = recovery[recovery.index("  verify:"):recovery.index("  recover:")]
        self.assertNotIn("actions: write", verify)
        self.assertNotIn("GH_TOKEN", verify)
        self.assertIn("if: github.event_name == 'schedule'", recovery)
        self.assertIn("if: steps.plan.outputs.dispatch == 'true'", recovery)
        self.assertIn("-f ref=main -f 'inputs[mode]=weekly' -f 'inputs[only_if_due]=true'", recovery)
        self.assertNotIn("OPENALEX_API_KEY", recovery)
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.only_if_due", refresh)
        self.assertIn('test "$RECOVERY_MODE" = weekly', refresh)
        self.assertIn('--current-run-id "$GITHUB_RUN_ID"', refresh)
        self.assertIn("if: steps.recovery.outcome == 'skipped' || steps.recovery.outputs.dispatch == 'true'", refresh)
        self.assertIn("if: needs.check_due.outputs.needed == 'true'", refresh)
        self.assertIn("github.event_name != 'workflow_dispatch' || !inputs.only_if_due || github.run_attempt == '1'", refresh)
        first = re.findall(r"^\s+- cron: '([^']+)'", refresh, flags=re.MULTILINE)[0]
        self.assertEqual(first, f"{watchdog.PRIMARY_LOCAL.minute} {watchdog.PRIMARY_LOCAL.hour},2,6,10 * * 1")
        self.assertIn('timezone: America/New_York',refresh)
        self.assertIn('timezone: America/New_York',recovery)


if __name__ == "__main__":
    unittest.main()

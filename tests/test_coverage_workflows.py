"""Production scheduling and no-network PR boundaries for coverage recovery."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CoverageWorkflowTests(unittest.TestCase):
    def test_snapshot_schedule_does_not_run_article_retrieval(self):
        text=(ROOT/'.github/workflows/editorial-feed-snapshots.yml').read_text()
        self.assertIn("cron: '7 2,8,14,20 * * *'",text)
        self.assertIn("if: github.event_name != 'pull_request'",text)
        self.assertIn('scripts/editorial_feed_cache.py --max-requests 24 --time-budget 240',text)
        self.assertNotIn('collect_weekly_sources.py',text)
        self.assertNotIn('comprehensive_readings.py',text)
        self.assertIn('git add data/editorial-feed-cache.json',text)
        self.assertIn('load_cache(path, ed.FEEDS)',text)

    def test_resume_advances_only_one_late_generation_without_live_feed_search(self):
        text=(ROOT/'.github/workflows/resume-weekly-discovery.yml').read_text()
        self.assertIn('preparation_pipeline.py closeout --expected-week "${{ steps.closeout_scope.outputs.week }}" --max-requests 48 --max-feed-requests 0 --time-budget 240',text)
        self.assertNotIn('scripts/update.py',text)
        self.assertIn("ACADEMIC_MAX_PAGES: '1'",text)
        self.assertIn("ACADEMIC_MAX_DATE_LOOKUPS: '12'",text)
        self.assertIn('scripts/discover_editorial.py --cached-only',text)
        self.assertIn('scripts/editorial_metadata.py --max-records 8 --max-requests 24 --time-budget 120',text)
        self.assertIn("all(actual.get(key) == expected[key] for key in ('from', 'to', 'timezone'))",text)
        self.assertNotIn('seed_historical.py',text)
        self.assertNotIn('compose_issue.py',text)
        self.assertLess(text.index('scripts/editorial_metadata.py --'),text.index('scripts/build_weekly.py'))

    def test_resume_controls_are_scoped_to_academic_step_not_validation(self):
        text=(ROOT/'.github/workflows/resume-weekly-discovery.yml').read_text()
        step=text.index('      - name: Advance the one late-index pass or resume its existing cursors')
        following=text.index('      - name: Admit only staged',step)
        block=text[step:following]
        for variable in ('ACADEMIC_MAX_PAGES','ACADEMIC_MAX_DATE_LOOKUPS','ACADEMIC_MAX_INLINE_WAIT_SECONDS','OPENALEX_API_KEY'):
            self.assertIn(variable,block)
            self.assertNotIn(variable,text[:step])
            self.assertNotIn(variable,text[following:])

    def test_completed_resume_routes_to_acquisition_and_publication(self):
        for name in ('publish.yml','weekly-source-acquisition.yml'):
            text=(ROOT/'.github/workflows'/name).read_text()
            self.assertIn('Resume weekly source discovery',text)
            self.assertIn('workflow_run:',text)
            self.assertIn("github.event.workflow_run.event != 'pull_request'",text)
            self.assertIn('github.event.workflow_run.head_repository.full_name == github.repository',text)
            self.assertIn("github.event.workflow_run.head_branch == 'main'",text)

    def test_all_shared_writers_preserve_pending_work(self):
        for name in ('refresh.yml','backfill-fulltext.yml','deepen-readings.yml','weekly-edition.yml','resume-weekly-discovery.yml'):
            text=(ROOT/'.github/workflows'/name).read_text()
            self.assertIn('observatory-edition' if name=='weekly-edition.yml' else 'observatory-index',text)
            if name=='weekly-edition.yml':
                self.assertIn('git diff --quiet "$publication_base" origin/main',text)
                self.assertIn('compose_issue.py --verify-release',text)
            self.assertIn('  queue: max',text)
            self.assertIn('  cancel-in-progress: false',text)

    def test_rejected_upstream_events_have_unique_skip_concurrency(self):
        for name in ('backfill-fulltext.yml','weekly-edition.yml','publish.yml','weekly-source-acquisition.yml'):
            text=(ROOT/'.github/workflows'/name).read_text()
            group=next(line for line in text.splitlines() if line.startswith('  group:'))
            self.assertIn("github.event.workflow_run.conclusion != 'success'",group)
            self.assertIn("github.event.workflow_run.event == 'pull_request'",group)
            self.assertIn('github.run_id',group)
            self.assertIn('skip-',group)

    def test_new_workflows_use_verified_node24_action_releases(self):
        for name in ('resume-weekly-discovery.yml','editorial-feed-snapshots.yml'):
            text=(ROOT/'.github/workflows'/name).read_text()
            self.assertIn('actions/checkout@v7.0.1',text)
            self.assertIn('actions/setup-python@v7.1.0',text)
            self.assertIn('actions/upload-artifact@v7.0.2',text)
            self.assertIn('runs-on: ubuntu-24.04',text)
            self.assertNotIn('actions/checkout@v4',text)
            self.assertNotIn('actions/setup-python@v5',text)


if __name__=='__main__':unittest.main()

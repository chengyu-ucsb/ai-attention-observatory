"""Protect the Monday archive migration against content loss and date drift."""
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import consolidate_editions
from build_issue import validate_issue_citations


class EditionConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'
        self.approved = self.data / 'approved-issues'
        self.approved.mkdir(parents=True)
        revisions = ROOT / 'data/edition-revisions'
        self.originals = {
            day: (revisions / (day + '.json')).read_bytes()
            for day in consolidate_editions.MAPPING
        }
        for day, raw in self.originals.items():
            (self.approved / (day + '.json')).write_bytes(raw)
        self.original_drafts = (revisions / 'issue-editorial-before-consolidation.json').read_bytes()
        (self.data / 'issue-editorial.json').write_bytes(self.original_drafts)
        self.stamp = datetime(2026, 11, 13, 17, 30, tzinfo=timezone.utc)

    def migrate(self):
        return consolidate_editions.migrate(self.root, now=self.stamp)

    def issues(self):
        return {p.stem: json.loads(p.read_text()) for p in self.approved.glob('*.json')}

    def tree_bytes(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_four_monday_editions_replace_five_release_dates(self):
        result = self.migrate()
        issues = self.issues()
        self.assertTrue(result['changed'])
        self.assertEqual(sorted(issues), ['2026-10-19', '2026-10-26', '2026-11-02', '2026-11-09'])
        self.assertEqual([issues[day]['number'] for day in sorted(issues)], ['01', '02', '03', '04'])
        self.assertTrue(all(date.fromisoformat(day).weekday() == 0 for day in issues))
        self.assertTrue(all(issue['edition_date'] == day for day, issue in issues.items()))
        self.assertEqual(set(json.loads((self.data / 'issue-editorial.json').read_text())), set(issues))

    def test_migration_is_byte_idempotent_even_with_a_later_clock(self):
        self.migrate()
        before = self.tree_bytes()
        result = consolidate_editions.migrate(
            self.root, now=datetime(2026, 11, 20, 23, 0, tzinfo=timezone.utc))
        self.assertFalse(result['changed'])
        self.assertEqual(self.tree_bytes(), before)

    def test_original_publications_and_draft_snapshot_are_retained_exactly(self):
        self.migrate()
        revisions = self.data / 'edition-revisions'
        registry = json.loads((self.data / 'edition-lineage.json').read_text())
        for day, raw in self.originals.items():
            with self.subTest(original=day):
                self.assertEqual((revisions / (day + '.json')).read_bytes(), raw)
                self.assertEqual(registry['revisions'][day]['sha256'], sha256(raw).hexdigest())
        self.assertEqual((revisions / 'issue-editorial-before-consolidation.json').read_bytes(),
                         self.original_drafts)

    def test_source_union_is_preserved_while_repeated_collection_is_removed(self):
        old = {day: json.loads(raw) for day, raw in self.originals.items()}
        original_ids = {source['id'] for issue in old.values() for source in issue['sources']}
        repeated = {source['id'] for source in old['2026-11-02']['sources']}
        october = {source['id'] for source in old['2026-10-26']['sources']}
        self.assertEqual(len(repeated), 8)
        self.assertTrue(repeated <= october)
        self.migrate()
        issues = self.issues()
        self.assertEqual({source['id'] for issue in issues.values() for source in issue['sources']}, original_ids)
        self.assertEqual(sum(len(issue['sources']) for issue in issues.values()), 59)
        self.assertEqual(len(issues['2026-10-26']['sources']), 18)
        for issue in issues.values():
            self.assertEqual(issue['source_count'], len(issue['sources']))
            self.assertEqual(len(issue['sources']), len({source['id'] for source in issue['sources']}))

    def test_strict_weekly_sources_are_separate_from_legacy_collections(self):
        self.migrate()
        issues = self.issues()
        for day in ('2026-10-19', '2026-10-26'):
            self.assertEqual(issues[day]['scope_kind'], 'legacy_collection')
            self.assertFalse(issues[day].get('publication_window'))
        for day, start, end in [('2026-11-02', '2026-10-26', '2026-11-01'),
                                ('2026-11-09', '2026-11-02', '2026-11-08')]:
            issue = issues[day]
            self.assertEqual(issue['publication_window']['from'], start)
            self.assertEqual(issue['publication_window']['to'], end)
            self.assertEqual(issue['publication_window']['timezone'], 'UTC')
            self.assertTrue(all(start <= source['published'] <= end for source in issue['sources']))
        self.assertEqual(issues['2026-11-02']['sources'], json.loads(self.originals['2026-11-07'])['sources'])
        self.assertEqual(issues['2026-11-09']['sources'], json.loads(self.originals['2026-11-13'])['sources'])

    def test_merged_supplement_has_real_citations_and_keeps_evidence_limits(self):
        self.migrate()
        issue = self.issues()['2026-10-26']
        validate_issue_citations(issue)
        self.assertEqual(len(issue['supplements']), 1)
        section = issue['supplements'][0]
        sources = {source['id'] for source in issue['sources']}
        self.assertTrue(set(section['source_ids']) <= sources)
        self.assertEqual(set(section['source_ids']), {cite['source_id'] for cite in section['citations']})
        for citation in section['citations']:
            self.assertIn(citation['text'], section['text'])
        self.assertIn('abstract-based', section['text'])
        self.assertIn('without experimental control', section['text'])
        self.assertIn('cross-sectional, self-report', section['text'])
        # The corrected existing analysis is retained, rather than replaced by
        # the old automated draft's stronger causal/performance language.
        self.assertEqual(issue['signals'], json.loads(self.originals['2026-10-26'])['signals'])
        self.assertEqual(issue['tension'], json.loads(self.originals['2026-10-26'])['tension'])

    def test_consolidated_supplement_cannot_bypass_inline_citation_validation(self):
        self.migrate()
        issue = self.issues()['2026-10-26']
        issue['supplements'][0]['citations'].pop()
        with self.assertRaisesRegex(ValueError, 'explicit inline citation'):
            validate_issue_citations(issue)

    def test_monday_labels_do_not_backdate_actual_release_or_replace_feed_ids(self):
        self.migrate()
        issues = self.issues()
        for day, original in [('2026-10-19', '2026-10-18'), ('2026-10-26', '2026-10-26'),
                              ('2026-11-02', '2026-11-07'), ('2026-11-09', '2026-11-13')]:
            self.assertEqual(issues[day]['first_published_date'], original)
            self.assertEqual(issues[day]['feed_id'], consolidate_editions.BASE + original + '.html')
            self.assertEqual(issues[day]['feed_published_at'], original + 'T12:00:00+00:00')
        registry = json.loads((self.data / 'edition-lineage.json').read_text())
        self.assertEqual(registry['aliases'], {'2026-10-18': '2026-10-19',
                                              '2026-11-07': '2026-11-02',
                                              '2026-11-13': '2026-11-09'})
        # November 2 is now a canonical address, so its earlier contents must
        # remain reachable via history rather than a conflicting redirect.
        self.assertNotIn('2026-11-02', registry['aliases'])
        self.assertTrue(any(item['url'] == 'history/2026-11-02.html'
                            for item in issues['2026-11-02']['edition_history']))

    def test_conflicting_dated_revision_is_never_overwritten(self):
        revisions = self.data / 'edition-revisions'
        revisions.mkdir()
        path = revisions / '2026-10-18.json'
        path.write_bytes(b'earlier immutable evidence')
        with self.assertRaisesRegex(ValueError, 'immutable revision'):
            self.migrate()
        self.assertEqual(path.read_bytes(), b'earlier immutable evidence')

    def test_conflicting_editorial_revision_is_never_overwritten(self):
        revisions = self.data / 'edition-revisions'
        revisions.mkdir()
        path = revisions / 'issue-editorial-before-consolidation.json'
        path.write_bytes(b'earlier immutable editorial snapshot')
        with self.assertRaises(ValueError):
            self.migrate()
        self.assertEqual(path.read_bytes(), b'earlier immutable editorial snapshot')


if __name__ == '__main__':
    unittest.main()

"""Offline regression tests for strict weekly nonacademic acquisition."""
import datetime as dt
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import discover_editorial as ed

TODAY = dt.date(2026, 11, 7)
FEED = {"id": "publisher", "name": "Example News", "url": "https://example.org/feed",
        "article_hosts": ["example.org"], "source_type": "journalism", "category": "Technology journalism"}


def item(day="2026-10-28", slug="story", title="How AI changes human attention in classrooms", extra=""):
    date = f"<pubDate>{day}</pubDate>" if day else ""
    return f"""<item><title>{title}</title><link>https://example.org/{slug}</link>{date}
    <description>Researchers examine artificial intelligence and the ways that cognitive offloading changes human attention, classroom learning routines, deliberate thinking and memory.</description>{extra}</item>"""


def rss(items, extra=""):
    return ET.fromstring(f'<rss xmlns:atom="http://www.w3.org/2005/Atom"><channel>{items}{extra}</channel></rss>')


def collect(root, existing=None, feeds=None, searches=None):
    return ed.collect(existing or [], now=TODAY, feeds=feeds or [FEED], searches=searches or [],
                      fetcher=lambda url: root, sleep=lambda _: None)


class EditorialCollectionTests(unittest.TestCase):
    def test_new_same_url_conflicting_dates_cannot_enter_week(self):
        from collection_window import weekly_eligible,previous_week
        for dates in [('2026-10-28','2026-09-01'),('2026-09-01','2026-10-28'),('2026-10-28','2026-10-29')]:
            added,status,quarantine=collect(rss(item(dates[0])+item(dates[1])))
            self.assertFalse(any(weekly_eligible(row,*previous_week(TODAY)) for row in added),dates)
            self.assertEqual(status['accepted'],0)
            self.assertTrue(status['conflicting_existing_records'])
            self.assertTrue(any(x['status']=='conflicting_original_publication_dates' for x in quarantine))

    def test_exact_previous_week_boundary(self):
        rows = "".join(item(day, str(i), f"AI attention and classroom learning case {i}")
                       for i, day in enumerate(["2026-10-25", "2026-10-26", "2026-11-01", "2026-11-02", ""]))
        added, status, quarantine = collect(rss(rows))
        self.assertEqual({x["published"] for x in added}, {"2026-10-26", "2026-11-01"})
        self.assertEqual(status["publication_window"]["from"], "2026-10-26")
        self.assertEqual(status["publication_window"]["to"], "2026-11-01")
        self.assertEqual(status["sources"][0]["rejected"]["outside_previous_week"], 2)
        self.assertEqual(quarantine[0]["status"], "original_publication_date_missing")

    def test_updated_does_not_become_original_publication(self):
        root = ET.fromstring('''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>AI and critical thinking in classroom learning</title><link href="https://example.org/a"/>
        <updated>2026-10-30T12:00:00Z</updated><summary>AI changes learning and human attention.</summary>
        </entry></feed>''')
        parsed = ed.parse_feed(root)[0]
        self.assertEqual(parsed["date"], "")
        self.assertEqual(parsed["updated"], "2026-10-30")
        added, _, quarantine = collect(root)
        self.assertEqual(added, [])
        self.assertEqual(len(quarantine), 1)

    def test_updated_old_article_excluded(self):
        root = ET.fromstring('''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>AI and critical thinking in classroom learning</title><link href="https://example.org/a"/>
        <published>2026-09-01T12:00:00Z</published><updated>2026-10-30T12:00:00Z</updated>
        <summary>AI changes learning and human attention.</summary></entry></feed>''')
        self.assertEqual(collect(root)[0], [])

    def test_utc_midnight_boundary(self):
        self.assertEqual(ed.normalize_date("2026-11-01T23:30:00-05:00"), "2026-11-02")
        self.assertEqual(ed.normalize_date("Sun, 25 Oct 2026 23:30:00 -0500"), "2026-10-26")

    def test_invalid_partial_dates_not_invented(self):
        for date in ["2026", "2026-10", "2026-02-30", "2026-10-28-invalid", "yesterday"]:
            self.assertEqual(ed.normalize_date(date), "")

    def test_no_silent_item_or_total_caps(self):
        root = rss("".join(item(slug=f"a{i}", title=f"AI and classroom attention findings number {i}") for i in range(105)))
        added, status, _ = collect(root)
        self.assertEqual(len(added), 105)
        self.assertEqual(status["sources"][0]["returned"], 105)

    def test_duplicate_tracking_urls(self):
        root = rss(item(slug="story?utm_source=mail&amp;fbclid=123"))
        old = {"title": "Earlier headline", "url": "https://www.example.org/story/", "venue": "Example News", "published": "2026-10-28"}
        self.assertEqual(collect(root, [old])[0], [])

    def test_existing_direct_feed_date_provenance_refreshed(self):
        old = {"title": "Earlier headline", "url": "https://example.org/story", "venue": "Example News", "published": "2026-10-28"}
        added, status, _ = collect(rss(item()), [old])
        self.assertEqual(added, [])
        self.assertEqual(status["verified_existing_records"][0]["publication_date_provenance"]["basis"], "publisher_rss_pubDate")

    def test_conflicting_archive_date_not_silently_rewritten(self):
        old = {"title": "Earlier headline", "url": "https://example.org/story", "venue": "Example News", "published": "2026-09-01"}
        added, status, quarantine = collect(rss(item()), [old])
        self.assertEqual(added, [])
        self.assertEqual(status["verified_existing_records"], [])
        self.assertEqual(quarantine[0]["status"], "conflicting_original_publication_dates")
        self.assertEqual(old["published"], "2026-09-01")

    def test_conflict_invalidates_previously_trusted_in_week_record(self):
        old = {"title": "Earlier headline", "url": "https://example.org/story",
               "venue": "Example News", "published": "2026-10-28", "kind": "nonacademic",
               "source": "Publisher RSS / Google News RSS",
               "publication_date_provenance": {"basis": "publisher_rss_pubDate", "date": "2026-10-28"},
               "reading": {"overview": "Preserve the previously acquired reading."}}
        start, end = ed.previous_week(TODAY)
        self.assertTrue(ed.weekly_eligible(old, start, end))
        # The fresh publisher date is outside the target window, but contradicts
        # the trusted archive date; it must not disappear at an early date gate.
        added, status, quarantine = collect(rss(item("2026-09-01")), [old])
        self.assertEqual(added, [])
        ed.apply_discovery_evidence([old], status)
        self.assertEqual(old["publication_date_provenance"]["status"], "unresolved")
        self.assertEqual({x["date"] for x in old["publication_date_provenance"]["evidence"]},
                         {"2026-09-01", "2026-10-28"})
        self.assertFalse(ed.weekly_eligible(old, start, end))
        self.assertEqual(old["published"], "2026-10-28")
        self.assertEqual(old["reading"]["overview"], "Preserve the previously acquired reading.")
        # A later matching feed is not an adjudication of contradictory dates.
        _, matching_status, _ = collect(rss(item()), [old])
        ed.apply_discovery_evidence([old], matching_status)
        self.assertEqual(old["publication_date_provenance"]["status"], "unresolved")
        self.assertFalse(ed.weekly_eligible(old, start, end))

    def test_conflict_wins_over_matching_feed_same_run(self):
        old = {"title": "Earlier headline", "url": "https://example.org/story",
               "venue": "Example News", "published": "2026-10-28", "kind": "nonacademic",
               "publication_date_provenance": {"basis": "publisher_rss_pubDate", "date": "2026-10-28"}}
        _, status, _ = collect(rss(item("2026-10-28") + item("2026-10-29")), [old])
        ed.apply_discovery_evidence([old], status)
        self.assertEqual(old["publication_date_provenance"]["status"], "unresolved")

    def test_new_same_url_conflicts_are_quarantined_regardless_of_date_order(self):
        for days in [('2026-10-28', '2026-09-01'), ('2026-09-01', '2026-10-28'),
                     ('2026-10-28', '2026-10-29'), ('2026-10-29', '2026-10-28')]:
            with self.subTest(days=days):
                added, status, quarantine = collect(rss(''.join(item(day) for day in days)))
                ed.apply_discovery_evidence(added, status)
                self.assertEqual(len(status['conflicting_existing_records']), 1)
                self.assertEqual(status['accepted'], 0)
                self.assertEqual(status['source_type_counts'], {})
                self.assertTrue(any(x['status'] == 'conflicting_original_publication_dates' for x in quarantine))
                self.assertTrue(all(not ed.weekly_eligible(x, *ed.previous_week(TODAY)) for x in added))
                self.assertTrue(all(x['publication_date_provenance']['status'] == 'unresolved' for x in added))

    def test_new_url_conflicts_across_pages_remain_quarantined_after_matching_repeat(self):
        pages = {FEED['url']: rss(item('2026-10-28'), '<atom:link rel="next" href="?page=2"/>'),
                 FEED['url'] + '?page=2': rss(item('2026-09-01') + item('2026-10-28'))}
        added, status, quarantine = ed.collect([], now=TODAY, feeds=[FEED], searches=[],
                                               fetcher=pages.__getitem__, sleep=lambda _: None)
        ed.apply_discovery_evidence(added, status)
        self.assertEqual(status['sources'][0]['pages'], 2)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]['publication_date_provenance']['status'], 'unresolved')
        self.assertFalse(ed.weekly_eligible(added[0], *ed.previous_week(TODAY)))

    def test_known_url_date_conflict_checked_even_if_topic_filter_changes(self):
        old = {"title": "Earlier headline", "url": "https://example.org/story",
               "published": "2026-10-28", "kind": "nonacademic",
               "publication_date_provenance": {"basis": "publisher_rss_pubDate", "date": "2026-10-28"}}
        root = rss('<item><title>Unrelated renamed headline</title><link>https://example.org/story</link>'
                   '<pubDate>2026-09-01</pubDate><description>Updated topic.</description></item>')
        _, status, _ = collect(root, [old])
        ed.apply_discovery_evidence([old], status)
        self.assertEqual(old["publication_date_provenance"]["status"], "unresolved")

    def test_identity_query_parameters_preserved(self):
        self.assertNotEqual(ed.url_key("https://example.org/?p=1"), ed.url_key("https://example.org/?p=2"))
        self.assertEqual(ed.url_key("https://www.example.org/story/?p=1&utm_campaign=x#part"), "example.org/story?p=1")

    def test_different_publishers_not_deduplicated_by_title(self):
        old = {"title": "How AI changes human attention in classrooms", "url": "https://other.org/story", "venue": "Other News", "published": "2026-10-28"}
        self.assertEqual(len(collect(rss(item()), [old])[0]), 1)

    def test_titles_are_not_truncated_for_deduplication(self):
        prefix = "How AI changes human attention in classrooms and what teachers can do to sustain memory, student agency and learning habits "
        root = rss(item(slug="one", title=prefix + "in primary schools") + item(slug="two", title=prefix + "in universities"))
        self.assertEqual(len(collect(root)[0]), 2)

    def test_same_publisher_exact_title_and_date_deduplicates(self):
        self.assertEqual(len(collect(rss(item(slug="one") + item(slug="two")))[0]), 1)

    def test_source_type_separate_from_topic_and_evidence(self):
        added, _, _ = collect(rss(item(extra="<category>Opinion</category>")))
        record = added[0]
        self.assertEqual(record["source_type"], "opinion")
        self.assertEqual(record["source_type_basis"], "publisher_item_category")
        self.assertEqual(record["format"], "Opinion & analysis")
        self.assertEqual(record["reading"]["level"], "source_preview")
        self.assertEqual(record["reading"]["findings"], "")
        self.assertFalse(record["publication_date_provenance"]["independently_verified"])
        self.assertEqual(record["publication_date_provenance"]["basis"], "publisher_rss_pubDate")

    def test_feed_default_provisional_not_peer_review(self):
        added, status, _ = collect(rss(item()))
        self.assertEqual(added[0]["source_type_basis"], "provisional_feed_default")
        self.assertEqual(status["full_articles_retrieved"], 0)

    def test_rolling_feed_shortfall_visible(self):
        _, status, _ = collect(rss(item("2026-11-05")))
        self.assertEqual(status["status"], "partial")
        self.assertIn("rolling_feed_does_not_reach_window_start", status["sources"][0]["warnings"])

    def test_follow_only_advertised_same_host_next(self):
        pages = {FEED["url"]: rss(item("2026-11-05"), '<atom:link rel="next" href="https://example.org/feed?page=2"/>'),
                 "https://example.org/feed?page=2": rss(item("2026-10-26"))}
        added, status, _ = ed.collect([], now=TODAY, feeds=[FEED], searches=[], fetcher=pages.__getitem__, sleep=lambda _: None)
        self.assertEqual(len(added), 1)
        self.assertEqual(status["sources"][0]["pages"], 2)
        self.assertEqual(status["status"], "completed_configured_sources")

    def test_untrusted_pagination_rejected(self):
        root = rss(item(), '<atom:link rel="next" href="https://other.org/feed"/>')
        _, status, _ = collect(root)
        self.assertEqual(status["sources"][0]["status"], "partial")
        self.assertEqual(status["sources"][0]["error"], "feed_pagination_requires_review")

    def test_pagination_cap_reported_not_silent(self):
        def endless(url):
            n = int(url.rsplit("=", 1)[-1]) if "=" in url else 0
            return rss(item(slug=f"story{n}", title=f"AI and attention in classroom number {n}"), f'<atom:link rel="next" href="https://example.org/feed?page={n+1}"/>')
        _, status, _ = ed.collect([], now=TODAY, feeds=[FEED], searches=[], fetcher=endless, sleep=lambda _: None)
        self.assertIn("pagination_page_limit_reached", status["sources"][0]["warnings"])
        self.assertEqual(status["sources"][0]["pages"], ed.MAX_FEED_PAGES)

    def test_unapproved_article_host_quarantined(self):
        root = rss(item().replace("https://example.org/story", "https://example.org.evil.test/story"))
        added, _, quarantine = collect(root)
        self.assertEqual(added, [])
        self.assertEqual(quarantine[0]["status"], "publisher_url_unverified")

    def test_google_news_is_unverified_lead_not_article(self):
        root = rss(item(extra="<source>Tech Policy Press</source>").replace("https://example.org/story", "https://news.google.com/rss/articles/opaque"))
        queries = []
        def fetch(url):
            queries.append(url)
            return root
        added, status, quarantine = ed.collect([], now=TODAY, feeds=[], searches=[('"AI" "attention"', "AI & cognition")], fetcher=fetch, sleep=lambda _: None)
        self.assertEqual(added, [])
        self.assertEqual(quarantine[0]["reported_date_basis"], "aggregator_pubDate_not_verified_original")
        self.assertFalse(quarantine[0]["eligible_for_weekly"])
        self.assertIn("after%3A2026-10-25", queries[0])
        self.assertIn("before%3A2026-11-02", queries[0])
        self.assertNotIn("when%3A45d", queries[0])

    def test_one_source_failure_does_not_discard_others(self):
        bad = dict(FEED, id="bad", name="Unavailable", url="https://example.org/missing")
        def fetch(url):
            if url.endswith("missing"):
                raise TimeoutError("timed out")
            return rss(item("2026-10-26"))
        added, status, _ = ed.collect([], now=TODAY, feeds=[bad, FEED], searches=[], fetcher=fetch, sleep=lambda _: None)
        self.assertEqual(len(added), 1)
        self.assertEqual(status["status"], "partial")
        self.assertEqual(status["sources"][0]["error_type"], "TimeoutError")

    def test_generic_policy_rhetoric_is_not_cognition_evidence(self):
        for title, description in [
            ("Rewriting Copyright Law for Generative AI", "We think copyright should support AI creators."),
            ("Government AI procurement plan announced", "The agency has an AI deployment workflow."),
            ("New AI machine learning benchmark unveiled", "Deep learning improves machine learning model scores.")]:
            self.assertFalse(ed.eligible({"title": title, "description": description}))

    def test_rate_limit_stops_same_provider_not_other_sources(self):
        calls = []
        first = dict(FEED, url="https://example.org/feed")
        second = dict(FEED, id="second", url="https://example.org/second")
        def fetch(url):
            calls.append(url)
            raise ed.urllib.error.HTTPError(url, 429, "rate limited", {"Retry-After": "3600"}, None)
        _, status, _ = ed.collect([], now=TODAY, feeds=[first, second], searches=[], fetcher=fetch, sleep=lambda _: None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(status["sources"][0]["retry_after"], "3600")
        self.assertEqual(status["sources"][1]["status"], "deferred")
        self.assertEqual(status["status"], "partial")

    def test_google_provider_outage_does_not_repeat_requests(self):
        calls = []
        def fetch(url):
            calls.append(url)
            raise TimeoutError()
        searches = [("AI attention", "AI & cognition"), ("AI thinking", "AI & cognition")]
        _, status, _ = ed.collect([], now=TODAY, feeds=[], searches=searches, fetcher=fetch, sleep=lambda _: None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(status["sources"][1]["status"], "deferred")

    def test_config_spans_requested_source_types(self):
        self.assertEqual({x["source_type"] for x in ed.FEEDS}, {"journalism", "opinion", "policy", "analysis"})
        self.assertGreaterEqual(len(ed.FEEDS), 10)
        self.assertEqual(len({x["id"] for x in ed.FEEDS}), len(ed.FEEDS))


if __name__ == "__main__":
    unittest.main()

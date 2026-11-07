"""Offline publisher metadata verification; never performs discovery or HTTP."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_metadata as metadata
from collection_window import previous_week, weekly_eligible

NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
TITLE = "How artificial intelligence changes human attention"
URL = "https://www.eff.org/article"
SECRET = "SOURCE_BODY_SENTINEL_DO_NOT_PERSIST"


def record(**values):
    return {"kind": "nonacademic", "url": URL, "title": TITLE, "venue": "Electronic Frontier Foundation",
            "published": "2026-10-28", "source_type": "policy", "source_type_basis": "provisional_feed_default",
            "publication_date_provenance": {"basis": "publisher_rss_pubDate", "date": "2026-10-28", "source_url": "https://www.eff.org/feed"},
            "reading": {"overview": "Preserve an already reviewed note."}, **values}


def page(date="2026-10-28T12:00:00Z", *, title=TITLE, canonical=URL, section="Analysis", extra="", **node_updates):
    node = {"@type": "NewsArticle", "headline": title, "url": canonical, "articleSection": section,
            "datePublished": date, **node_updates}
    return ('<html><head><meta property="og:title" content="' + title + '">'
            '<link rel="canonical" href="' + canonical + '">' + extra +
            '<script type="application/ld+json">' + json.dumps(node) + '</script></head><body>' + SECRET + '</body></html>')


def verify(html=None, **values):
    return metadata.verify_record(record(**values), html or page(), checked_at=NOW)


def process(rows=None, state=None, fetcher=None, **kwargs):
    return metadata.process(rows if rows is not None else [record()], state, now=NOW,
                            fetcher=fetcher or (lambda url: (page(canonical=url), url)), **kwargs)


class ParseAndVerifyTests(unittest.TestCase):
    def test_redirect_cannot_swap_meaningful_article_query_identity(self):
        original=record(url=URL+'?article=123')
        target=URL+'?article=456'
        result=metadata.verify_record(original,page(canonical=target),url=target,checked_at=NOW)
        self.assertEqual(result['editorial_metadata']['status'],'canonical_identity_mismatch')
        self.assertFalse(result.get('publication_date_provenance',{}).get('independently_verified',False))

    def test_original_jsonld_date_verified_without_source_body(self):
        original = record()
        output = metadata.verify_record(original, page(), checked_at=NOW)
        self.assertEqual(output["published"], "2026-10-28")
        self.assertEqual(output["publication_date_provenance"]["basis"], "publisher_datePublished")
        self.assertTrue(output["publication_date_provenance"]["independently_verified"])
        self.assertEqual(output["source_type"], "analysis")
        self.assertEqual(output["editorial_metadata"]["source_type_status"], "verified")
        self.assertEqual(original, record())
        self.assertEqual(output["reading"], original["reading"])
        self.assertNotIn(SECRET, json.dumps(output))
        self.assertNotIn(SECRET, json.dumps(metadata.parse_metadata(page(), URL)))
        self.assertTrue(weekly_eligible(output, *previous_week(NOW)))

    def test_meta_original_dates_and_itemprop(self):
        for field in metadata.DATE_META:
            html = '<meta property="og:title" content="' + TITLE + '"><meta itemprop="' + field + '" content="2026-10-28">'
            result = verify(html)
            self.assertEqual(result["editorial_metadata"]["date_status"], "verified", field)
            self.assertEqual(result["publication_date_provenance"]["basis"], "publisher_meta_published_time")

    def test_modification_dates_never_original(self):
        html = '<meta property="og:title" content="' + TITLE + '"><meta property="article:modified_time" content="2026-10-28">'
        html += '<script type="application/ld+json">' + json.dumps({"@type": "Article", "headline": TITLE, "dateModified": "2026-10-28"}) + '</script>'
        result = verify(html, published="", publication_date_provenance={"status": "unresolved"})
        self.assertEqual(result["published"], "")
        self.assertEqual(result["editorial_metadata"]["date_status"], "unresolved")
        self.assertFalse(weekly_eligible(result, *previous_week(NOW)))

    def test_no_date_does_not_erase_trusted_feed_date(self):
        result = verify('<meta property="og:title" content="' + TITLE + '">')
        self.assertEqual(result["publication_date_provenance"], record()["publication_date_provenance"])
        self.assertEqual(result["editorial_metadata"]["date_status"], "publisher_feed_only")
        self.assertTrue(weekly_eligible(result, *previous_week(NOW)))

    def test_missing_date_can_be_established_from_matching_publisher(self):
        result = verify(published="", publication_date_provenance={"status": "unresolved"})
        self.assertEqual(result["published"], "2026-10-28")
        self.assertTrue(weekly_eligible(result, *previous_week(NOW)))

    def test_original_conflicts_in_either_direction_never_clear(self):
        for original, incoming in [("2026-10-28", "2026-09-01"), ("2026-09-01", "2026-10-28"), ("2026-10-28", "2026-10-29")]:
            result = verify(page(incoming), published=original,
                            publication_date_provenance={"basis": "publisher_rss_pubDate", "date": original})
            self.assertEqual(result["published"], original)
            self.assertEqual(result["editorial_metadata"]["date_status"], "conflict")
            self.assertFalse(weekly_eligible(result, *previous_week(NOW)))
            repeated = metadata.verify_record(result, page(original), checked_at=NOW)
            self.assertEqual(repeated["publication_date_provenance"]["status"], "unresolved")
            self.assertTrue(repeated["publication_date_provenance"]["requires_explicit_date_resolution"])

    def test_conflicting_jsonld_and_meta_fields(self):
        result = verify(page(extra='<meta property="article:published_time" content="2026-09-01">'))
        self.assertEqual(result["editorial_metadata"]["date_status"], "conflict")
        self.assertEqual({x["date"] for x in result["publication_date_provenance"]["evidence"]}, {"2026-09-01", "2026-10-28"})

    def test_invalid_or_partial_original_fields_are_unresolved(self):
        for value in ["2026", "2026-10", "2026-02-30", "yesterday", 123, None]:
            result = verify(page(value))
            self.assertEqual(result["publication_date_provenance"]["status"], "unresolved", value)
            self.assertFalse(weekly_eligible(result, *previous_week(NOW)))

    def test_utc_boundary_not_local_calendar_day(self):
        result = verify(page("2026-11-01T23:30:00-05:00"), published="", publication_date_provenance={})
        self.assertEqual(result["published"], "2026-11-02")
        self.assertFalse(weekly_eligible(result, *previous_week(NOW)))

    def test_canonical_and_title_identity_required(self):
        for html, status in [
                (page(canonical="https://evil.example/article"), "canonical_identity_mismatch"),
                (page(canonical="https://www.eff.org/"), "canonical_identity_mismatch"),
                (page(title="This is another distinct article about attention"), "title_identity_mismatch")]:
            result = verify(html)
            self.assertEqual(result["editorial_metadata"]["status"], status)
            self.assertEqual(result["publication_date_provenance"], record()["publication_date_provenance"])
        result = metadata.verify_record(record(), page(), url="https://eff.org/article", checked_at=NOW)
        self.assertEqual(result["editorial_metadata"]["status"], "publisher_host_mismatch")

    def test_other_article_nodes_and_unrelated_dates_not_used(self):
        html = '<meta property="og:title" content="' + TITLE + '"><script type="application/ld+json">'
        html += json.dumps({"@graph": [{"@type": "WebSite", "datePublished": "2026-10-28"},
            {"@type": "Article", "headline": "Recommended unrelated article", "datePublished": "2026-10-28"},
            {"@type": "Article", "headline": TITLE, "url": "https://www.eff.org/unrelated", "datePublished": "2026-10-28"}]}) + '</script>'
        self.assertEqual(verify(html)["editorial_metadata"]["date_status"], "publisher_feed_only")

    def test_nested_main_entity_and_relative_canonical(self):
        html = '<link rel="canonical" href="/article"><script type="application/ld+json">'
        html += json.dumps({"@type": "WebPage", "mainEntity": {"@type": "Article", "headline": TITLE,
                      "mainEntityOfPage": {"@id": URL}, "datePublished": "2026-10-28"}}) + '</script>'
        self.assertEqual(verify(html)["editorial_metadata"]["date_status"], "verified")

    def test_title_publisher_suffix_only_exact_and_not_arbitrary_substring(self):
        html = '<title>' + TITLE + ' | Electronic Frontier Foundation</title><meta name="datePublished" content="2026-10-28">'
        self.assertEqual(verify(html)["editorial_metadata"]["identity"], "verified")
        html = html.replace(' | Electronic Frontier Foundation', ' and a different unrelated subject')
        self.assertEqual(verify(html)["editorial_metadata"]["identity"], "unverified")

    def test_no_outlet_or_topic_genre_inference(self):
        result = verify(page(section="Artificial Intelligence", **{"@type": "Article"}))
        self.assertEqual(result["source_type"], "policy")
        self.assertEqual(result["source_type_basis"], "provisional_feed_default")
        self.assertEqual(result["editorial_metadata"]["source_type_status"], "unresolved")

    def test_explicit_genres_and_specific_schema_types(self):
        for section, kind in [("Opinion", "opinion"), ("Analysis", "analysis"), ("Policy brief", "policy"), ("Reporting", "journalism")]:
            self.assertEqual(verify(page(section=section))["source_type"], kind)
        for value, kind in metadata.SCHEMA_GENRES.items():
            self.assertEqual(verify(page(section="AI", **{"@type": value}))["source_type"], kind)
        self.assertEqual(verify(page(section="AI", **{"@type": ["NewsArticle", "OpinionNewsArticle"]}))["source_type"], "opinion")

    def test_explicit_feed_type_conflict_preserved_on_repeat(self):
        result = verify(page(section="Opinion"), source_type="journalism", source_type_basis="publisher_item_category")
        self.assertEqual(result["source_type"], "journalism")
        self.assertEqual(result["editorial_metadata"]["source_type_status"], "conflict")
        repeated = metadata.verify_record(result, page(section="News"), checked_at=NOW)
        self.assertEqual(repeated["editorial_metadata"]["source_type_status"], "conflict")

    def test_paywall_and_bot_pages_stop(self):
        result = verify(page(isAccessibleForFree=False))
        self.assertEqual(result["editorial_metadata"]["status"], "publisher_access_restricted")
        self.assertEqual(result["editorial_metadata"]["date_status"], "unresolved")
        with self.assertRaisesRegex(ValueError, "access_challenge_not_article"):
            verify("Verify you are human " + page())

    def test_identity_query_preserved_but_never_persisted(self):
        url = URL + "?article=123&utm_campaign=hello"
        result = metadata.verify_record(record(url=url), page(canonical=URL + "?article=123"), url=url, checked_at=NOW)
        self.assertEqual(result["editorial_metadata"]["identity"], "verified")
        self.assertNotIn("?", result["editorial_metadata"]["source_url"])
        wrong = metadata.verify_record(record(url=url), page(canonical=URL + "?article=456"), url=url, checked_at=NOW)
        self.assertEqual(wrong["editorial_metadata"]["identity"], "unverified")


class ResumeTests(unittest.TestCase):
    def test_bounded_fair_resumption_and_no_refetch_unchanged(self):
        rows = [record(url=URL + str(i)) for i in range(5)]
        first, state, report = process(rows, max_records=2)
        self.assertEqual(report["attempted_records"], 2)
        second, state, report = process(first, state, max_records=2)
        self.assertEqual(report["attempted_records"], 2)
        final, state, report = process(second, state, max_records=2)
        self.assertEqual(report["attempted_records"], 1)
        fetcher = Mock()
        final, state, report = process(final, state, fetcher=fetcher)
        fetcher.assert_not_called()
        self.assertEqual(report["outcomes"]["already_checked"], 5)
        self.assertTrue(all(row["attempts"] == 1 for row in state["records"].values()))

    def test_request_and_deadline_budgets(self):
        rows = [record(url=URL + str(i)) for i in range(3)]
        _, _, report = process(rows, max_requests=1)
        self.assertEqual(report["requests"], 1)
        self.assertEqual(report["attempted_records"], 1)
        self.assertEqual(report["stop_reason"], "request_budget")
        fetcher = Mock()
        _, _, report = process(rows, fetcher=fetcher, deadline_seconds=0)
        fetcher.assert_not_called()
        self.assertEqual(report["stop_reason"], "deadline")

    def test_no_outside_week_or_historical_or_scholarly_fetch(self):
        rows = [record(published="2026-09-01"), record(published="2026-11-02"),
                record(historical_backfill=True), record(kind="scholarly"),
                record(published="", publication_date_provenance={})]
        fetcher = Mock(return_value=(page(), URL))
        _, _, report = process(rows, fetcher=fetcher)
        self.assertEqual(fetcher.call_count, 1)
        self.assertEqual(report["selected_records"], 1)

    def test_host_retry_after_and_permanent_access_stops(self):
        rows = [record(url=URL + str(i)) for i in range(3)]
        for code in (401, 403, 429):
            fetcher = Mock(side_effect=HTTPError(URL, code, "failure " + SECRET, {"Retry-After": "7200"}, None))
            original, state, report = process(rows, fetcher=fetcher)
            self.assertEqual(fetcher.call_count, 1)
            self.assertEqual(report["outcomes"]["host_paused"], 2)
            _, state, _ = process(original, state, fetcher=fetcher)
            self.assertEqual(fetcher.call_count, 1)
            if code == 429:
                self.assertEqual(state["host_backoff"]["www.eff.org"]["until"], "2026-11-07T14:00:00+00:00")
            else:
                self.assertTrue(state["host_backoff"]["www.eff.org"]["blocked"])
            self.assertNotIn(SECRET, json.dumps(state))

    def test_retry_after_longer_than_seven_days_is_preserved(self):
        from datetime import timedelta
        for header in ('2592000', 'Mon, 07 Dec 2026 12:00:00 GMT'):
            error=HTTPError(URL,429,'limited',{'Retry-After':header},None)
            output,state,_=process(fetcher=Mock(side_effect=error))
            self.assertEqual(state['host_backoff']['www.eff.org']['until'],(NOW+timedelta(days=30)).isoformat())
            no_call=Mock()
            metadata.process(output,state,now=NOW+timedelta(days=8),fetcher=no_call)
            no_call.assert_not_called()

    def test_unrepresentable_retry_after_holds_host(self):
        error=HTTPError(URL,429,'limited',{'Retry-After':str(10**40)},None)
        output,state,_=process(fetcher=Mock(side_effect=error))
        self.assertTrue(state['host_backoff']['www.eff.org']['blocked'])
        no_call=Mock()
        metadata.process(output,state,now=NOW,fetcher=no_call)
        no_call.assert_not_called()

    def test_retry_after_http_date_and_resume_when_due(self):
        fetcher = Mock(side_effect=HTTPError(URL, 429, "rate", {"Retry-After": "Sat, 07 Nov 2026 12:00:01 GMT"}, None))
        output, state, _ = process(fetcher=fetcher)
        self.assertEqual(state["host_backoff"]["www.eff.org"]["until"], "2026-11-07T12:00:01+00:00")
        output, state, report = metadata.process(output, state, now="2026-11-07T12:00:02Z", fetcher=lambda url: (page(), url))
        self.assertEqual(report["attempted_records"], 1)
        self.assertEqual(next(iter(state["records"].values()))["attempts"], 2)

    def test_changed_title_reopens_but_never_access_denial(self):
        output, state, _ = process()
        output[0]["title"] = TITLE + " today"
        fetcher = Mock(return_value=(page(title=output[0]["title"]), URL))
        _, _, report = process(output, state, fetcher=fetcher)
        self.assertEqual(report["attempted_records"], 1)
        blocked = Mock(side_effect=HTTPError(URL, 403, "blocked", {}, None))
        output, state, _ = process(fetcher=blocked)
        output[0]["title"] += " updated"
        _, _, report = process(output, state, fetcher=blocked)
        self.assertEqual(blocked.call_count, 1)

    def test_old_attempts_retained_but_not_counted_in_new_week(self):
        output, state, _ = process()
        fetcher = Mock()
        _, later, report = metadata.process(output, state, now="2026-11-09", fetcher=fetcher)
        fetcher.assert_not_called()
        self.assertEqual(len(later["records"]), 1)
        self.assertEqual(report["verified_original_dates"], 0)
        self.assertEqual(report["weekly_eligible_records"], 0)

    def test_state_is_closed_and_exception_details_not_saved(self):
        output, state, report = process(fetcher=Mock(side_effect=ValueError(SECRET)))
        state["body"] = SECRET
        row = next(iter(state["records"].values()))
        row["body"] = SECRET
        row["source_url"] = URL + "?token=" + SECRET
        row["status"] = SECRET
        _, clean, report = process(output, state)
        self.assertNotIn(SECRET, json.dumps(clean))
        self.assertNotIn(SECRET, json.dumps(report))

    def test_metadata_does_not_claim_full_article_retrieval(self):
        output, state, report = process()
        self.assertNotIn("full_articles_retrieved", report)
        self.assertFalse(report["source_text_saved"])
        self.assertFalse(report["model_used"])
        self.assertNotIn(SECRET, json.dumps(state))
        self.assertEqual(report["verified_original_dates"], 1)


class NetworkPolicyTests(unittest.TestCase):
    def test_disallowed_host_credentials_http_and_subdomains_fail_before_request(self):
        fetcher = metadata.MetadataFetcher(metadata.Budget(10, 30))
        for url in ["http://www.eff.org/a", "https://unreviewed.eff.org/a", "https://eff.org.evil.example/a",
                    "https://user:pass@www.eff.org/a", "https://www.eff.org/a?api_key=secret", "https://127.0.0.1/a"]:
            with patch.object(metadata, "build_opener") as opener:
                with self.assertRaisesRegex(ValueError, "unapproved_or_credentialed"):
                    fetcher(url)
                opener.assert_not_called()

    def test_robots_precedes_page_and_is_cached_per_host(self):
        fetcher = metadata.MetadataFetcher(metadata.Budget(10, 30))
        with patch.object(fetcher, "request", side_effect=[(b"User-agent: *\nDisallow: /private\n", "", "text/plain"),
              (page().encode(), URL, "text/html"), (page().encode(), URL + "2", "text/html")]) as request:
            fetcher(URL)
            fetcher(URL + "2")
            self.assertEqual(request.call_count, 3)
            self.assertEqual(request.call_args_list[0].args[0], "https://www.eff.org/robots.txt")
            with self.assertRaisesRegex(ValueError, "robots_disallow"):
                fetcher("https://www.eff.org/private")
            self.assertEqual(request.call_count, 3)

    def test_robots_403_no_article_request_and_404_allows(self):
        fetcher = metadata.MetadataFetcher(metadata.Budget(10, 30))
        with patch.object(fetcher, "request", side_effect=HTTPError(URL, 403, "denied", {}, None)) as request:
            with self.assertRaises(HTTPError):
                fetcher(URL)
            self.assertEqual(request.call_count, 1)
        with patch.object(fetcher, "request", side_effect=[HTTPError(URL, 404, "not found", {}, None), (page().encode(), URL, "text/html")]) as request:
            fetcher(URL)
            self.assertEqual(request.call_count, 2)

    def test_actual_request_budget_and_redirect_guard(self):
        budget = metadata.Budget(1, 30)
        fetcher = metadata.MetadataFetcher(budget)
        class Response(io.BytesIO):
            headers = {"Content-Type": "text/html"}
            def geturl(self):
                return URL
        with patch.object(metadata, "build_opener") as build:
            build.return_value.open.return_value = Response(page().encode())
            fetcher.request(URL, 100_000)
            self.assertEqual(budget.requests, 1)
            guard = build.call_args.args[0]
            req = Request(URL)
            req.timeout = 20
            with self.assertRaisesRegex(ValueError, "cross_host_redirect_requires_review"):
                guard.redirect_request(req, None, 302, "", {}, "https://eff.org/article")
            with self.assertRaisesRegex(metadata.BudgetExceeded, "request_budget"):
                guard.redirect_request(req, None, 302, "", {}, URL + "2")
            with self.assertRaisesRegex(ValueError, "credentialed_source_url_disallowed"):
                guard.redirect_request(req, None, 302, "", {}, URL + "?api_key=secret")

    def test_redirect_disallowed_by_robots_never_requested(self):
        from urllib.robotparser import RobotFileParser
        fetcher = metadata.MetadataFetcher(metadata.Budget(10, 30))
        robots = RobotFileParser()
        robots.parse(["User-agent: *", "Disallow: /private"])
        fetcher.robots["https://www.eff.org"] = robots
        with patch.object(metadata, "build_opener") as build:
            build.return_value.open.side_effect = URLError("fixture")
            with self.assertRaises(URLError):
                fetcher.request(URL, 100)
            guard = build.call_args.args[0]
            request = Request(URL)
            with self.assertRaisesRegex(ValueError, "robots_disallow"):
                guard.redirect_request(request, None, 302, "", {}, "https://www.eff.org/private")


class CLITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.library = self.root / "library.json"
        self.state = self.root / "state.json"
        self.status = self.root / "status.json"
        self.library.write_text(json.dumps([record()]))
        self.original_process = metadata.process
        self.fetcher = Mock(return_value=(page(), URL))

    def fixture_process(self, records, state, **kwargs):
        kwargs["now"] = NOW
        return self.original_process(records, state, fetcher=self.fetcher, **kwargs)

    def invoke(self, extra=None):
        output = io.StringIO()
        with patch.object(metadata, "process", side_effect=self.fixture_process), redirect_stdout(output):
            code = metadata.main(["--library", str(self.library), "--state", str(self.state),
                                  "--status", str(self.status)] + (extra or []))
        return code, json.loads(output.getvalue())

    def test_missing_state_starts_fresh_saves_metadata_and_resumes_without_fetch(self):
        self.assertFalse(self.state.exists())
        code, report = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(report["verified_original_dates"], 1)
        self.assertEqual(report["verified_source_types"], 1)
        self.assertNotIn("full_articles_retrieved", report)
        self.assertEqual(json.loads(self.status.read_text()), report)
        state = json.loads(self.state.read_text())
        self.assertNotIn(SECRET, json.dumps(state))
        self.assertEqual(json.loads(self.library.read_text())[0]["reading"], record()["reading"])
        code, report = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.fetcher.call_count, 1)
        self.assertEqual(report["attempted_records"], 0)

    def test_default_paths_and_budgets_and_explicit_flags(self):
        with patch.object(metadata, "run_files", return_value={"verified_original_dates": 0,
                "verified_source_types": 0}) as run, redirect_stdout(io.StringIO()):
            self.assertEqual(metadata.main([]), 0)
            self.assertEqual(run.call_args.args, (metadata.ROOT / "data/library.json",
                metadata.ROOT / "data/editorial-metadata-state.json", metadata.ROOT / "data/editorial-metadata-status.json"))
            self.assertEqual(run.call_args.kwargs, {"max_records": 24, "max_requests": 60, "deadline_seconds": 90})
            self.assertEqual(metadata.main(["--max-records", "2", "--max-requests", "5", "--time-budget", "3.5"]), 0)
            self.assertEqual(run.call_args.kwargs, {"max_records": 2, "max_requests": 5, "deadline_seconds": 3.5})

    def test_zero_budget_does_not_request_pages(self):
        code, report = self.invoke(["--time-budget", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(report["stop_reason"], "deadline")
        self.fetcher.assert_not_called()

    def test_invalid_cli_budgets_rejected_before_work(self):
        for arguments in [("--max-records", "-1"), ("--max-requests", "1.5"),
                          ("--time-budget", "nan"), ("--time-budget", "inf"), ("--time-budget", "-1")]:
            with patch.object(metadata, "run_files") as run, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    metadata.main(list(arguments))
                self.assertEqual(raised.exception.code, 2)
                run.assert_not_called()

    def test_invalid_state_json_never_silently_resets_access_stops(self):
        raw = "invalid JSON " + SECRET
        self.state.write_text(raw)
        before = self.library.read_text()
        code, report = self.invoke()
        self.assertEqual(code, 1)
        self.assertNotIn(SECRET, json.dumps(report))
        self.assertEqual(self.state.read_text(), raw)
        self.assertEqual(self.library.read_text(), before)
        self.assertFalse(self.status.exists())
        self.fetcher.assert_not_called()

    def test_invalid_state_structure_and_backoff_fail_before_requests(self):
        for value in [[], {"schema_version": 999}, {"records": []}, {"host_backoff": {"www.eff.org": []}},
                      {"host_backoff": {"www.eff.org": {"blocked": "true"}}},
                      {"host_backoff": {"www.eff.org": {"until": "invalid"}}}]:
            self.state.write_text(json.dumps(value))
            code, report = self.invoke()
            self.assertEqual(code, 1, value)
            self.assertEqual(json.loads(self.state.read_text()), value)
        self.fetcher.assert_not_called()

    def test_state_unknown_fields_and_query_tokens_removed_before_save(self):
        self.invoke()
        state = json.loads(self.state.read_text())
        state["body"] = SECRET
        row = next(iter(state["records"].values()))
        row["body"] = SECRET
        row["source_url"] += "?access_token=" + SECRET
        self.state.write_text(json.dumps(state))
        self.invoke()
        self.assertNotIn(SECRET, self.state.read_text())
        self.assertEqual(self.fetcher.call_count, 1)

    def test_atomic_state_then_library_interruption_is_resumable_even_metadata_only(self):
        # The result changes only editorial_metadata, not the trusted feed date
        # or source type. Its fingerprint must still detect an unsaved library.
        self.fetcher.return_value = ('<meta property="og:title" content="' + TITLE + '">', URL)
        original = self.library.read_text()
        replace = metadata.os.replace
        replaced = []
        def interrupted(source, target):
            replaced.append(Path(target).name)
            if Path(target) == self.library:
                raise OSError("interrupted " + SECRET)
            return replace(source, target)
        with patch.object(metadata.os, "replace", side_effect=interrupted):
            code, report = self.invoke()
        self.assertEqual(code, 1)
        self.assertNotIn(SECRET, json.dumps(report))
        self.assertEqual(replaced, ["state.json", "library.json"])
        self.assertTrue(self.state.exists())
        self.assertEqual(self.library.read_text(), original)
        self.assertFalse(self.status.exists())
        self.assertEqual(list(self.root.glob(".editorial-metadata-*.tmp")), [])
        code, report = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.fetcher.call_count, 2)
        self.assertEqual(next(iter(json.loads(self.state.read_text())["records"].values()))["attempts"], 2)
        self.assertEqual(json.loads(self.library.read_text())[0]["editorial_metadata"]["date_status"], "publisher_feed_only")

    def test_atomic_save_order_and_temporary_files_cleanup(self):
        replace = metadata.os.replace
        replaced = []
        def observed(source, target):
            self.assertEqual(Path(source).parent, Path(target).parent)
            self.assertTrue(Path(source).name.startswith(".editorial-metadata-"))
            json.loads(Path(source).read_text())
            replaced.append(Path(target).name)
            return replace(source, target)
        with patch.object(metadata.os, "replace", side_effect=observed):
            self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(replaced, ["state.json", "library.json", "status.json"])
        self.assertEqual(list(self.root.glob(".editorial-metadata-*.tmp")), [])

    def test_invalid_library_and_output_path_collision_never_fetch_or_replace(self):
        for value in [{"items": []}, ["bad record"], [float("nan")]]:
            self.library.write_text(json.dumps(value))
            code, _ = self.invoke()
            self.assertEqual(code, 1)
            self.assertFalse(self.state.exists())
        with self.assertRaisesRegex(ValueError, "paths_must_be_distinct"):
            metadata.run_files(self.library, self.library, self.status)
        self.fetcher.assert_not_called()

    def test_serialize_all_results_before_any_replacement(self):
        before = self.library.read_text()
        with patch.object(metadata, "process", return_value=([{"bad": float("nan")}], {}, {})), \
             patch.object(metadata, "atomic_json") as save:
            with self.assertRaises(ValueError):
                metadata.run_files(self.library, self.state, self.status)
            save.assert_not_called()
        self.assertEqual(self.library.read_text(), before)


if __name__ == "__main__":
    unittest.main()

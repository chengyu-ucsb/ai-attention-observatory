"""Offline abstract preservation and recurring discovery/adoption regressions."""
from copy import deepcopy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from abstract_metadata import MAX_ABSTRACT_CHARS, abstract_record, openalex_abstract, merge_abstract
from academic_state import DiscoveryState, cursor_search
from academic_state_schema import digest, validate_row
import enrich_metadata
import priority_research
import search_plan
import update
import weekly_preparation as prep

NOW = dt.datetime(2026, 11, 9, 0, 10, tzinfo=dt.timezone.utc)
SAT = dt.datetime(2026, 11, 7, 15, tzinfo=dt.timezone.utc)
WINDOW = {"from": "2026-11-02", "to": "2026-11-08"}
DOI = "10.1234/abstract-retention"
TITLE = "Generative AI and cognitive offloading"
# Synthetic text only. Results deliberately occur beyond both old cutoffs.
LONG = ("Generative AI and cognitive offloading were studied in a learning task. "
        + "The protocol specified repeated observations and a comparison condition. " * 57
        + "Results: The intervention group completed fewer unnecessary task switches. "
        + "The findings were limited to the observed setting.")


def invert(text):
    index = {}
    for position, word in enumerate(text.split()):
        index.setdefault(word, []).append(position)
    return index


def openalex(text=LONG, doi=DOI, title=TITLE, day="2026-11-07", **extra):
    return {"id": "https://openalex.org/W" + doi.rsplit("/", 1)[-1],
            "doi": "https://doi.org/" + doi, "title": title,
            "publication_date": day, "abstract_inverted_index": invert(text), **extra}


def crossref(text="AI cognitive offloading was studied.", doi=DOI, title=TITLE, day=(2026, 11, 7)):
    return {"DOI": doi, "type": "journal-article", "title": [title],
            "published": {"date-parts": [list(day)]}, "container-title": ["Computers & Education"],
            "abstract": text}


def candidate(text=LONG):
    return priority_research.crossref_article(crossref(text), lane="AI & cognition",
        scope="previous_publication_week", query="AI cognition", today=NOW.date(), screen=False)


class AbstractMetadataTests(unittest.TestCase):
    def test_complete_provider_text_keeps_late_results_and_small_preview(self):
        self.assertGreater(LONG.index("Results:"), 3800)
        fields = openalex_abstract(invert(LONG))
        self.assertEqual(fields["abstract_text"], LONG)
        self.assertIn("fewer unnecessary task switches", fields["abstract_text"])
        self.assertEqual(fields["preview"], LONG[:420] + "…")
        self.assertEqual(fields["abstract_completeness"], "provider_text_preserved")
        self.assertEqual(update.abstract(invert(LONG)), LONG)
        self.assertEqual(enrich_metadata.uninvert(invert(LONG)), LONG)

    def test_cap_and_overflow_space_cannot_claim_provider_completeness(self):
        for text in ("x" * 6000, "x" * 6001, "x" * 6000 + " tail", "x " * 20000):
            for fields in (abstract_record(text, "Provider"), openalex_abstract(invert(text))):
                with self.subTest(length=len(text), provider=fields["abstract_source"]):
                    expected = " ".join(text.split())
                    self.assertLessEqual(len(fields["abstract_text"]), MAX_ABSTRACT_CHARS)
                    self.assertEqual(fields["abstract_text"], expected[:MAX_ABSTRACT_CHARS].rstrip())
                    truncated = len(expected) > MAX_ABSTRACT_CHARS
                    self.assertEqual(fields["abstract_completeness"],
                                     "truncated" if truncated else "provider_text_preserved")
                    self.assertEqual("truncated at 6,000" in fields["abstract_source"], truncated)

    def test_missing_and_malformed_indexes_never_invent_complete_text(self):
        for index in (None, {}):
            self.assertEqual(openalex_abstract(index)["abstract_completeness"], "unavailable")
        bad = [[], "text", {"word": None}, {"word": 0}, {"word": "01"}, {"word": []},
               {None: [0]}, {3: [0]}, {" ": [0]}, {"word": [True]}, {"word": [False]},
               {"word": [-1]}, {"word": [1.0]}, {"word": ["0"]}, {"word": [1]},
               {"word": [0, 2]}, {"first": [0], "different": [0]}, {"word": [10**100]},
               {"first": [0], "distant": [10**100]}]
        for index in bad:
            with self.subTest(index=index):
                fields = openalex_abstract(index)
                self.assertEqual(fields["abstract_text"], "")
                self.assertEqual(fields["abstract_completeness"], "invalid_provider_index")

    def test_duplicate_positions_are_deduplicated_without_losing_repeated_words(self):
        index = {"again": [2, 0, 2], "and": [1, 1]}
        self.assertEqual(openalex_abstract(index)["abstract_text"], "again and again")
        self.assertEqual(openalex_abstract(index)["abstract_completeness"], "provider_text_preserved")
        self.assertEqual(openalex_abstract(dict(reversed(list(index.items())))), openalex_abstract(index))

    def test_crossref_and_enrichment_share_cap_and_keep_text_provenance_together(self):
        for text in (LONG, "x" * 7000):
            row = candidate(text)
            expected = abstract_record(text, "Crossref publisher-supplied abstract")
            for field in expected:
                self.assertEqual(row[field], expected[field])
            existing = {"abstract_text": text[:800], "reading": {"level": "abstract"}}
            self.assertTrue(enrich_metadata.enrich_record(existing, text, "Provider"))
            self.assertEqual(existing["abstract_text"], text[:6000])
            self.assertEqual(existing["abstract_completeness"], expected["abstract_completeness"])
            self.assertEqual(existing["reading"], {"level": "abstract"})
            self.assertFalse(enrich_metadata.enrich_record(existing, text, "Provider"))

    def test_merge_preserves_longer_sources_and_annotates_only_identical_legacy_text(self):
        current = abstract_record(LONG, "First provider")
        current["reading"] = {"findings": "Existing interpretation", "level": "abstract"}
        saved = deepcopy(current)
        self.assertFalse(merge_abstract(current, abstract_record(LONG[:800], "Short provider")))
        self.assertEqual(current, saved)
        del current["abstract_completeness"]
        self.assertTrue(merge_abstract(current, abstract_record(LONG, "First provider")))
        self.assertEqual(current, saved)
        current.pop("abstract_completeness")
        self.assertFalse(merge_abstract(current, abstract_record("z" * len(LONG), "Unrelated text")))
        # Legacy producers cannot leave a stale completeness receipt on new text.
        self.assertTrue(merge_abstract(saved, {"abstract_text": LONG + " More.", "abstract_source": "Legacy"}))
        self.assertNotIn("abstract_completeness", saved)
        self.assertEqual(saved["reading"], current["reading"])
        uncertain = abstract_record(LONG, "Old checkpoint", completeness="unknown")
        self.assertTrue(merge_abstract(uncertain, abstract_record(LONG, "Fresh provider")))
        self.assertEqual(uncertain["abstract_completeness"], "provider_text_preserved")

    def test_preparation_schema_retains_completeness_but_rejects_unknown_payloads(self):
        row = candidate()
        self.assertEqual(prep.metadata_record(row)["abstract_completeness"], "provider_text_preserved")
        for status in ({"approved": True}, "full_paper_read", True):
            with self.subTest(status=status), self.assertRaises(ValueError):
                prep.metadata_record(dict(row, abstract_completeness=status))
        with self.assertRaises(ValueError):
            prep.metadata_record(dict(row, abstract_text="x" * 6001))


class RecurringAbstractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        lanes = patch.object(search_plan, "LANES", {"AI & cognition": ["AI cognitive offloading"]})
        lanes.start(); self.addCleanup(lanes.stop)
        sleeps = patch.object(update.time, "sleep")
        sleeps.start(); self.addCleanup(sleeps.stop)
        self.oa = [openalex()]
        self.cr = [crossref()]
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        if "api.openalex.org" in url:
            return {"results": self.oa, "meta": {"count": len(self.oa)}}
        if "/works/10." in url:
            self.fail("Fixture candidates should share existing Crossref date evidence")
        return {"message": {"items": self.cr, "total-results": len(self.cr)}}

    def discover(self, state=None):
        return update.discover(observed_on=NOW, metadata_request=self.fetch, state=state)

    def prepare(self, **kwargs):
        return prep.prepare(self.root, feeds=[], manifest={"papers": [], "venue_queries": []},
                            academic_request=self.fetch, max_requests=100, max_feed_requests=0, **kwargs)

    def test_duplicate_queries_and_cached_replay_keep_late_results_once(self):
        with patch.object(search_plan, "LANES", {"AI & cognition": ["AI cognition", "AI offloading"]}):
            path = self.root / "checkpoint.json"
            state = DiscoveryState(path, window=WINDOW)
            rows, errors, _ = self.discover(state)
            self.assertFalse(errors)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["abstract_text"], LONG)
            calls = len(self.calls)
            replayed, errors, _ = self.discover(DiscoveryState(path, window=WINDOW))
        self.assertFalse(errors)
        self.assertEqual(replayed, rows)
        self.assertEqual(len(self.calls), calls)

    def test_oversize_sources_keep_truncation_through_checkpoint_and_replay(self):
        for provider, text in (("OpenAlex", "x" * 6000 + " tail"),
                               ("OpenAlex", "x " * 20000),
                               ("Crossref", "x" * 7000),
                               ("Crossref", "<jats:p>" + LONG + "</jats:p>")):
            with self.subTest(provider=provider, length=len(text)):
                work = openalex(text) if provider == "OpenAlex" else crossref(text)
                response = ({"results": [work], "meta": {"count": 1}} if provider == "OpenAlex"
                            else {"message": {"items": [work], "total-results": 1}})
                path = self.root / (provider + str(len(text)) + ".json")
                rows, _, errors = cursor_search(lambda _: response, provider, {},
                                                state=DiscoveryState(path, window=WINDOW))
                self.assertFalse(errors)
                replay, audit, errors = cursor_search(lambda _: self.fail("Completed query refetched"),
                    provider, {}, state=DiscoveryState(path, window=WINDOW))
                self.assertEqual(rows, replay)
                self.assertEqual(audit["requests_this_run"], 0)
                if provider == "OpenAlex":
                    fields = openalex_abstract(rows[0]["abstract_inverted_index"],
                                               completeness=rows[0]["abstract_completeness"])
                else:
                    fields = priority_research.crossref_article(rows[0], lane="AI & cognition",
                        scope="previous_publication_week", query="AI", today=NOW.date(), screen=False)
                expected = "provider_text_preserved" if text.startswith("<jats:p>") else "truncated"
                self.assertEqual(fields["abstract_completeness"], expected)
                self.assertLessEqual(len(fields["abstract_text"]), 6000)
                if expected == "provider_text_preserved":
                    self.assertEqual(fields["abstract_text"], LONG)

    def test_legacy_checkpoints_remain_unknown_without_changing_pages_or_cooldowns(self):
        path = self.root / "legacy.json"
        state = DiscoveryState(path, window=WINDOW)
        self.discover(state)
        for query in state.current["queries"].values():
            legacy = []
            for row in query["rows"].values():
                row.pop("abstract_completeness", None)
                if query["provider"] == "OpenAlex":
                    row["abstract_inverted_index"] = invert(LONG[:800])
                legacy.append(row)
            query["rows"] = {digest(row): row for row in legacy}
        state.data["providers"]["Crossref"].update(blocked=True, last_http_status=403, next_retry_at=9999999999)
        state.save()
        before = path.read_bytes()
        calls = len(self.calls)
        rows, errors, _ = self.discover(DiscoveryState(path, window=WINDOW))
        self.assertFalse(errors)
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(rows[0]["abstract_completeness"], "unknown")
        self.assertIn("completeness unknown", rows[0]["abstract_source"])
        reloaded = DiscoveryState(path, window=WINDOW)
        for query in reloaded.current["queries"].values():
            replay, _, errors = cursor_search(lambda _: self.fail("Legacy query refetched"),
                query["provider"], query["params"], state=reloaded, page_size=query["page_size"])
            self.assertFalse(errors)
            self.assertTrue(all(row["abstract_completeness"] == "unknown" for row in replay))

    def test_invalid_indexes_are_omitted_in_actual_cursor_projection(self):
        self.oa = [openalex()]
        self.oa[0]["abstract_inverted_index"] = {"first": [0], "conflict": [0]}
        self.cr = [crossref("")]
        rows, errors, _ = self.discover()
        self.assertFalse(errors)
        self.assertEqual(rows[0]["abstract_text"], "")
        self.assertEqual(rows[0]["abstract_completeness"], "invalid_provider_index")

    def test_checkpoint_coverage_is_closed_and_bounded(self):
        for provider, row in (("Crossref", {"abstract": "x"}),
                              ("OpenAlex", {"abstract_inverted_index": {"x": [0]}})):
            for status in ("full_paper_read", {"approved": True}, True, "unavailable"):
                with self.subTest(provider=provider, status=status), self.assertRaises(ValueError):
                    validate_row(provider, dict(row, abstract_completeness=status))
        with self.assertRaises(ValueError):
            validate_row("OpenAlex", {"abstract_inverted_index": {"x" * 6001: [0]},
                                      "abstract_completeness": "truncated"})

    def test_long_abstract_does_not_bypass_original_date_retraction_or_topic_gates(self):
        self.oa += [openalex(doi="10.1234/old"), openalex(doi="10.1234/unknown"),
                    openalex(doi="10.1234/future", day="2026-11-09"),
                    openalex(doi="10.1234/retracted", is_retracted=True),
                    openalex("Cross-attention architectures improve model scores. " * 80,
                             doi="10.1234/computational", title="Cross-attention neural architecture")]
        self.cr += [crossref(doi="10.1234/old", day=(2026, 9, 1)),
                    crossref(doi="10.1234/unknown", day=(2026, 11)),
                    crossref(doi="10.1234/future", day=(2026, 11, 9)),
                    crossref("Cross-attention architectures improve model scores.",
                             doi="10.1234/computational", title="Cross-attention neural architecture")]
        packet = self.prepare(now=NOW, closeout=True)
        self.assertEqual([row["doi"] for row in packet["items"]], [DOI])
        self.assertEqual(packet["items"][0]["published"], "2026-11-07")
        self.assertTrue(any(row.get("doi") == "10.1234/unknown" for row in packet["quarantine"]))

    def test_preparation_refresh_replay_and_closeout_adoption_preserve_late_results(self):
        self.oa = [openalex(LONG[:800])]
        early = self.prepare(now=SAT)
        self.assertEqual(len(early["items"][0]["abstract_text"]), 800)
        self.oa = [openalex()]
        packet = self.prepare(now=NOW, closeout=True)
        self.assertEqual(packet["items"][0]["abstract_text"], LONG)
        self.assertEqual(packet["items"][0]["abstract_completeness"], "provider_text_preserved")
        old = deepcopy(early["items"][0])
        old.update(reading={"level": "abstract", "findings": "Existing reading"},
                   approved=True, source_checked="2026-11-07")
        saved = deepcopy(old)
        adopted = prep.adopt_closed_packet(packet, [old], NOW)
        self.assertEqual(old, saved)
        for row in (adopted["library"][0], adopted["weekly"]["items"][0]):
            self.assertEqual(row["abstract_text"], LONG)
            self.assertEqual(row["abstract_completeness"], "provider_text_preserved")
            for field in ("reading", "approved", "source_checked", "first_seen"):
                self.assertEqual(row[field], old[field])
        calls = len(self.calls)
        replay = self.prepare(now=NOW + dt.timedelta(hours=1), closeout=True)
        self.assertEqual(replay["items"][0]["abstract_text"], LONG)
        self.assertEqual(len(self.calls), calls)

    def test_main_upgrades_legacy_800_character_record_and_stays_idempotent(self):
        row = candidate()
        old = deepcopy(row)
        old.update(abstract_text=LONG[:800], abstract_source="OpenAlex abstract index",
                   reading={"level": "abstract", "findings": "Keep this reading"}, first_seen="2026-11-07")
        old.pop("abstract_completeness")
        data = self.root / "data"
        (data / "library.json").write_text(json.dumps([old]))
        with patch.object(update, "DIR", data), patch.object(update, "TODAY", NOW.date().isoformat()), \
                patch.dict("os.environ", {"MODE": "weekly"}, clear=True), \
                patch.object(update, "discover", return_value=([row], [], {})), \
                patch.object(update, "discover_priority", return_value=([], [], {})), patch("builtins.print"):
            update.main()
            first = json.loads((data / "library.json").read_text())
            update.main()
            second = json.loads((data / "library.json").read_text())
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["abstract_text"], LONG)
        self.assertEqual(first[0]["abstract_completeness"], "provider_text_preserved")
        self.assertEqual(first[0]["reading"], old["reading"])
        self.assertEqual(first[0]["first_seen"], old["first_seen"])


if __name__ == "__main__":
    unittest.main()

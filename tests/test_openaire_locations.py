"""OpenAIRE schema and identity regressions; every response is an offline fixture."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from openaire_locations import openaire_candidates


DOI = "10.1016/j.chb.2024.108386"
FIRST = "https://opus.bibliothek.uni-augsburg.de/opus4/files/114673/114673.pdf"
SECOND = "https://epub.ub.uni-muenchen.de/125262/1/1-s2.0-S0747563224002541-main.pdf"


def pid(value=DOI):
    return {"@classid": "doi", "$": value}


def wrapped(publication):
    return {"metadata": {"oaf:entity": {"oaf:result": publication}}}


def payload(*publications, single=False):
    values = [wrapped(p) for p in publications]
    return {"response": {"results": {"result": values[0] if single else values}}}


class OpenAireLocationTests(unittest.TestCase):
    def test_real_nested_schema_keeps_later_repository_and_direct_fulltext(self):
        data = payload({"pid": pid(), "children": {
            "result": [
                {"instance": {"url": {"$": FIRST}, "license": {"$": "CC BY"}}},
                {"instance": {"fulltext": {"$": SECOND},
                              "webresource": {"url": {"$": "https://epub.ub.uni-muenchen.de/125262/"}}}},
            ],
            "instance": {"webresource": {"url": {"$": "https://doi.org/" + DOI}}},
        }})
        get = Mock(return_value=data)
        rows = openaire_candidates(DOI, get)
        self.assertEqual([r["url"] for r in rows], [FIRST, SECOND,
                         "https://epub.ub.uni-muenchen.de/125262/", "https://doi.org/" + DOI])
        self.assertEqual(rows[0]["license"], "CC BY")
        self.assertIsNone(rows[1]["license"])
        self.assertTrue(all(r["version"] == "unspecified" for r in rows))
        self.assertTrue(all(r["redistribution_granted"] is False for r in rows))
        # The locator never tries the failing first repository. Both alternatives
        # reach the reader, which owns retry/failure handling.
        get.assert_called_once()
        request = urlsplit(get.call_args.args[0])
        self.assertEqual(request.netloc, "api.openaire.eu")
        self.assertEqual(parse_qs(request.query), {"doi": [DOI], "format": ["json"]})

    def test_single_and_list_fields_and_duplicate_urls(self):
        instance = {"version": {"$": "acceptedVersion"},
                    "license": {"$": "CC BY-NC"}, "url": [{"$": SECOND}, {"$": SECOND}],
                    "webresource": [{"url": {"$": SECOND}}]}
        for child in ({"instance": instance}, [{"instance": [instance]}]):
            with self.subTest(child=child):
                data = payload({"pid": [pid()], "children": {"result": child}}, single=True)
                rows = openaire_candidates("https://doi.org/" + DOI.upper(), lambda url: data)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["doi"], DOI)
                self.assertEqual(rows[0]["version"], "acceptedVersion")
                self.assertEqual(rows[0]["license"], "CC BY-NC")

    def test_cited_doi_never_matches_another_publication(self):
        wrong = {"pid": pid("10.5555/wrong"), "fulltext": {"$": FIRST},
                 "rels": {"rel": {"pid": pid(), "fulltext": {"$": SECOND}}}}
        self.assertEqual(openaire_candidates(DOI, lambda url: payload(wrong)), [])

    def test_missing_parent_pid_cannot_be_repaired_by_nested_matching_doi(self):
        data = payload({"children": {"result": {"pid": pid(), "fulltext": {"$": FIRST}}}})
        self.assertEqual(openaire_candidates(DOI, lambda url: data), [])

    def test_wrong_child_and_related_work_are_not_candidates(self):
        data = payload({"pid": pid(), "fulltext": {"$": SECOND},
            "rels": {"rel": {"fulltext": {"$": "https://example.org/reference.pdf"}}},
            "children": {"result": {"pid": pid("10.5555/wrong"), "instance": {"url": {"$": FIRST}}}},
            "webresource": {"url": {"$": "https://doi.org/10.5555/wrong"}}})
        self.assertEqual([r["url"] for r in openaire_candidates(DOI, lambda url: data)], [SECOND])

    def test_private_credentialed_and_signed_locations_are_rejected(self):
        bad = ["http://example.org/paper.pdf", "https://127.0.0.1/a.pdf",
               "https://[::1]/a.pdf", "https://localhost/a.pdf", "https://host.internal/a.pdf",
               "https://10.0.0.1/a.pdf", "https://2130706433/a.pdf",
               "https://user:password@example.org/a.pdf", "https://example.org:8443/a.pdf",
               "https://example.org/a.pdf?X-Amz-Signature=secret",
               "https://example.org/a.pdf?access_token=secret",
               "https://example.org/a.pdf?api_key=secret"]
        good = "https://example.org/a.pdf?download=true"
        data = payload({"pid": pid(), "instance": {"url": [{"$": v} for v in bad + [good + "#page=1"]]}})
        rows = openaire_candidates(DOI, lambda url: data)
        self.assertEqual([r["url"] for r in rows], [good])

    def test_invalid_identifier_is_rejected_before_any_request(self):
        get = Mock()
        for value in [None, "10.1234", "10.x/article", "https://evil.org/10.5555/a",
                      "10.5555/a?token=secret", "10.5555/a\nnext", "10.5555/a%0Aevil"]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "invalid_doi"):
                openaire_candidates(value, get)
        get.assert_not_called()

    def test_empty_results_and_malformed_wrappers_are_empty(self):
        for data in [{}, None, {"response": {"results": None}},
                     {"response": {"results": {"result": [None, {"metadata": None}]}}}]:
            with self.subTest(data=data):
                self.assertEqual(openaire_candidates(DOI, lambda url: data), [])

    def test_http_error_propagates_for_callers_diagnostics(self):
        get = Mock(side_effect=HTTPError("https://api.openaire.eu", 429, "quota", {}, None))
        with self.assertRaises(HTTPError) as error:
            openaire_candidates(DOI, get)
        self.assertEqual(error.exception.code, 429)


if __name__ == "__main__":
    unittest.main()

"""Regression checks for source-level analytical depth (no network/API calls)."""
import pathlib, sys, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from condense_readings import annotate, deep_perspective
from enrich_deep_readings import ArticleParser, acceptable, host_allowed, process

class DeepReadingTests(unittest.TestCase):
 def test_editorial_essay_has_substantive_argument_parts(self):
  record={
   "kind":"nonacademic",
   "url":"https://www.techpolicy.press/the-internet-was-built-for-human-agency-ai-agents-are-changing-the-rules/",
   "title":"The Internet Was Built For Human Agency. AI Agents Are Changing the Rules.",
   "reading":{"level":"curated","overview":"The Internet's infrastructure was designed around humans."},
   "editorial_notes":{"argument":"AI agents act with delegated authority; authentication is not enough.",
                      "design_relevance":"A focus assistant should show who approved each action.",
                      "caveat":"The essay is a governance argument."}
  }
  note=annotate(record)["reading"]["digest"]
  self.assertEqual(note["status"],"edited_perspective")
  self.assertIn("principal",note["longform"]["examples"].lower())
  self.assertIn("approved",note["longform"]["open_question"])
  self.assertIn("focus assistant",note["longform"]["implications"])
  self.assertEqual(note["finding"],"")

 def test_publisher_synopsis_does_not_invent_analysis(self):
  record={"kind":"nonacademic","title":"Future digital attention assistant",
          "url":"https://theverge.com/future-focus",
          "reading":{"level":"curated","overview":"A company introduces a new focus assistant for office workers."}}
  note=annotate(record)["reading"]["digest"]
  self.assertEqual(note["longform"]["source_depth"],"publisher_synopsis")
  self.assertEqual(note["longform"]["reasoning"],"")
  self.assertEqual(note["longform"]["tension"],"")
  self.assertIn("company",note["longform"]["thesis"])
  self.assertEqual(note["finding"],"")

 def test_machine_synthesis_keeps_status_explicit(self):
  record={"kind":"nonacademic","title":"Digital attention and AI",
    "url":"https://theverge.com/attention-and-ai",
    "reading":{"level":"curated","overview":"Publisher blurb."},
    "deep_analysis":{"kind":"nonacademic","source_depth":"source_html",
     "thesis":"This essay considers why AI may shape what captures attention.",
     "reasoning":"It follows the incentives behind recommendation platforms.",
     "examples":"The essay discusses a fictional video-feed design.",
     "tension":"Convenience can undermine agency.", "implications":"A filter could explain its criteria.",
     "open_question":"Who sets its priorities?", "qualification":"A design argument.",
     "basis":"AI-assisted analysis of accessible article text"}}
  d=annotate(record)["reading"]["digest"]
  self.assertEqual(d["longform"]["source_depth"],"machine_read_full_article")
  self.assertEqual(d["longform"]["reasoning"],record["deep_analysis"]["reasoning"])

 def test_scholarly_longform_is_only_published_for_fulltext(self):
  record={"kind":"scholarly","title":"Attention and AI","doi":"10.5555/new",
    "reading":{"level":"full_text","findings":"We found differences.","methods":"Three interviews."},
    "deep_analysis":{"kind":"scholarly","source_depth":"full_text",
      "research_question":"What changes?","study_design":"An interview study.",
      "reported_results":"People described different attention habits."}}
  d=annotate(record)["reading"]["digest"]
  self.assertIn("longform",d)
  record["reading"]["level"]="abstract"
  self.assertNotIn("longform",annotate(record)["reading"]["digest"])

 def test_parser_discards_navigation(self):
  parser=ArticleParser()
  parser.feed('<main><nav><p>Ignore the navigation text which is long enough for inclusion.</p></nav>'
              '<article><h2>Agency and Delegation</h2>'
              '<p>Humans should remain in control when their agents make choices on their behalf and across many services.</p>'
              '</article></main><footer><p>Ignore promotional material in the footer and never index this section.</p></footer>')
  self.assertEqual(len(parser.paragraphs),1)
  self.assertIn("Humans should",parser.paragraphs[0])
  self.assertNotIn("Ignore",parser.paragraphs[0])

 def test_unapproved_hosts_and_claim_validation(self):
  self.assertFalse(host_allowed("https://news.google.com/rss/articles/example"))
  self.assertFalse(host_allowed("http://theconversation.com/article"))
  self.assertFalse(host_allowed("https://theconversation.com.evil.test/article"))
  self.assertTrue(host_allowed("https://www.techpolicy.press/story/"))
  sample="Our source develops the argument through an explicit case of attention governance. "*30
  note={"thesis":"An account "+("with detailed claims "*14),
        "reasoning":"The explanation "+("is in the text "*20),
        "examples":"One example "+("of the policy "*20),
        "anchors":["no such phrase exists","another absent phrase"]}
  self.assertFalse(acceptable(note,sample,"nonacademic"))

 def test_no_api_key_never_makes_network_requests(self):
  records=[{"kind":"nonacademic","url":"https://www.techpolicy.press/story/",
            "reading":{"level":"curated"}}]
  stats=process(records,"",limit=1)
  self.assertTrue(stats["skipped_no_key"])
  self.assertFalse(records[0].get("deep_analysis"))

if __name__=="__main__": unittest.main()

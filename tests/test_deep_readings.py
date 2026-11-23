"""Regression checks for source-level analytical depth (no network/API calls)."""
import pathlib, sys, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from condense_readings import annotate, deep_perspective
from enrich_deep_readings import ArticleParser, acceptable, host_allowed, process, has_copied_sequence

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
  self.assertIn("inspect",note["longform"]["open_question"])
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

 def test_unverified_media_prose_stays_out_of_the_article(self):
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
  self.assertEqual(d["longform"]["source_depth"],"publisher_synopsis")
  self.assertEqual(d["longform"]["reasoning"],"")
  from test_prepared_reading_schema import generated
  from reading_depth import depth_audit
  thesis="Some instructors ask students to review every automated correction."
  example="The article follows one class that compared edited drafts with their original wording."
  verified=generated(kind="nonacademic",claim_field="thesis",claim_text=thesis)
  verified["reading"]={"level":"curated","overview":"The publisher describes a classroom exercise with automated feedback."}
  fallback=annotate(verified)
  self.assertEqual(fallback["reading"]["digest"]["longform"]["thesis"],verified["reading"]["overview"])
  self.assertIn("checked_evidence_needs_elaboration",depth_audit([fallback])["summary_review"][0]["reasons"])
  verified=generated(kind="nonacademic",claim_field="thesis",claim_text=thesis,support={"examples":example})
  d=annotate(verified)["reading"]["digest"]
  self.assertEqual(d["longform"]["source_depth"],"machine_read_full_article")
  self.assertEqual(d["longform"]["examples"],example)

 def test_scholarly_longform_is_only_published_for_fulltext(self):
  record={"kind":"scholarly","title":"Attention and AI","doi":"10.5555/new",
    "reading":{"level":"full_text","findings":"We found differences.","methods":"Three interviews."},
    "deep_analysis":{"kind":"scholarly","source_depth":"full_text",
      "research_question":"What changes?","study_design":"An interview study.",
      "reported_results":"People described different attention habits."}}
  d=annotate(record)["reading"]["digest"]
  self.assertNotIn("longform",d)
  self.assertNotIn("machine_account",annotate(record)["reading"])
  from test_prepared_reading_schema import generated
  from build_public import readable
  from build_reader import article
  from reading_depth import depth_audit
  record=generated(claim_field="study_design")
  record["abstract_text"]=("One group used paper feedback and the other group used online feedback. "
                           "Participants reported how often they revised their original responses.")
  record["reading"]={"level":"full_text","machine_account":{"source_url":record["url"]}}
  fallback=annotate(record)
  self.assertEqual(fallback["reading"]["level"],"abstract")
  self.assertNotIn("machine_account",fallback["reading"])
  self.assertTrue(readable(fallback))
  self.assertIn("checked_evidence_needs_elaboration",depth_audit([fallback])["summary_review"][0]["reasons"])
  self.assertIn("study_design",fallback["deep_analysis"])
  result="The group receiving online feedback revised more of their original responses."
  record=generated(claim_field="study_design",support={"reported_results":result})
  record["reading"]={"level":"citation_only"}
  published=annotate(record)
  account=published["reading"]["machine_account"]
  self.assertEqual(account["study_design"],record["deep_analysis"]["study_design"])
  self.assertTrue(readable(published))
  self.assertFalse(depth_audit([published])["summary_review"])
  self.assertEqual(article(published)["reading"]["machine_account"],account)
  self.assertFalse({"coverage","claim_evidence","source_hash"}&set(account))
  record["deep_analysis"]["coverage"]["chunks_processed"]=0
  self.assertNotIn("machine_account",annotate(record)["reading"])
  self.assertFalse(readable(annotate(record)))

 def test_argument_support_depends_on_genre(self):
  from condense_readings import substantive_machine_account
  design="Students would compare their initial answers with revised answers."
  argument="The authors propose that explaining a revision reveals a learner’s judgment."
  example="Teachers could examine which recommendations a student accepted and why."
  self.assertFalse(substantive_machine_account({"research_question":argument},"research"))
  self.assertFalse(substantive_machine_account({"reported_results":design,"study_design":design},"review"))
  self.assertFalse(substantive_machine_account({"study_design":design},"proposal"))
  self.assertTrue(substantive_machine_account({"study_design":design,"critical_context":example},"proposal"))
  self.assertFalse(substantive_machine_account({"authors_interpretation":argument},"conceptual"))
  self.assertTrue(substantive_machine_account({"authors_interpretation":argument,"critical_context":example},"conceptual"))
  self.assertFalse(substantive_machine_account({"thesis":argument,"qualification":example},"nonacademic"))
  self.assertFalse(substantive_machine_account({"reported_results":argument,"study_design":design,
                    "account_status":"checked_evidence_only"},"research"))

 def test_parser_discards_navigation(self):
  parser=ArticleParser()
  parser.feed('<main><nav><p>Ignore the navigation text which is long enough for inclusion.</p></nav>'
              '<article><h2>Agency and Delegation</h2>'
              '<p>Humans should remain in control when their agents make choices on their behalf and across many services.</p>'
              '</article></main><footer><p>Ignore promotional material in the footer and never index this section.</p></footer>')
  self.assertEqual(len(parser.paragraphs),2)
  self.assertEqual(parser.paragraphs[0],"Agency and Delegation")
  self.assertIn("Humans should",parser.paragraphs[1])
  self.assertNotIn("Ignore"," ".join(parser.paragraphs))

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

 def test_no_local_model_never_makes_network_requests(self):
  records=[{"kind":"nonacademic","url":"https://www.techpolicy.press/story/",
            "reading":{"level":"curated"}}]
  stats=process(records,None,limit=1)
  self.assertTrue(stats["skipped_no_model"])
  self.assertFalse(records[0].get("deep_analysis"))

 def test_reject_direct_text_copying(self):
  text="Attention guardians could help people decide what they want to see instead of following someone else's metrics and incentives."
  answer={"thesis":text, "reasoning":"A distinct argument about how technology affects agency."}
  self.assertTrue(has_copied_sequence(answer,text))

 def test_accept_source_anchors_but_reject_missing_analysis(self):
  text=("Digital platforms change what gets attention in everyday life. "
        "User control should remain meaningful even when agents make decisions. ")*30
  answer={"thesis":"Some ideas about platforms and humans.", "reasoning":"A generic summary.",
          "anchors":["Digital platforms change what gets", "User control should remain meaningful"]}
  self.assertFalse(acceptable(answer,text,"nonacademic"))

if __name__=="__main__": unittest.main()

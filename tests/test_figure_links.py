"""Figure images must be source-hosted and verified, not constructed as fake charts."""
import sys,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
from enrich_figure_links import url_for,s3_candidates
class FigureSafetyTests(unittest.TestCase):
 def test_pmc_image_candidate_is_source_hosted(self):
  self.assertEqual(url_for("PMC123456","paper-fig1.jpg"),
   "https://pmc.ncbi.nlm.nih.gov/articles/PMC123456/bin/paper-fig1.jpg")
 def test_nonimage_or_unsafe_paths_rejected(self):
  self.assertEqual(url_for("PMC123456",".."),"")
  self.assertEqual(url_for("PMC123456","unsafe/name?.svg"),"")
  self.assertEqual(url_for("PMC123456",""),"")
 def test_2026_aws_figure_candidate_urls_are_hosted_and_versioned(self):
  urls=s3_candidates("PMC123456",1,"figure-1")
  self.assertIn("https://pmc-oa-opendata.s3.amazonaws.com/PMC123456.1/figure-1.jpg",urls)
  self.assertTrue(all(x.startswith("https://pmc-oa-opendata.s3.amazonaws.com/PMC123456.1/") for x in urls))
 def test_no_guess_for_unsupported_or_unsafe_figure_media(self):
  self.assertEqual(s3_candidates("PMC123456",1,"test.tif"),[])
  self.assertEqual(s3_candidates("PMC123456",1,"../../script.js"),[])
  self.assertEqual(s3_candidates("PMC123456",9,"Figure1"),[])
if __name__=="__main__":unittest.main()

"""Figure images must be source-hosted and verified, not constructed as fake charts."""
import sys,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
from enrich_figure_links import url_for
class FigureSafetyTests(unittest.TestCase):
 def test_pmc_image_candidate_is_source_hosted(self):
  self.assertEqual(url_for("PMC123456","paper-fig1.jpg"),
   "https://pmc.ncbi.nlm.nih.gov/articles/PMC123456/bin/paper-fig1.jpg")
 def test_nonimage_or_unsafe_paths_rejected(self):
  self.assertEqual(url_for("PMC123456",".."),"")
  self.assertEqual(url_for("PMC123456","unsafe/name?.svg"),"")
  self.assertEqual(url_for("PMC123456",""),"")
if __name__=="__main__":unittest.main()

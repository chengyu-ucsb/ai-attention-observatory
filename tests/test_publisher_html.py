"""Publisher HTML fallback, deliberately restricted to licensed official sources."""
import hashlib
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import enrich_publisher_html as publisher

ARTICLE='''<html><head><meta name="citation_doi" content="10.3389/fpsyg.2026.12345"/>
<link rel="license" href="https://creativecommons.org/licenses/by/4.0/"/></head>
<body><nav><h2>Results</h2><p>Unrelated navigation and advertising.</p></nav>
<article><h2>2. Methods</h2><p>We recruited 310 students to examine how a generative AI assistant shaped sustained task attention during a writing exercise.</p>
<h2>3. Results</h2><p>Students relying heavily on the AI system reported more interruptions and less confidence in evaluating answers independently.</p>
<h2>4. Discussion</h2><p>The observed association does not distinguish self-selection from any effect of the technology itself.</p>
<h2>References</h2><p>Previous research has shown large unrelated effects on cognitive processes.</p></article></body></html>'''
class PublisherHTMLTests(unittest.TestCase):
 def test_parse_licensed_full_article_not_nav_or_references(self):
  text,error=publisher.parse(ARTICLE,"10.3389/fpsyg.2026.12345")
  self.assertIsNone(error)
  self.assertIn("310 students",text["methods"])
  self.assertIn("less confidence",text["results"])
  self.assertNotIn("Unrelated navigation",str(text))
  self.assertNotIn("large unrelated effects",str(text))
 def test_denies_unlicensed_source(self):
  text,error=publisher.parse(ARTICLE.replace("creativecommons.org/licenses/by/4.0/","creativecommons.org/licenses/by-nc/4.0/"),"10.3389/fpsyg.2026.12345")
  self.assertEqual(error,"license_not_verified");self.assertEqual(text,{})
 def test_primary_identity_not_bibliography_occurrence(self):
  wrong=ARTICLE.replace('content="10.3389/fpsyg.2026.12345"','content="10.3389/fpsyg.2026.99999"')
  wrong=wrong.replace('</article>','<p>Cited DOI 10.3389/fpsyg.2026.12345</p></article>')
  self.assertEqual(publisher.parse(wrong,'10.3389/fpsyg.2026.12345')[1],'primary_doi_not_verified')
  missing=ARTICLE.replace('name="citation_doi"','name="unrelated"')
  self.assertEqual(publisher.parse(missing,'10.3389/fpsyg.2026.12345')[1],'primary_doi_not_verified')
  conflicting=ARTICLE.replace('</head>','<meta name="dc.identifier" content="doi:10.3389/fpsyg.2026.99999"></head>')
  self.assertEqual(publisher.parse(conflicting,'10.3389/fpsyg.2026.12345')[1],'primary_doi_not_verified')
  conflicting=conflicting.replace('name="dc.identifier"','name="citation_doi"')
  self.assertEqual(publisher.parse(conflicting,'10.3389/fpsyg.2026.12345')[1],'primary_doi_not_verified')
 def test_concrete_unambiguous_cc_by_license_required(self):
  for license_path in ('by-nc-nd/4.0/','by-nc/4.0/','by-nd/4.0/','by/9.0/','by/4.0/?restriction=nc','by/4.0/;restriction=nc'):
   html=ARTICLE.replace('by/4.0/',license_path)
   self.assertEqual(publisher.parse(html,'10.3389/fpsyg.2026.12345')[1],'license_not_verified')
  phrase=ARTICLE.replace('<link rel="license" href="https://creativecommons.org/licenses/by/4.0/"/>','Licensed under the Creative Commons Attribution license')
  self.assertEqual(publisher.parse(phrase,'10.3389/fpsyg.2026.12345')[1],'license_not_verified')
  for wrapper in ('<!-- {} -->','<script>const license = `{}`;</script>'):
   hidden=ARTICLE.replace('<link rel="license" href="https://creativecommons.org/licenses/by/4.0/"/>',wrapper.format('<a href="https://creativecommons.org/licenses/by/4.0/">license</a>'))
   self.assertEqual(publisher.parse(hidden,'10.3389/fpsyg.2026.12345')[1],'license_not_verified')
  mixed=ARTICLE.replace('</head>','<link rel="license" href="https://creativecommons.org/licenses/by-nc-nd/4.0/"></head>')
  self.assertEqual(publisher.parse(mixed,'10.3389/fpsyg.2026.12345')[1],'license_not_verified')
  for version in ('3.0','4.0'):
   self.assertIsNone(publisher.parse(ARTICLE.replace('by/4.0','by/'+version),'10.3389/fpsyg.2026.12345')[1])
 def test_doi_and_host_scope_is_narrow(self):
  self.assertIn("journals/psychology",publisher.url_for("10.3389/fpsyg.2026.12345"))
  self.assertEqual(publisher.url_for("10.1234/anything"),"")
  self.assertEqual(publisher.url_for("javascript://bad"),"")
 def test_saves_real_source_sections_not_html(self):
  with tempfile.TemporaryDirectory() as d:
   file=Path(d)/"library.json"
   file.write_text(json.dumps([{"kind":"scholarly","doi":"10.3389/fpsyg.2026.12345","published":"2026-03-03"}]))
   with patch.object(publisher,"LIB",file),patch.object(publisher,"fetch_article",return_value=(ARTICLE,"https://www.frontiersin.org/articles/verified/full")),patch.object(publisher.time,"sleep"):
    result=publisher.run()
   self.assertEqual(result["new_fulltexts"],1)
   row=json.loads(file.read_text())[0]
   self.assertEqual(row["analysis"]["extraction_version"],4)
   self.assertEqual(row["analysis"]["license"],"cc-by (source webpage verified)")
   self.assertNotIn("<html>",str(row["analysis"]))

class PublisherSectionRepairTests(unittest.TestCase):
 def article(self, body):
  return ARTICLE.split('<body>')[0]+'<body><article>'+body+'</article></body></html>'
 def paragraph(self, text):
  return '<p>'+text+' This is synthetic source prose long enough to test section extraction with clear context and explicitly invented observations.</p>'
 def test_nested_results_and_boundaries(self):
  html=self.article('<h2>Methodology</h2><h3>Design</h3>'+self.paragraph('METHOD')+
   '<h3>Path results</h3>'+self.paragraph('OBSERVED_PATH')+
   '<table><tr><th>Predictor</th><td>999 synthetic cell</td></tr></table>'+
   '<h3>Research results</h3><h4>H1 hypothetical relationship</h4>'+self.paragraph('OBSERVED_ASSOCIATION')+
   '<h2>Discussion</h2>'+self.paragraph('INTERPRETATION')+
   '<h2>Conclusion</h2><h3>Limitations</h3>'+self.paragraph('LIMITATION')+
   '<h3>Suggestions for further research</h3>'+self.paragraph('FUTURE')+
   '<h2>Statements</h2><h3>Funding</h3>'+self.paragraph('DISCLOSURE')+
   '<h2>Results</h2>'+self.paragraph('AFTER_STOP'))
  (sections,coverage),error=publisher.parse(html,'10.3389/fpsyg.2026.12345',with_coverage=True)
  self.assertIsNone(error)
  self.assertIn('OBSERVED_PATH',sections['results'])
  self.assertIn('OBSERVED_ASSOCIATION',sections['results'])
  self.assertNotIn('hypothetical',sections['results'])
  self.assertNotIn('OBSERVED',sections['methods'])
  self.assertNotIn('INTERPRETATION',sections['results'])
  for marker in ('999','FUTURE','DISCLOSURE','AFTER_STOP'):
   self.assertNotIn(marker,str(sections))
  self.assertEqual(coverage['tables_omitted_by_section'],{'results':1})
  self.assertIn('Methodology > Research results > H1 hypothetical relationship',coverage['encountered_section_headings']['results'])
 def test_unknown_peers_and_previous_results(self):
  html=self.article('<h2>Results</h2>'+self.paragraph('CURRENT')+
   '<h3>Results of previous studies</h3>'+self.paragraph('PRIOR')+
   '<h3>Future research</h3><h4>Results</h4>'+self.paragraph('FUTURE_NESTED')+
   '<h2>Supplementary material</h2>'+self.paragraph('UNSUPPORTED')+
   '<h2>Results and discussion</h2>'+self.paragraph('MIXED'))
  sections,error=publisher.parse(html,'10.3389/fpsyg.2026.12345')
  self.assertIsNone(error)
  self.assertIn('CURRENT',sections['results'])
  self.assertIn('MIXED',sections['discussion'])
  for marker in ('PRIOR','UNSUPPORTED','MIXED','FUTURE_NESTED'):
   self.assertNotIn(marker,sections['results'])
 def test_interpretation_ancestry_does_not_become_observed_results(self):
  html=self.article('<h2>Results</h2>'+self.paragraph('OBSERVED')+
   '<h3>Hypotheses</h3>'+self.paragraph('PROPOSED')+
   '<h2>Discussion</h2><h3>Results</h3>'+self.paragraph('INTERPRETED'))
  sections,error=publisher.parse(html,'10.3389/fpsyg.2026.12345')
  self.assertIsNone(error)
  self.assertIn('INTERPRETED',sections['discussion'])
  self.assertNotIn('INTERPRETED',sections['results'])
  self.assertNotIn('PROPOSED',str(sections))
 def test_cap_is_reported_without_starving_nested_results(self):
  html=self.article('<h2>Methodology</h2>'+self.paragraph('x'*8000)+
   '<h3>Path results</h3>'+self.paragraph('OBSERVED'))
  (sections,coverage),_=publisher.parse(html,'10.3389/fpsyg.2026.12345',with_coverage=True)
  self.assertEqual(len(sections['methods']),6700)
  self.assertIn('OBSERVED',sections['results'])
  self.assertEqual(coverage['truncated_sections'],['methods'])
  self.assertFalse(coverage['full_document'])
 def record(self):
  return {'title':'Synthetic article','kind':'scholarly','doi':'10.3389/fpsyg.2026.12345',
   'analysis':{'provenance':publisher.PUBLISHER_PROVENANCE,'extraction_version':3,
    'methods':'Old methods','results':'','discussion':'Old discussion'},
   'publisher_html_attempt':{'version':1,'status':'full_text','next_at':'2099-01-01'}}
 def test_targeted_migration_preserves_failure_cooldowns(self):
  row=self.record();today=dt.date(2026,11,11)
  self.assertFalse(publisher.eligible(row,today))
  for status in ('publisher_access_denied','license_not_verified','temporary_error','incomplete_reparse'):
   row['publisher_html_attempt']['status']=status
   self.assertFalse(publisher.eligible(row,today))
  row['publisher_html_attempt']['next_at']='2026-11-10'
  self.assertFalse(publisher.eligible(row,today))
  row['analysis']['results']='Previously extracted results'
  self.assertFalse(publisher.eligible(row,today))
  row=self.record();row['analysis']['provenance']='Other source'
  self.assertFalse(publisher.eligible(row,today))
 def test_retained_repair_is_pure_and_targeted(self):
  row=self.record();row['analysis']['fulltext_url']='https://www.frontiersin.org/example'
  before=json.loads(json.dumps(row))
  verification={'doi':row['doi'],'title':row['title'],'license':'cc-by','sha256':hashlib.sha256(ARTICLE.encode()).hexdigest(),'arbitrary_private_field':'must_not_leak'}
  with patch.object(publisher,'fetch_article',side_effect=AssertionError('No network')):
   repaired,error=publisher.reparse_retained_html(row,ARTICLE,dt.date(2026,11,11),source_verification=verification)
   self.assertIsNone(error)
   self.assertEqual(repaired['extraction_version'],4)
   representation=repaired['extraction_coverage']['source_representation']
   self.assertEqual(representation['sha256'],verification['sha256'])
   self.assertEqual(representation['format'],'retained_publisher_html')
   self.assertNotIn('must_not_leak',json.dumps(repaired))
   self.assertIn('less confidence',repaired['results'])
   self.assertEqual(row,before)
   failed,error=publisher.reparse_retained_html(row,'unlicensed source',dt.date(2026,11,11),source_verification=verification)
   self.assertIsNone(failed)
   self.assertEqual(row,before)
 def test_failure_cooldown_survives_attempt_version_change(self):
  row=self.record();del row['analysis']
  for version in (0,1,2):
   row['publisher_html_attempt'].update(version=version,status='publisher_access_denied')
   self.assertFalse(publisher.eligible(row,dt.date(2026,11,11)))
 def test_reparse_failure_keeps_previous_analysis(self):
  row=self.record()
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'library.json';path.write_text(json.dumps([row]))
   html=self.article('<h2>Discussion</h2>'+self.paragraph('Only discussion available'))
   with patch.object(publisher,'eligible',return_value=True),patch.object(publisher,'LIB',path),patch.object(publisher,'fetch_article',return_value=(html,'https://www.frontiersin.org/example')),patch.object(publisher.time,'sleep'),patch.object(publisher,'inspect_wiley_html',return_value={}),patch.object(publisher,'apply_verified_readings',return_value=0),patch('builtins.print'):
    publisher.run()
   actual=json.loads(path.read_text())[0]
   self.assertEqual(actual['analysis'],row['analysis'])
   self.assertEqual(actual['publisher_html_attempt']['status'],'incomplete_reparse')
if __name__=="__main__":unittest.main()

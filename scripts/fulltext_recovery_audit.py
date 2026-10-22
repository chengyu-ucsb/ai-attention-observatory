"""Private operations audit; not part of public site or newsletter."""
import collections
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run():
 data=json.loads((ROOT/"data/library.json").read_text(encoding="utf-8"))
 scholarly=[r for r in data if r.get("kind")=="scholarly"]
 pending=[r for r in scholarly if not r.get("analysis")]
 diagnostics={
  "scholarly_indexed":len(scholarly),
  "with_at_least_some_full_text_sections":len(scholarly)-len(pending),
  "without_full_text_sections":len(pending),
  "without_doi":sum(not r.get("doi") for r in pending),
  "pmc_lookup_statuses":dict(collections.Counter((r.get("pmc_oai_attempt") or {}).get("status","not_tried") for r in pending)),
  "openalex_xml_statuses":dict(collections.Counter((r.get("fulltext_attempt") or {}).get("status","not_tried") for r in pending)),
  "openalex_pdf_statuses":dict(collections.Counter((r.get("pdf_fulltext_attempt") or {}).get("status","not_tried") for r in pending)),
  "fulltext_providers":dict(collections.Counter((r.get("analysis") or {}).get("provenance","") for r in scholarly if r.get("analysis"))),
  "warning":"Full-text sections are automatically extracted, not verified article-level full text reviews."
 }
 print(json.dumps(diagnostics,ensure_ascii=False,indent=2))
 return diagnostics
if __name__=="__main__":run()

"""Compact source-coverage report for GitHub Actions and future audits.

Counts reflect the Observatory's public *indexed subset*, not a comprehensive
literature census. No material from the private indexing backlog is published.
"""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"

def report():
    public=json.loads((DATA/"public-library.json").read_text())
    core=[r for r in public if r.get("source_group")=="AI-specific"]
    scholarly=[r for r in public if r.get("kind")=="scholarly"]
    years=lambda items:dict(sorted(Counter((r.get("published") or "")[:4] for r in items
                         if (r.get("published") or "")[:4].isdigit()).items()))
    group=Counter(r.get("source_group") or "unclassified" for r in public)
    levels=Counter((r.get("reading") or {}).get("level") or "unknown" for r in public)
    fulltext=[r for r in scholarly if (r.get("reading") or {}).get("level")=="full_text"]
    return {
      "public_total":len(public),
      "scholarly":len(scholarly),
      "full_text_extracted":len(fulltext),
      "scholarly_abstract_only":sum((r.get("reading") or {}).get("level")=="abstract" for r in scholarly),
      "full_text_share_of_scholarly":round(100*len(fulltext)/max(1,len(scholarly)),1),
      "source_groups":dict(sorted(group.items())),
      "reading_levels":dict(sorted(levels.items())),
      "ai_specific_by_publication_year":years(core),
      "all_records_by_publication_year":years(public),
      "post_2022_core_records":sum(2023<=int((r.get("published") or "0000")[:4]) for r in core if (r.get("published") or "")[:4].isdigit()),
      "note":"Indexed sample, not annual publication volumes or a systematic review of the field."
    }

if __name__=="__main__":
    print(json.dumps(report(),ensure_ascii=False,indent=2))

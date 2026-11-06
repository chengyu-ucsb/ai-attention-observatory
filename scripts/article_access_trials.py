"""Small public access pilot; no accounts, purchases or raw article persistence."""
from datetime import datetime, timezone
from pathlib import Path
import json
from urllib.error import HTTPError
from full_document_access import (request, fetch_candidate, candidate,
    unpaywall_candidates,core_candidates,semantic_candidates,failure_diagnostic)
from comprehensive_readings import chunk_document,coverage_is_complete

ROOT=Path(__file__).resolve().parents[1]
IDENTIFIERS=['10.1287/isre.2024.1431','10.1080/10494820.2026.2744894']
PORTALS=[
 ('ResearchGate','https://www.researchgate.net/publication/394391422_Knowing_not_to_know_XAI_and_human_metacognition'),
 ('SSRN','https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5383106'),
]
PORTAL_HOSTS={'www.researchgate.net','researchgate.net','papers.ssrn.com','ssrn.com'}


def free_source_pilot():
    """Six bounded live access checks; never generate/publish article summaries."""
    manifest=json.loads((ROOT/'data/free-access-candidates.json').read_text())
    records=manifest['records'][:5]
    targets=[(r,r['fulltext_candidates'][0]) for r in records]
    # An exact, independently identified open-access PMC article exercises the
    # official API path rather than trying to scrape the human article page.
    targets.append(({'title':'Artificial intelligence in language instruction: impact on English learning achievement, L2 motivation, and self-regulated learning',
                     'doi':'10.3389/fpsyg.2023.1261955','kind':'scholarly'},
                    {'url':'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10658009/fullTextXML',
                     'provider':'Europe PMC full-text API','doi':'10.3389/fpsyg.2023.1261955',
                     'version':'repository_article_xml','structured_format':'jats'}))
    rows=[]
    for record,route in targets:
        row={'site':route['provider'],'url':route['url'],'doi':record.get('doi',''),
             'fulltext_retrieved':False,'summary_completed':False,'pilot':'free_source_routes_2026_11_06'}
        try:
            doc=fetch_candidate(route,record)
            chunks=chunk_document(doc)
            complete=doc.coverage.get('evidence_status')=='full_document_retrieved'
            row.update(status='document_text_retrieved_not_reviewed' if complete else 'partial_text_retrieved_not_reviewed',
                       fulltext_retrieved=complete,coverage=doc.manifest(),chunks=len(chunks),
                       all_retrieved_text_retained=coverage_is_complete(doc,chunks))
            del doc,chunks
        except Exception as exc:
            row.update(failure_diagnostic(exc,article=True))
        rows.append(row)
    return rows


def run():
    result={'checked_at':datetime.now(timezone.utc).isoformat(),
      'scope':'Two exact-DOI tests and limited direct public access checks; not corpus-wide recovery.',
      'reddit_thread_verified':False,'source_text_saved':False,'tests':[]}
    for identifier in IDENTIFIERS:
        for name,fn in [('CORE',core_candidates),('Unpaywall',unpaywall_candidates),('Semantic Scholar',semantic_candidates)]:
            row={'site':name,'doi':identifier,'fulltext_retrieved':False}
            try:
                raw=fn(identifier)
                candidates=list({c['url']:c for c in raw}.values())
                row.update(status='locator_responded',exact_match_candidates=len(candidates),
                           candidate_locations=candidates[:8])
            except HTTPError as exc: row['status']='http_'+str(exc.code)
            except Exception as exc: row['status']=type(exc).__name__
            result['tests'].append(row)
    for name,url in PORTALS:
        row={'site':name,'url':url,'fulltext_retrieved':False}
        try:
            raw,final,kind=request(url,PORTAL_HOSTS,2_000_000)
            text=raw.decode('utf-8','replace').lower()
            row.update(status='landing_page_only_not_fulltext',final_url=final)
            if 'no file available' in text or 'request full-text' in text:
                row['status']='request_copy_or_metadata_only'
            if 'captcha' in text or 'access denied' in text:
                row['status']='access_challenge'
            del raw,text
        except HTTPError as exc: row['status']='http_'+str(exc.code)
        except Exception as exc: row['status']=type(exc).__name__
        result['tests'].append(row)
    route=candidate('https://www.econstor.eu/bitstream/10419/334511/1/1947737333.pdf',
                    'EconStor','10.2139/ssrn.5383106','working_paper_not_journal_version')
    row={'site':'EconStor','url':route['url'],'fulltext_retrieved':False}
    try:
        doc=fetch_candidate(route,{'title':'Knowing (Not) to Know: Explainable Artificial Intelligence and Human Metacognition',
                                   'doi':'10.2139/ssrn.5383106','kind':'scholarly'})
        chunks=chunk_document(doc)
        row.update(status='document_text_retrieved_not_reviewed',
                   fulltext_retrieved=doc.coverage.get('evidence_status')=='full_document_retrieved',
                   coverage=doc.manifest(),chunks=len(chunks),
                   all_retrieved_text_retained=coverage_is_complete(doc,chunks))
        del doc,chunks
    except HTTPError as exc: row['status']='http_'+str(exc.code)
    except Exception as exc: row['status']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
    result['tests'].append(row)
    result['scope']='Two exact-DOI locator checks, historical EconStor access, and six bounded official free-source routes; not corpus-wide recovery or summary validation.'
    result['tests'].extend(free_source_pilot())
    (ROOT/'data/fulltext-access-tests.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('ACCESS_TEST_RESULTS_BEGIN')
    print(json.dumps(result,indent=2))
    print('ACCESS_TEST_RESULTS_END')
    return result


if __name__=='__main__': run()


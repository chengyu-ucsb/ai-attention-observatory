"""Verify nominated weekly-brief leads; chat prose is never source evidence."""
import datetime as dt
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote
from priority_research import crossref_article
from update import request, key

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'

def get_atom(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'AttentionAIObservatory/1.1 (contact: fangcu@ucmail.uc.edu)'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read(2_000_000).decode('utf-8')

def verify_arxiv(lead, today, fetch_atom=get_atom):
    match = re.fullmatch(r'https://arxiv\.org/(?:abs|html)/(\d{4}\.\d{4,5})(?:v\d+)?', lead.get('url', ''))
    if not match:
        raise ValueError('Only DOI and canonical arXiv leads support automatic verification')
    identifier = match[1]
    root = ET.fromstring(fetch_atom('https://export.arxiv.org/api/query?id_list=' + identifier))
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    entries = root.findall('a:entry', ns)
    if len(entries) != 1:
        raise ValueError('arXiv record unavailable')
    entry = entries[0]
    source_id = entry.findtext('a:id', '', ns)
    if not re.fullmatch(r'https?://arxiv\.org/abs/' + re.escape(identifier) + r'(?:v\d+)?', source_id):
        raise ValueError('arXiv identifier mismatch')
    title = ' '.join(entry.findtext('a:title', '', ns).split())
    published = entry.findtext('a:published', '', ns)[:10]
    if not same_title(lead['title'], title) or dt.date.fromisoformat(published) > today:
        raise ValueError('arXiv title or publication-date mismatch')
    abstract = ' '.join(entry.findtext('a:summary', '', ns).split())
    return dict(title=title, authors=[a.findtext('a:name', '', ns) for a in entry.findall('a:author', ns)],
        published=published, venue='arXiv', doi='', url='https://arxiv.org/abs/' + identifier,
        abstract_text=abstract, abstract_source='arXiv author-supplied abstract', preview=abstract[:420],
        kind='scholarly', lane=lead['lane'], relation='AI-related literature',
        evidence='Preprint; article screening required', source='Weekly brief lead verified against arXiv',
        curated=False, first_seen=today.isoformat(), discovery_scope='weekly_brief',
        brief_provenance={'origin': lead['origin'], 'week': lead['week']})

def same_title(a, b):
    words = lambda s: set(re.findall(r'[a-z0-9]+', s.casefold()))
    left, right = words(a), words(b)
    return bool(left and right) and len(left & right) / len(left | right) >= .8

def verify(lead, today, fetch=request):
    doi = lead.get('doi', '').lower()
    if not re.fullmatch(r'10\.\d{4,9}/\S+', doi):
        raise ValueError('A DOI is required; non-DOI leads remain in the intake queue')
    work = fetch('https://api.crossref.org/works/' + quote(doi, safe='/')).get('message', {})
    record = crossref_article(work, lane=lead['lane'], scope='weekly_brief',
        query='exact DOI from weekly brief', today=today, editor_seed=True)
    if not record or record['doi'] != doi or not same_title(lead['title'], record['title']):
        raise ValueError('Registry identity mismatch; requires source review')
    record['brief_provenance'] = {'origin': lead['origin'], 'week': lead['week']}
    record['source'] = 'Weekly brief lead verified against Crossref'
    return record

def main():
    leads = json.loads((DATA / 'brief-leads.json').read_text(encoding='utf-8'))
    library = json.loads((DATA / 'library.json').read_text(encoding='utf-8'))
    records = {key(x): x for x in library}
    status = []
    today = dt.datetime.now(dt.timezone.utc).date()
    for lead in leads:
        dt.date.fromisoformat(lead['week'])
        if lead['lane'] not in {'AI & cognition', 'Fragmentation', 'Interventions', 'Technology & society'}:
            raise ValueError('Unsupported brief lane')
        if not lead.get('origin') or not lead.get('title'):
            raise ValueError('Brief leads require title and origin')
        identity = 'doi:' + lead.get('doi', '').lower()
        if not lead.get('doi'):
            identity = next((k for k, r in records.items() if r.get('url') == lead.get('url')), '')
        if identity in records and same_title(lead['title'], records[identity]['title']):
            records[identity]['brief_provenance'] = {'origin': lead['origin'], 'week': lead['week']}
            status.append({**lead, 'status': 'already_indexed'})
            continue
        try:
            if identity in records:
                raise ValueError('Existing record title conflicts with nomination; preserve acquired record for review')
            # Retry provider transport failures, but never relax identity checks.
            for attempt in range(3):
                try:
                    record = verify(lead, today) if lead.get('doi') else verify_arxiv(lead, today)
                    break
                except (OSError, TimeoutError):
                    if attempt == 2:
                        raise
                    time.sleep(3 * (attempt + 1))
            records[key(record)] = record
            status.append({**lead, 'status': 'verified_imported'})
        except Exception as exc:
            state = 'provider_unavailable' if isinstance(exc, (OSError, TimeoutError)) else 'needs_source_review'
            status.append({**lead, 'status': state, 'reason': type(exc).__name__ + ': ' + str(exc)[:180]})
        time.sleep(3)  # arXiv's public API asks for at least three seconds between requests.
    (DATA / 'library.json').write_text(json.dumps(list(records.values()), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (DATA / 'brief-intake-status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending = sum(x['status'] in ('needs_source_review', 'provider_unavailable') for x in status)
    print(json.dumps({'brief_leads': len(status), 'needs_source_review': pending}))
    if pending:
        print('::warning::Weekly brief leads need source review; see data/brief-intake-status.json')

if __name__ == '__main__':
    main()

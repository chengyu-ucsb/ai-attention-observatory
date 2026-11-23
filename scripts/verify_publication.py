"""Verify the actual live manifest, permanent edition and feed after deployment."""
from __future__ import annotations
import argparse
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
from build_reader import encoded
from build_newsletter import ATOM, CONTENT, json_feed, rss_item

BASE='https://chengyu-ucsb.github.io/ai-attention-observatory/'


def fetch(url):
    request=Request(url,headers={'Cache-Control':'no-cache','User-Agent':'ObservatoryPublicationVerifier/1.0'})
    with urlopen(request,timeout=20) as response:return response.read(4_000_000)


def verify(expected,base=BASE,reader=fetch,*,approved_issue=None):
    live=json.loads(reader(urljoin(base,'data/reader-manifest.json')))
    if live.get('edition_id')!=expected.get('edition_id') or live.get('edition_sha256')!=expected.get('edition_sha256') or live.get('index_url')!=expected.get('index_url'):
        raise ValueError('deployed_manifest_mismatch')
    reader_hash = sha256(encoded(live.get('issue', {}))).hexdigest()
    if (reader_hash != live.get('reader_sha256') or reader_hash != expected.get('reader_sha256')):
        raise ValueError('deployed_reader_hash_invalid')
    edition=live.get('edition_id')
    if not edition:raise ValueError('no_published_edition')
    permanent=urljoin(base,'issues/'+edition+'.html')
    html=reader(permanent).decode('utf-8')
    import html as html_tools
    if live['issue'].get('headline','') not in html_tools.unescape(html):
        raise ValueError('permanent_edition_mismatch')
    if '<meta name="observatory-edition-sha256" content="'+live['edition_sha256']+'">' not in html:
        raise ValueError('permanent_edition_hash_mismatch')
    if approved_issue is None:
        archive = Path(__file__).resolve().parents[1] / 'data' / 'approved-issues'
        approved_issue = json.loads((archive / (date.fromisoformat(edition).isoformat()+'.json')).read_text())
    if sha256(encoded(approved_issue)).hexdigest() != live['edition_sha256']:
        raise ValueError('approved_edition_hash_mismatch')

    expected_rss = rss_item(approved_issue)
    feed = ET.fromstring(reader(urljoin(base, 'issue-feed.xml')))
    first = feed.find('./channel/item')
    if first is None or any(first.findtext(key) != expected_rss.findtext(key) for key in ('guid', 'link')):
        raise ValueError('published_feed_entry_missing_or_not_first')
    fields = ('title', 'description', 'pubDate', f'{{{ATOM}}}updated', f'{{{CONTENT}}}encoded')
    if any(first.findtext(key) != expected_rss.findtext(key) for key in fields):
        raise ValueError('published_rss_feed_content_mismatch')

    structured = json.loads(reader(urljoin(base, 'data/issue-feed.json')))
    items = structured.get('items') or []
    expected_json = json_feed([approved_issue])['items'][0]
    if not items or items[0] != expected_json or expected_json['_observatory'] != live['issue']:
        raise ValueError('published_feed_content_mismatch')
    return {'status':'live_verified','edition_id':edition,'permanent_url':permanent,
            'edition_sha256':live['edition_sha256'],
            'publication_window':live['issue'].get('publication_window')}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--base-url',default=BASE)
    args=parser.parse_args();expected=json.loads(args.manifest.read_text())
    for attempt in range(6):
        try:
            print(json.dumps(verify(expected,args.base_url)));return
        except Exception:
            if attempt==5:raise SystemExit('Live publication could not be verified against the deployed artifact.')
            time.sleep(10)


if __name__=='__main__':main()

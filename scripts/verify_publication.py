"""Verify the actual live manifest, permanent edition and feed after deployment."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
from build_reader import encoded

BASE='https://chengyu-ucsb.github.io/ai-attention-observatory/'


def fetch(url):
    request=Request(url,headers={'Cache-Control':'no-cache','User-Agent':'ObservatoryPublicationVerifier/1.0'})
    with urlopen(request,timeout=20) as response:return response.read(4_000_000)


def verify(expected,base=BASE,reader=fetch):
    live=json.loads(reader(urljoin(base,'data/reader-manifest.json')))
    if live.get('edition_id')!=expected.get('edition_id') or live.get('edition_sha256')!=expected.get('edition_sha256') or live.get('index_url')!=expected.get('index_url'):
        raise ValueError('deployed_manifest_mismatch')
    if sha256(encoded(live.get('issue',{}))).hexdigest()!=live.get('edition_sha256'):
        raise ValueError('deployed_edition_hash_invalid')
    edition=live.get('edition_id')
    if not edition:raise ValueError('no_published_edition')
    permanent=urljoin(base,'issues/'+edition+'.html')
    html=reader(permanent).decode('utf-8')
    import html as html_tools
    if live['issue'].get('headline','') not in html_tools.unescape(html):
        raise ValueError('permanent_edition_mismatch')
    if '<meta name="observatory-edition-sha256" content="'+live['edition_sha256']+'">' not in html:
        raise ValueError('permanent_edition_hash_mismatch')
    feed=ET.fromstring(reader(urljoin(base,'issue-feed.xml')))
    if not any(item.findtext('link')==permanent and item.findtext('guid')==permanent
               for item in feed.findall('./channel/item')):
        raise ValueError('published_feed_entry_missing')
    structured=json.loads(reader(urljoin(base,'data/issue-feed.json')))
    item=next((item for item in structured.get('items',[]) if item.get('id')==permanent),None)
    if not item or sha256(encoded(item.get('_observatory',{}))).hexdigest()!=live['edition_sha256']:
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

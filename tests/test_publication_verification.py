from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_reader import encoded
from verify_publication import verify,BASE


class PublicationVerificationTests(unittest.TestCase):
    def setUp(self):
        issue={'edition_date':'2026-11-09','headline':'What changed?','status':'published',
               'publication_window':{'from':'2026-11-02','to':'2026-11-08'}}
        self.manifest={'edition_id':'2026-11-09','issue':issue,'edition_sha256':sha256(encoded(issue)).hexdigest(),'index_url':'data/reader/indexes/a.json'}
        url=BASE+'issues/2026-11-09.html'
        self.pages={BASE+'data/reader-manifest.json':encoded(self.manifest),
                    url:('<meta name="observatory-edition-sha256" content="'+self.manifest['edition_sha256']+'"><h1>What changed?</h1>').encode(),
                    BASE+'issue-feed.xml':('<rss><channel><item><link>'+url+'</link><guid>'+url+'</guid></item></channel></rss>').encode(),
                    BASE+'data/issue-feed.json':encoded({'items':[{'id':url,'_observatory':issue}]})}

    def test_only_matching_live_manifest_permalink_and_feed_are_success(self):
        result=verify(self.manifest,reader=self.pages.__getitem__)
        self.assertEqual(result['status'],'live_verified')
        self.assertEqual(result['edition_id'],'2026-11-09')
        self.pages[BASE+'issue-feed.xml']=b'<rss><channel/></rss>'
        with self.assertRaisesRegex(ValueError,'feed_entry_missing'):verify(self.manifest,reader=self.pages.__getitem__)

    def test_old_deployed_issue_is_not_new_publication_success(self):
        stale=deepcopy(self.manifest);stale['edition_id']='2026-11-07'
        self.pages[BASE+'data/reader-manifest.json']=encoded(stale)
        with self.assertRaisesRegex(ValueError,'manifest_mismatch'):verify(self.manifest,reader=self.pages.__getitem__)

    def test_same_id_with_stale_feed_content_is_not_publication_success(self):
        stale=json.loads(self.pages[BASE+'data/issue-feed.json'])
        stale['items'][0]['_observatory']['headline']='Previous copy'
        self.pages[BASE+'data/issue-feed.json']=encoded(stale)
        with self.assertRaisesRegex(ValueError,'feed_content_mismatch'):verify(self.manifest,reader=self.pages.__getitem__)


if __name__=='__main__':unittest.main()

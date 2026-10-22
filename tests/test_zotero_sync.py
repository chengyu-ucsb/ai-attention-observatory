"""Zotero API access, collection-scoping and privacy regressions."""
import json
import os
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import zotero_sync as sync

K1="ABCDEFGH"
K2="JKLMPQRS"
K3="ZZZZYYYY"
class FakeClient:
 def __init__(self,collections,top=None,children=None,fulltext=None,rights=True,valid=True):
  self.collections=collections
  self.top=top or {}
  self.children=children or {}
  self.fulltext=fulltext or {}
  self.rights=rights;self.valid=valid;self.called=[]
 def request(self,path,params=None):
  self.called.append(path)
  if path=="/keys/current":
   if not self.valid:raise urllib.error.HTTPError("https://api.zotero.org/keys/current",403,"Denied",{},None)
   return {"userID":54321,"access":{"user":{"library":self.rights}}}
  key=path.split("/")[-2] if path.endswith("/fulltext") else None
  if key is not None:return self.fulltext.get(key,{"content":""})
  raise AssertionError("Unexpected Zotero request")
 def pages(self,path,limit=800):
  self.called.append(path)
  if path.endswith("/collections"):return self.collections
  if path.endswith("/children"):return self.children.get(path.split("/")[-2],[])
  if path.endswith("/items/top"):return self.top.get(path.split("/")[-3],[])
  raise AssertionError("Unexpected list endpoint")


def coll(key,name,parent=False):
 return {"key":key,"data":{"name":name,"parentCollection":parent}}
def paper(key,doi):
 return {"key":key,"data":{"key":key,"itemType":"journalArticle","DOI":doi,"title":"Private Zotero record"}}
def pdf(key):
 return {"key":key,"data":{"contentType":"application/pdf","itemType":"attachment"}}

class ZoteroSyncTests(unittest.TestCase):
 def source_file(self,doi):
  tmp=tempfile.TemporaryDirectory()
  path=pathlib.Path(tmp.name)/"library.json"
  path.write_text(json.dumps([{"kind":"scholarly","doi":doi}]))
  self.addCleanup(tmp.cleanup)
  return path
 def test_dois_are_normalized_before_matching(self):
  self.assertEqual(sync.normalized_doi("https://doi.org/10.1000/Foo-BAR."),"10.1000/foo-bar")
  self.assertEqual(sync.normalized_doi("DOI: 10.1145/ABC.123"),"10.1145/abc.123")
  self.assertEqual(sync.normalized_doi("Not a DOI"),"")
 def test_scope_only_named_collection_and_its_descendants(self):
  cols=[coll(K1,"Personal papers"),coll(K2,"AI & Attention Observatory"),coll(K3,"Child",K2)]
  self.assertEqual(sync.collections_scope(cols,"AI & Attention Observatory"),[K2,K3])
  self.assertIsNone(sync.collections_scope(cols,"Unrelated name"))
  self.assertIsNone(sync.collections_scope([coll(K1,"AI & Attention Observatory"),coll(K2,"AI & Attention Observatory")],"AI & Attention Observatory"))
 def test_invalid_key_cannot_read_any_library_items(self):
  client=FakeClient([],valid=False)
  result=sync.run(client,self.source_file("10.1000/abc"))
  self.assertEqual(result["status"],"key_invalid_or_unpermitted")
  self.assertEqual(client.called,["/keys/current"])
 def test_missing_collection_never_falls_back_to_full_library(self):
  client=FakeClient([coll(K1,"Other manuscripts")])
  result=sync.run(client,self.source_file("10.1000/abc"))
  self.assertEqual(result["status"],"collection_missing_or_ambiguous")
  self.assertEqual(client.called,["/keys/current","/users/54321/collections"])
 def test_scoped_matches_scan_only_related_attachment(self):
  collection_items={K2:[paper(K1,"https://doi.org/10.1000/ABC")]}
  client=FakeClient([coll(K2,"AI & Attention Observatory")],top=collection_items,
    children={K1:[pdf(K3)]},fulltext={K3:{"content":"scientific source data "*60}})
  result=sync.run(client,self.source_file("10.1000/abc"))
  self.assertEqual(result["status"],"connected_indexed_fulltext_available")
  self.assertIn("/users/54321/items/"+K3+"/fulltext",client.called)
  self.assertNotIn("content",str(result))
  self.assertNotIn("Private Zotero record",str(result))
 def test_records_not_matching_observatory_are_never_fetched(self):
  client=FakeClient([coll(K2,"AI & Attention Observatory")],top={K2:[paper(K1,"10.2000/private")]})
  result=sync.run(client,self.source_file("10.1000/public"))
  self.assertEqual(result["status"],"connected_no_doi_overlap")
  self.assertFalse(any(x.endswith("/children") for x in client.called))
 def test_unsynced_pdf_returns_precise_status(self):
  client=FakeClient([coll(K2,"AI & Attention Observatory")],top={K2:[paper(K1,"10.1000/abc")]},
    children={K1:[pdf(K3)]},fulltext={K3:{"content":""}})
  self.assertEqual(sync.run(client,self.source_file("10.1000/abc"))["status"],"connected_no_synced_fulltext")
 def test_private_data_is_not_saved_to_public_library(self):
  path=self.source_file("10.1000/abc")
  before=path.read_bytes()
  client=FakeClient([coll(K2,"AI & Attention Observatory")],top={K2:[paper(K1,"10.1000/abc")]},
    children={K1:[pdf(K3)]},fulltext={K3:{"content":"Private licensed article text "*50}})
  sync.run(client,path)
  self.assertEqual(path.read_bytes(),before)
 def test_header_auth_never_in_query_string(self):
  with patch("urllib.request.urlopen") as opener:
   opener.return_value.__enter__.return_value.read.return_value=b'{"userID":54321}'
   sync.ZoteroAPI("secret-test-key").request("/keys/current")
  request=opener.call_args.args[0]
  self.assertNotIn("secret-test-key",request.full_url)
  self.assertEqual(request.get_header("Zotero-api-key"),"secret-test-key")
 def test_collection_empty_is_non_fatal_and_does_not_probe_other_library(self):
  client=FakeClient([coll(K2,"AI & Attention Observatory")])
  self.assertEqual(sync.run(client,self.source_file("10.1000/abc"))["status"],"collection_empty")

if __name__=="__main__":unittest.main()

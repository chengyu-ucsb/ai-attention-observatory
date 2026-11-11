from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import comprehensive_readings as reading
from full_document_access import Document
from reading_progress import ReadingProgress


class MemoryStore:
    def __init__(self):self.rows={}
    def get_checkpoint(self,key):return deepcopy(self.rows.get(key))
    def save_checkpoint(self,key,_id,_hash,_version,_segment,value):self.rows[key]=deepcopy(value)


class ReadingProgressTests(unittest.TestCase):
    def test_failure_resumes_only_remaining_chunks_without_saving_source_quotes(self):
        doc=Document([{'location':'page:1','text':('This source discusses context and limitations of a classroom task. '*100)},
                      {'location':'page:2','text':'The task did not establish learning outside the observed classroom.'}],
                     'https://example.org/paper.pdf')
        store=MemoryStore();progress=ReadingProgress(store,'10.1234/example','test-reader-v1')
        visited=[]
        def accepted(_model,chunk,_kind,_title,deadline=None):
            visited.append(chunk['id'])
            span=reading.source_spans(chunk)[0]
            return [{'field':'limitations','text':'Generalization to other circumstances was not demonstrated by this classroom observation.',
                     'quote':' '.join(span['text'].split())}]
        chunks=reading.chunk_document(doc)
        def failing(*args,**kwargs):
            if args[1]['id']==chunks[1]['id']:raise ValueError('model_json_invalid')
            return accepted(*args,**kwargs)
        with patch.object(reading,'read_chunk',side_effect=failing):
            with self.assertRaisesRegex(ValueError,'model_json_invalid'):
                reading.synthesize(doc,object(),'scholarly','Title',checkpoint=progress)
        self.assertEqual(len(store.rows),1)
        self.assertNotIn('This source discusses',json.dumps(store.rows))
        visited.clear()
        with patch.object(reading,'read_chunk',side_effect=accepted):
            result=reading.synthesize(doc,object(),'scholarly','Title',checkpoint=progress)
        self.assertNotIn(chunks[0]['id'],visited)
        self.assertTrue(result['coverage']['all_retrieved_text_processed'])
        self.assertEqual(result['coverage']['chunks_processed'],len(chunks))
        self.assertIsNone(ReadingProgress(store,'10.1234/example','test-reader-v2').load(doc,chunks[0],'scholarly','Title'))
        self.assertIsNone(progress.load(doc,chunks[0],'scholarly','Changed title'))

    def test_corrupt_checkpoint_fails_closed(self):
        store=MemoryStore();progress=ReadingProgress(store,'example','v1')
        doc=Document([{'location':'page:1','text':'Some exact source text for this test document.'}],'https://example.org/a')
        chunk=reading.chunk_document(doc)[0]
        store.rows[progress.key(doc,chunk,'scholarly','Title')]={'claims':[],'checked':False}
        with self.assertRaisesRegex(ValueError,'invalid_reading_progress'):
            progress.load(doc,chunk,'scholarly','Title')


if __name__=='__main__':unittest.main()

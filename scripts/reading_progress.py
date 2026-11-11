"""Private cloud checkpoints for successfully checked sections.

Source passages are reconstructed from the exact current rendition, never saved
here. A changed source, parser/chunk layout, title, or reader revision has a new
cache key. Partial progress does not make an article publication-eligible.
"""
from hashlib import sha256
from observatory_store import fingerprint
from contextlib import contextmanager
import os
from pathlib import Path


@contextmanager
def cloud_progress(model_path):
    """Use the private OIDC bridge, or an explicitly configured backend DSN."""
    if not (os.getenv('OBSERVATORY_STORE_URL') or os.getenv('OBSERVATORY_DATABASE_URL')):
        yield None
        return
    from observatory_store import connection,Store
    from hashlib import file_digest
    with open(model_path,'rb') as source:
        model_hash=file_digest(source,'sha256').hexdigest()
    scripts=Path(__file__).resolve().parent
    revision=fingerprint({'model_sha256':model_hash,**{
        name:sha256((scripts/name).read_bytes()).hexdigest() for name in
        ('comprehensive_readings.py','full_document_access.py','prepared_reading_schema.py','reading_progress.py')}})
    def factory_for(store):
        def factory(record):
            ident,_=store.put_source(record)
            return ReadingProgress(store,ident,revision)
        return factory
    if os.getenv('OBSERVATORY_STORE_URL'):
        from observatory_remote_store import RemoteStore
        yield factory_for(RemoteStore())
        return
    with connection() as conn:
        # Each successful section survives an interrupted article/run.
        conn.autocommit=True
        store=Store(conn)
        yield factory_for(store)


class ReadingProgress:
    def __init__(self, store, source_id, reader_version):
        if not reader_version or len(reader_version)>200:
            raise ValueError('reader_version_required')
        self.store=store
        self.source_id=source_id
        self.reader_version=reader_version

    def key(self, document, chunk, kind, title):
        return fingerprint({'policy':1,'reader':self.reader_version,
            'source_id':self.source_id,'source_hash':document.manifest()['source_sha256'],
            'document_version':document.manifest()['document_version'],
            'kind':kind,'title':title,'chunk':chunk})

    def load(self, document, chunk, kind, title):
        from comprehensive_readings import source_spans,normalize,validate_claim
        value=self.store.get_checkpoint(self.key(document,chunk,kind,title))
        if value is None:return None
        if set(value)!={'claims','checked'} or value['checked'] is not True:
            raise ValueError('invalid_reading_progress')
        if not isinstance(value['claims'],list) or len(value['claims'])>6:
            raise ValueError('invalid_reading_progress')
        spans={span['id']:span for span in source_spans(chunk)}
        result=[]
        for claim in value['claims']:
            if set(claim)!={'field','text','source_span','anchor_sha256'} or claim['source_span'] not in spans:
                raise ValueError('invalid_reading_progress')
            quote=' '.join(spans[claim['source_span']]['text'].split())
            if sha256(normalize(quote).encode()).hexdigest()!=claim['anchor_sha256']:
                raise ValueError('invalid_reading_progress')
            restored={'field':claim['field'],'text':claim['text'],'quote':quote}
            validate_claim(restored,chunk,kind);result.append(restored)
        return result

    def save(self, document, chunk, kind, title, claims):
        from comprehensive_readings import source_spans,normalize
        spans={normalize(span['text']):span['id'] for span in source_spans(chunk)}
        safe=[]
        for claim in claims:
            anchor=normalize(claim['quote'])
            if anchor not in spans:raise ValueError('progress_anchor_not_in_source')
            safe.append({'field':claim['field'],'text':claim['text'],
                         'source_span':spans[anchor],'anchor_sha256':sha256(anchor.encode()).hexdigest()})
        self.store.save_checkpoint(self.key(document,chunk,kind,title),self.source_id,
            document.manifest()['source_sha256'],self.reader_version,chunk['id'],
            {'claims':safe,'checked':True})

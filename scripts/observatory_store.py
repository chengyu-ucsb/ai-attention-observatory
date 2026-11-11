"""PostgreSQL storage adapter. Never print connection strings or SQL payloads.

The migration can be applied through Supabase's connected SQL tools. This CLI
uses OBSERVATORY_DATABASE_URL for trusted backend operations and has no default
connection or browser credential. No production schedule changes on import.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIELDS = ('doi','url','title','authors','kind','published','venue','lane',
                 'relation','source_group','source_version','research_type')


def fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source_metadata(record):
    result = {key: record[key] for key in SOURCE_FIELDS if key in record}
    provenance = dict(record.get('publication_date_provenance') or {})
    provenance.pop('checked_at', None)
    result['publication_date_provenance'] = provenance
    return result


def source_id(record):
    doi = str(record.get('doi') or '').strip().lower()
    return doi or record.get('url') or ''


@contextmanager
def connection():
    dsn = os.getenv('OBSERVATORY_DATABASE_URL')
    if not dsn:
        raise RuntimeError('database_not_configured')
    import psycopg
    from psycopg.rows import dict_row
    # TLS required for managed connections; never let a URL downgrade it.
    with psycopg.connect(dsn, sslmode='require', connect_timeout=15,
                         prepare_threshold=None, row_factory=dict_row) as conn:
        yield conn


class Store:
    def __init__(self, conn):
        self.conn = conn

    def put_source(self, record):
        ident = source_id(record)
        metadata = source_metadata(record)
        url = ('https://doi.org/' + str(record['doi']).strip()) if record.get('doi') else record.get('url', '')
        if not ident or not url.startswith('https://') or record.get('kind') not in ('scholarly','nonacademic'):
            raise ValueError('invalid_source_identity')
        digest = fingerprint(metadata)
        self.conn.execute('insert into observatory.sources(source_id,kind,canonical_url) values (%s,%s,%s) on conflict do nothing',
                          (ident,record['kind'],url))
        published = str(record.get('published') or '')
        from datetime import date
        try: published = date.fromisoformat(published).isoformat() if len(published)==10 else None
        except ValueError: published = None
        self.conn.execute('insert into observatory.source_versions(source_id,fingerprint,metadata,published_on) values (%s,%s,%s::jsonb,%s) on conflict do nothing',
                          (ident,digest,json.dumps(metadata),published))
        return ident,digest

    def enqueue(self, kind, value, *, lane='current', priority=100):
        key = fingerprint({'kind':kind,'input':value,'lane':lane})
        row = self.conn.execute('insert into observatory.jobs(dedupe_key,kind,input,lane,priority) values (%s,%s,%s::jsonb,%s,%s) on conflict(dedupe_key) do nothing returning id',
                               (key,kind,json.dumps(value),lane,priority)).fetchone()
        return str(row['id']) if row else None

    def claim(self, worker, *, lane='current', batch=1, lease_seconds=1800):
        return self.conn.execute('select * from observatory.claim_jobs(%s,%s,%s,%s)',
                                 (worker,batch,lease_seconds,lane)).fetchall()

    def finish(self, job, result):
        return self.conn.execute('select observatory.finish_job(%s,%s,%s::jsonb) as saved',
                                 (job['id'],job['lease_token'],json.dumps(result))).fetchone()['saved']

    def fail(self, job, category, reason, retry_after=None):
        return self.conn.execute('select observatory.fail_job(%s,%s,%s,%s,%s) as saved',
                                 (job['id'],job['lease_token'],category,reason,retry_after)).fetchone()['saved']

    def get_checkpoint(self, key):
        row = self.conn.execute('select result from observatory.reading_checkpoints where cache_key=%s',(key,)).fetchone()
        return row['result'] if row else None

    def save_checkpoint(self, key, ident, source_hash, version, segment, result):
        self.conn.execute('insert into observatory.reading_checkpoints(cache_key,source_id,source_hash,reader_version,segment_id,result) values (%s,%s,%s,%s,%s,%s::jsonb) on conflict do nothing',
                          (key,ident,source_hash,version,segment,json.dumps(result)))

    def freeze_edition(self, issue):
        if issue.get('status')!='published' or not issue.get('sources'):
            raise ValueError('only_accepted_editions_can_be_imported')
        from build_issue import validate_issue_citations
        from copy import deepcopy
        validate_issue_citations(deepcopy(issue))
        window=issue.get('publication_window') or {}
        start=window.get('from') or issue['edition_date']
        end=window.get('to') or issue['edition_date']
        from build_reader import encoded
        ident=issue['edition_date'];digest=sha256(encoded(issue)).hexdigest()
        existing=self.conn.execute('select snapshot_hash from observatory.editions where edition_id=%s',(ident,)).fetchone()
        if existing and existing['snapshot_hash']!=digest:
            raise ValueError('edition_snapshot_conflict')
        self.conn.execute('insert into observatory.editions(edition_id,window_start,window_end,eligibility_timezone,snapshot_hash,payload) values (%s,%s,%s,%s,%s,%s::jsonb) on conflict do nothing',
                          (ident,start,end,window.get('timezone','UTC'),digest,json.dumps(issue)))
        return ident

    def status(self):
        jobs=self.conn.execute('select lane,state,count(*) as count from observatory.jobs group by lane,state order by lane,state').fetchall()
        return {'jobs':jobs,'sources':self.conn.execute('select count(*) as count from observatory.sources').fetchone()['count'],
                'editions':self.conn.execute('select count(*) as count from observatory.editions').fetchone()['count']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('status','import','enqueue-window'))
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--packet',type=Path)
    args=parser.parse_args()
    try:
        with connection() as conn:
            store=Store(conn)
            if args.action=='import':
                records=json.loads((args.root/'data/library.json').read_text())
                imported=skipped=0
                for record in records:
                    if record.get('kind') not in ('scholarly','nonacademic') or not source_id(record):
                        skipped+=1;continue
                    store.put_source(record);imported+=1
                issues=json.loads((args.root/'data/issue-feed.json').read_text()).get('items',[])
                for item in issues:
                    issue=item.get('_observatory')
                    if issue and issue.get('status')=='published':store.freeze_edition(issue)
                result={'metadata_imported':imported,'skipped':skipped,'source_bodies_imported':False,
                        'publication_verified':False}
            elif args.action=='enqueue-window':
                if not args.packet:raise ValueError('packet_required')
                packet=json.loads(args.packet.read_text())
                from weekly_preparation import validate_packet
                validate_packet(packet)
                queued=0
                for record in packet['items']:
                    ident,digest=store.put_source(record)
                    queued+=bool(store.enqueue('retrieve',{'source_id':ident,'fingerprint':digest,
                        'publication_window':packet['target_publication_window']}))
                result={'queued':queued,'processing_started':False}
            else:result=store.status()
        print(json.dumps(result,default=str))
    except Exception as exc:
        # Exception messages may include hosts, credentials, or source text.
        print(json.dumps({'status':'failed','error_type':type(exc).__name__,
                          'database_configured':bool(os.getenv('OBSERVATORY_DATABASE_URL'))}))
        return 1
    return 0


if __name__=='__main__':sys.exit(main())

/* Execute real PostgreSQL semantics in PGlite; no external account or secrets. */
"use strict";
const fs=require('node:fs'),assert=require('node:assert/strict');
const {PGlite}=require(process.env.PGLITE_MODULE||'@electric-sql/pglite');
(async()=>{
 const db=new PGlite();
 await db.exec('create role anon; create role authenticated;');
 await db.exec(fs.readFileSync('supabase/migrations/202611110001_observatory.sql','utf8'));
 await assert.rejects(db.query("select * from observatory.claim_jobs(null)"),/Invalid claim/);
 const hash='a'.repeat(64),input=JSON.stringify({source_id:'example'});
 await db.query("insert into observatory.jobs(dedupe_key,kind,input,lane,priority) values ('low','retrieve',$1,'current',1),('high','review',$1,'current',20),('history','retrieve',$1,'backfill',999)",[input]);
 const first=(await db.query("select * from observatory.claim_jobs('worker-a',1,1800,'current')")).rows[0];
 assert.equal(first.dedupe_key,'high');
 const second=(await db.query("select * from observatory.claim_jobs('worker-b',1,1800,'current')")).rows[0];
 assert.equal(second.dedupe_key,'low');assert.notEqual(first.id,second.id);
 assert.equal((await db.query("select * from observatory.claim_jobs('worker-c',1,1800,'current')")).rows.length,0);
 assert.equal((await db.query("select observatory.finish_job($1,$2,'{}') as done",[first.id,second.lease_token])).rows[0].done,false);
 await db.query("update observatory.jobs set lease_until=now()-interval '1 second' where id=$1",[first.id]);
 const retry=(await db.query("select * from observatory.claim_jobs('worker-c',1,1800,'current')")).rows[0];
 assert.equal(retry.id,first.id);assert.notEqual(retry.lease_token,first.lease_token);
 assert.equal((await db.query("select observatory.finish_job($1,$2,'{}') as done",[first.id,first.lease_token])).rows[0].done,false);
 assert.equal((await db.query("select observatory.fail_job($1,$2,'format','model_json_invalid') as saved",[retry.id,retry.lease_token])).rows[0].saved,true);
 const format=(await db.query('select state,extract(epoch from available_at-now()) as delay from observatory.jobs where id=$1',[retry.id])).rows[0];
 assert.equal(format.state,'queued');assert(Number(format.delay)>290&&Number(format.delay)<=300);
 await db.query("select observatory.fail_job($1,$2,'semantic','unsupported_claim')",[second.id,second.lease_token]);
 assert.equal((await db.query('select state from observatory.jobs where id=$1',[second.id])).rows[0].state,'held');
 await assert.rejects(db.query("insert into observatory.jobs(dedupe_key,kind,input) values ('low','retrieve','{}')"));
 await db.query("insert into observatory.editions(edition_id,window_start,window_end,snapshot_hash,payload) values ('2026-11-09','2026-11-02','2026-11-08',$1,'{}')",[hash]);
 await assert.rejects(db.query("update observatory.editions set payload='{\"changed\":true}' where edition_id='2026-11-09'"),/Immutable/);
 await assert.rejects(db.query("insert into observatory.publications(edition_id,channel,state,expected_hash,permanent_url) values ('2026-11-09','website','live',$1,'https://example.org/issue')",[hash]));
 await assert.rejects(db.query("insert into observatory.publications(edition_id,channel,state,expected_hash,observed_hash,checked_at,permanent_url) values ('2026-11-09','website','live',$1,$1,now(),'https://example.org/issue')",['b'.repeat(64)]));
 await db.query("insert into observatory.publications(edition_id,channel,state,expected_hash,observed_hash,checked_at,permanent_url) values ('2026-11-09','website','live',$1,$1,now(),'https://example.org/issue')",[hash]);
 for(const role of ['anon','authenticated']){
  await db.exec('set role '+role);
  await assert.rejects(db.query('select * from observatory.jobs'),/permission denied/);
  await db.exec('reset role');
 }
 await db.exec('set role observatory_worker');
 assert((await db.query('select count(*) as n from observatory.jobs')).rows[0].n>0);
 await db.exec('reset role');
 const tables=(await db.query("select count(*) as n from pg_tables where schemaname='observatory' and rowsecurity")).rows[0].n;
 assert.equal(Number(tables),10);
 await db.close();
 console.log('Database verified: current-week isolation, leases, stale-worker fencing, bounded retries, semantic holds, immutable editions and private access.');
})().catch(error=>{console.error(error.message);process.exitCode=1});

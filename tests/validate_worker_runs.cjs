/* Real database behavior: duplicate run requests and stale workers are fenced. */
"use strict";
const fs=require('node:fs'),assert=require('node:assert/strict');
const {PGlite}=require(process.env.PGLITE_MODULE||'@electric-sql/pglite');
(async()=>{
 const db=new PGlite();await db.exec('create role anon; create role authenticated;');
 for(const file of fs.readdirSync('supabase/migrations').filter(f=>f.endsWith('.sql')).sort())
  await db.exec(fs.readFileSync('supabase/migrations/'+file,'utf8'));
 if(process.env.DRAFT_WORKER_SQL)await db.exec(fs.readFileSync(process.env.DRAFT_WORKER_SQL,'utf8'));
 await db.exec('set role observatory_worker');
 const scope='readings:closed:2026-11-02', hash='a'.repeat(64);
 const begin=async(worker,h=hash,s=scope)=>(await db.query('select observatory.begin_worker_run($1,$2,$3,$4) as lease',
  [s,h,worker,'https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/'+worker.split(':')[1]])).rows[0].lease;
 const a=await begin('github:100:1');assert(a.claimed);
 const replay=await begin('github:100:1');assert.equal(replay.lease_token,a.lease_token);
 assert.equal((await begin('github:100:1','b'.repeat(64))).claimed,false);
 assert.equal((await begin('github:200:1','b'.repeat(64))).claimed,false);
 assert((await begin('github:300:1',hash,'readings:preparing:2026-11-09')).claimed);
 await db.query("update observatory.jobs set lease_until=now()-interval '1 second' where id=$1",[a.id]);
 const b=await begin('github:200:1');assert(b.claimed);assert.notEqual(b.lease_token,a.lease_token);
 assert.equal((await db.query("select observatory.finish_job($1,$2,'{}') as saved",[a.id,a.lease_token])).rows[0].saved,false);
 await db.query("select observatory.fail_job($1,$2,'internal','workflow_failed',900)",[b.id,b.lease_token]);
 assert.equal((await begin('github:200:2')).reason,'retry_cooldown');
 await db.query("update observatory.jobs set available_at=now()-interval '1 second' where id=$1",[b.id]);
 const c=await begin('github:200:2');assert(c.claimed);
 assert.equal((await db.query("select observatory.finish_job($1,$2,'{\"completed\":0,\"failed\":2,\"weekly_publication_verified\":false}') as saved",[c.id,c.lease_token])).rows[0].saved,true);
 assert.equal((await begin('github:400:1')).reason,'done');
 assert((await begin('github:400:1','c'.repeat(64))).claimed);
 const budgetScope='readings:closed:2026-10-26';
 for(let i=0;i<6;i++){
  const lease=await begin('github:'+(600+i)+':1',String(i).repeat(64),budgetScope);
  assert(lease.claimed);
  await db.query("select observatory.finish_job($1,$2,'{}')",[lease.id,lease.lease_token]);
 }
 assert.equal((await begin('github:700:1','f'.repeat(64),budgetScope)).reason,'daily_attempt_budget');
 await db.query("update observatory.jobs set updated_at=now()-interval '2 days' where input->>'scope'=$1",[budgetScope]);
 assert((await begin('github:700:1','f'.repeat(64),budgetScope)).claimed);
 await db.exec('reset role;set role anon;');
 await assert.rejects(begin('github:500:1'),/permission denied/);
 await db.close();console.log('Reading runs verified: exclusive scoped leases, duplicate requests, cooldowns, recovery and explicit non-publication outcomes.');
})().catch(error=>{console.error(error.message);process.exitCode=1});

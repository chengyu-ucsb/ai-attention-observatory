-- Scope each bounded reading pass to one live lease. No public API is exposed.
create or replace function observatory.begin_worker_run(scope_key text, inputs_hash text, worker text, run_url text)
returns jsonb language plpgsql set search_path = '' as $$
declare job observatory.jobs; key text;
begin
  if scope_key is null or scope_key !~ '^readings:(preparing|closed):[0-9]{4}-[0-9]{2}-[0-9]{2}$'
     or inputs_hash is null or inputs_hash !~ '^[0-9a-f]{64}$'
     or worker is null or worker !~ '^github:[0-9]+:[0-9]+$'
     or run_url is null or run_url !~ '^https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/[0-9]+$'
  then raise exception 'Invalid worker scope'; end if;
  perform pg_advisory_xact_lock(hashtextextended(scope_key,0));
  update observatory.jobs set state='failed',failure_class='internal',failure_reason='worker_lease_expired',
    lease_token=null,lease_owner=null,lease_until=null,updated_at=now()
    where kind='review' and input->>'scope'=scope_key and state='running' and lease_until<=now();
  select * into job from observatory.jobs where kind='review' and input->>'scope'=scope_key
    and state='running' order by created_at limit 1;
  if found then
    if job.lease_owner=worker and job.input->>'inputs_hash'=inputs_hash then
      return jsonb_build_object('claimed',true,'id',job.id,'lease_token',job.lease_token,'lease_until',job.lease_until,'resumed_request',true);
    end if;
    return jsonb_build_object('claimed',false,'reason','another_worker_running','id',job.id);
  end if;
  -- Conservative daily cap: cumulative attempts on rows updated today are an
  -- upper bound on today's actual starts, including recovery of older jobs.
  if (select coalesce(sum(attempts),0) from observatory.jobs where kind='review'
      and input->>'scope'=scope_key and updated_at >=
      (date_trunc('day',now() at time zone 'America/New_York') at time zone 'America/New_York')) >= 6 then
    return jsonb_build_object('claimed',false,'reason','daily_attempt_budget');
  end if;
  key := scope_key || ':' || inputs_hash;
  insert into observatory.jobs(dedupe_key,kind,input,priority)
    values(key,'review',jsonb_build_object('scope',scope_key,'inputs_hash',inputs_hash),200)
    on conflict do nothing;
  select * into job from observatory.jobs where dedupe_key=key for update;
  if job.state in ('done','held') or job.attempts>=job.max_attempts then
    return jsonb_build_object('claimed',false,'reason',job.state,'id',job.id);
  end if;
  if job.available_at>now() then
    return jsonb_build_object('claimed',false,'reason','retry_cooldown','id',job.id);
  end if;
  update observatory.jobs set state='running',attempts=attempts+1,lease_owner=worker,
    lease_token=gen_random_uuid(),lease_until=now()+interval '110 minutes',updated_at=now(),
    result=jsonb_build_object('active_run_url',run_url,'weekly_publication_verified',false)
    where id=job.id returning * into job;
  return jsonb_build_object('claimed',true,'id',job.id,'lease_token',job.lease_token,'lease_until',job.lease_until,'resumed_request',false);
end $$;
revoke all on function observatory.begin_worker_run(text,text,text,text) from public,anon,authenticated;
grant execute on function observatory.begin_worker_run(text,text,text,text) to observatory_worker;

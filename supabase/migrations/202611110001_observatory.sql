-- Private operational database. Keep observatory OUT of exposed API schemas.
-- No credentials, source bodies, or user content are embedded in this migration.
create schema if not exists observatory;
revoke all on schema observatory from public;
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'observatory_worker') then
    create role observatory_worker nologin;
  end if;
end $$;

create table observatory.sources (
  source_id text primary key,
  kind text not null check (kind in ('scholarly','nonacademic')),
  canonical_url text not null check (canonical_url ~ '^https://'),
  created_at timestamptz not null default now()
);
create table observatory.source_versions (
  source_id text not null references observatory.sources(source_id),
  fingerprint text not null check (fingerprint ~ '^[0-9a-f]{64}$'),
  metadata jsonb not null check (jsonb_typeof(metadata) = 'object'),
  published_on date,
  observed_at timestamptz not null default now(),
  primary key (source_id, fingerprint)
);
create table observatory.retrievals (
  source_id text not null,
  fingerprint text not null,
  source_hash text not null check (source_hash ~ '^[0-9a-f]{64}$'),
  receipt jsonb not null check (jsonb_typeof(receipt) = 'object'),
  private_object_key text,
  retention_basis text,
  created_at timestamptz not null default now(),
  primary key (source_id, fingerprint, source_hash),
  foreign key (source_id,fingerprint) references observatory.source_versions,
  check (private_object_key is null or
    (retention_basis is not null and length(btrim(retention_basis)) > 0))
);
create table observatory.reading_checkpoints (
  cache_key text primary key check (cache_key ~ '^[0-9a-f]{64}$'),
  source_id text not null references observatory.sources,
  source_hash text not null check (source_hash ~ '^[0-9a-f]{64}$'),
  reader_version text not null,
  segment_id text not null,
  result jsonb not null check (jsonb_typeof(result) = 'object'),
  created_at timestamptz not null default now()
);
create table observatory.readings (
  reading_id text primary key check (reading_id ~ '^[0-9a-f]{64}$'),
  source_id text not null,
  fingerprint text not null,
  source_hash text not null check (source_hash ~ '^[0-9a-f]{64}$'),
  review_status text not null check (review_status in
    ('machine_checked_not_independently_reviewed','accepted_original','held')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  created_at timestamptz not null default now(),
  foreign key (source_id,fingerprint) references observatory.source_versions
);
create table observatory.jobs (
  id uuid primary key default gen_random_uuid(),
  dedupe_key text not null unique,
  kind text not null check (kind in ('discover','retrieve','review','synthesize','publish','verify')),
  lane text not null default 'current' check (lane in ('current','backfill')),
  input jsonb not null check (jsonb_typeof(input) = 'object'),
  priority integer not null default 100,
  state text not null default 'queued' check (state in ('queued','running','done','held','failed')),
  attempts integer not null default 0 check (attempts >= 0),
  max_attempts integer not null default 4 check (max_attempts between 1 and 20),
  available_at timestamptz not null default now(),
  lease_owner text,
  lease_token uuid,
  lease_until timestamptz,
  failure_class text check (failure_class in ('format','source_unavailable','rate_limit','semantic','changed_source','internal')),
  failure_reason text,
  result jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((state = 'running' and lease_token is not null and lease_owner is not null and lease_until is not null)
      or (state <> 'running' and lease_token is null and lease_owner is null and lease_until is null))
);
create index jobs_ready on observatory.jobs(lane,priority desc,available_at,created_at)
  where state in ('queued','running');
create table observatory.provider_pauses (
  provider text primary key,
  until_at timestamptz not null,
  reason text not null,
  updated_at timestamptz not null default now()
);
create table observatory.editions (
  edition_id text primary key,
  window_start date not null,
  window_end date not null check (window_end >= window_start),
  eligibility_timezone text not null default 'UTC',
  snapshot_hash text not null check (snapshot_hash ~ '^[0-9a-f]{64}$'),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  frozen_at timestamptz not null default now(),
  unique (edition_id,snapshot_hash)
);
create table observatory.publications (
  edition_id text not null references observatory.editions,
  channel text not null check (channel in ('website','rss','chat','email')),
  state text not null check (state in ('pending','live','failed')),
  expected_hash text not null check (expected_hash ~ '^[0-9a-f]{64}$'),
  observed_hash text,
  permanent_url text not null check (permanent_url ~ '^https://'),
  checked_at timestamptz,
  primary key (edition_id,channel),
  foreign key (edition_id,expected_hash) references observatory.editions(edition_id,snapshot_hash),
  check (state <> 'live' or (observed_hash is not null and observed_hash = expected_hash and checked_at is not null))
);
create table observatory.tool_versions (
  tool_id text not null,
  version text not null,
  evidence_status text not null check (evidence_status in ('demonstration','hypothesis','evaluated')),
  protocol jsonb not null check (jsonb_typeof(protocol) = 'object'),
  source_ids text[] not null default '{}',
  created_at timestamptz not null default now(),
  primary key (tool_id,version)
);

create function observatory.immutable_snapshot() returns trigger language plpgsql
set search_path = '' as $$ begin
  raise exception 'Immutable evidence or edition: insert a new version';
end $$;
create trigger frozen_edition before update or delete on observatory.editions
for each row execute function observatory.immutable_snapshot();
create trigger frozen_source before update or delete on observatory.source_versions
for each row execute function observatory.immutable_snapshot();
create trigger frozen_reading before update or delete on observatory.readings
for each row execute function observatory.immutable_snapshot();

-- Leases fence crashed workers. Retried messages can be delivered again;
-- effect handlers must use dedupe_key/input hashes for idempotency.
create function observatory.claim_jobs(worker text, batch_size integer default 1,
  lease_seconds integer default 1800, selected_lane text default 'current')
returns setof observatory.jobs language plpgsql set search_path = '' as $$
begin
  if worker is null or batch_size is null or lease_seconds is null or selected_lane is null
     or length(worker) not between 1 and 120 or batch_size not between 1 and 20
     or lease_seconds not between 30 and 7200 or selected_lane not in ('current','backfill') then
    raise exception 'Invalid claim parameters';
  end if;
  update observatory.jobs set state='failed', failure_class='internal',
    failure_reason='lease_attempts_exhausted', lease_token=null, lease_owner=null,
    lease_until=null, updated_at=now()
    where lane=selected_lane and attempts>=max_attempts
      and (state='queued' or (state='running' and lease_until<now()));
  return query
    with selected as (
      select j.id from observatory.jobs j
      where j.lane=selected_lane and j.attempts<j.max_attempts
        and ((j.state='queued' and j.available_at<=now()) or (j.state='running' and j.lease_until<now()))
      order by j.priority desc,j.available_at,j.created_at,j.id
      for update skip locked limit batch_size
    )
    update observatory.jobs j set state='running',attempts=j.attempts+1,
      lease_owner=worker,lease_token=gen_random_uuid(),
      lease_until=now()+make_interval(secs=>lease_seconds),updated_at=now()
      from selected where j.id=selected.id returning j.*;
end $$;

create function observatory.finish_job(job_id uuid, token uuid, outcome jsonb)
returns boolean language plpgsql set search_path = '' as $$
declare changed integer;
begin
  update observatory.jobs set state='done',result=outcome,lease_owner=null,
    lease_token=null,lease_until=null,updated_at=now()
    where id=job_id and state='running' and lease_token=token and lease_until>now();
  get diagnostics changed = row_count;
  return changed=1;
end $$;

create function observatory.fail_job(job_id uuid, token uuid, category text,
  reason text, retry_after_seconds integer default null)
returns boolean language plpgsql set search_path = '' as $$
declare changed integer;
begin
  if category is null or reason is null
     or category not in ('format','source_unavailable','rate_limit','semantic','changed_source','internal')
     or length(reason) not between 1 and 200 then raise exception 'Invalid failure'; end if;
  update observatory.jobs set
    state=case when category in ('semantic','changed_source') then 'held'
               when attempts>=max_attempts then 'failed' else 'queued' end,
    available_at=now()+make_interval(secs=>greatest(60,least(172800,coalesce(retry_after_seconds,
      case category when 'format' then 300 when 'rate_limit' then 3600
        when 'source_unavailable' then 21600 else 1800 end)))),
    failure_class=category,failure_reason=reason,
    lease_token=null,lease_owner=null,lease_until=null,updated_at=now()
    where id=job_id and state='running' and lease_token=token and lease_until>now();
  get diagnostics changed = row_count;
  return changed=1;
end $$;

-- Workers are private backend identities. No browser role can read these rows.
do $$ declare item record; begin
  for item in select tablename from pg_tables where schemaname='observatory' loop
    execute format('alter table observatory.%I enable row level security',item.tablename);
    execute format('create policy worker_access on observatory.%I to observatory_worker using (true) with check (true)',item.tablename);
  end loop;
  if exists(select 1 from pg_roles where rolname='anon') then
    revoke all on schema observatory from anon;
    revoke all on all tables in schema observatory from anon;
    revoke all on all functions in schema observatory from anon;
  end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then
    revoke all on schema observatory from authenticated;
    revoke all on all tables in schema observatory from authenticated;
    revoke all on all functions in schema observatory from authenticated;
  end if;
end $$;
revoke all on all tables in schema observatory from public;
revoke all on all functions in schema observatory from public;
grant usage on schema observatory to observatory_worker;
grant select,insert,update on all tables in schema observatory to observatory_worker;
grant execute on all functions in schema observatory to observatory_worker;
alter default privileges in schema observatory revoke execute on functions from public;

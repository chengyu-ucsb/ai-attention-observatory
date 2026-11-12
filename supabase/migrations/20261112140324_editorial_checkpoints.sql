CREATE TABLE observatory.editorial_checkpoints (
 cache_key text PRIMARY KEY CHECK (cache_key ~ '^[0-9a-f]{64}$'),
 revision integer NOT NULL CHECK (revision > 0),
 value jsonb NOT NULL CHECK (jsonb_typeof(value) = 'object' AND value->>'kind' IN ('stage','edition') AND octet_length(value::text) <= 62000),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE observatory.editorial_checkpoints ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON observatory.editorial_checkpoints FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON observatory.editorial_checkpoints TO observatory_worker;
CREATE POLICY editorial_worker ON observatory.editorial_checkpoints TO observatory_worker USING (true) WITH CHECK (true);
COMMENT ON TABLE observatory.editorial_checkpoints IS 'Private input-bound editorial progress and finite attempt budgets. A cached result is not publication approval.';

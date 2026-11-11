-- Allow the platform-owned server connection to drop privileges per transaction.
-- This does not grant browser access, login, superuser, or bypass-RLS rights.
grant observatory_worker to postgres with set true;

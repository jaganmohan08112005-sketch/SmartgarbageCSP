-- ─────────────────────────────────────────────────────────────────────
-- Supabase Row-Level Security (RLS) Policies
-- Defense-in-depth: these policies protect data even if an SQL injection
-- or ORM bypass slips past the application layer.
--
-- Run this in the Supabase SQL Editor after `flask db upgrade`.
-- Safe to re-run (IF NOT EXISTS / CREATE POLICY IF NOT EXISTS).
-- ─────────────────────────────────────────────────────────────────────

-- ═══════════════════════════════════════════════════════════════════
-- USER TABLE
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE "user" ENABLE ROW LEVEL SECURITY;

-- Users can read their own row (dashboard, profile).
-- Admins can read all users (approval workflow).
-- Service role (backend) bypasses RLS, so this only affects
-- direct Supabase client queries (if any are added later).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'user_select_own' AND tablename = 'user') THEN
    CREATE POLICY user_select_own ON "user"
      FOR SELECT USING (
        id = current_setting('app.current_user_id', true)::int
        OR current_setting('app.user_role', true) = 'admin'
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

-- Users can update their own non-privileged fields.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'user_update_own' AND tablename = 'user') THEN
    CREATE POLICY user_update_own ON "user"
      FOR UPDATE USING (
        id = current_setting('app.current_user_id', true)::int
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════
-- COMPLAINT TABLE
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE complaint ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'complaint_select_own' AND tablename = 'complaint') THEN
    CREATE POLICY complaint_select_own ON complaint
      FOR SELECT USING (
        user_id = current_setting('app.current_user_id', true)::int
        OR current_setting('app.user_role', true) = 'admin'
        OR current_setting('app.user_role', true) = 'worker'
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'complaint_insert_auth' AND tablename = 'complaint') THEN
    CREATE POLICY complaint_insert_auth ON complaint
      FOR INSERT WITH CHECK (
        current_setting('app.current_user_id', true) != ''
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════
-- NOTIFICATION TABLE
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE notification ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'notification_select_own' AND tablename = 'notification') THEN
    CREATE POLICY notification_select_own ON notification
      FOR SELECT USING (
        user_id = current_setting('app.current_user_id', true)::int
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════
-- WASTE_DECLARATION TABLE
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE waste_declaration ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'waste_decl_select_own' AND tablename = 'waste_declaration') THEN
    CREATE POLICY waste_decl_select_own ON waste_declaration
      FOR SELECT USING (
        user_id = current_setting('app.current_user_id', true)::int
        OR current_setting('app.user_role', true) = 'admin'
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'waste_decl_insert_own' AND tablename = 'waste_declaration') THEN
    CREATE POLICY waste_decl_insert_own ON waste_declaration
      FOR INSERT WITH CHECK (
        user_id = current_setting('app.current_user_id', true)::int
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════
-- PAYT_INVOICE TABLE
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE payt_invoice ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'payt_select_own' AND tablename = 'payt_invoice') THEN
    CREATE POLICY payt_select_own ON payt_invoice
      FOR SELECT USING (
        user_id = current_setting('app.current_user_id', true)::int
        OR current_setting('app.user_role', true) = 'admin'
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════
-- WORKER_PROFILE TABLE
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE worker_profile ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'worker_select_own' AND tablename = 'worker_profile') THEN
    CREATE POLICY worker_select_own ON worker_profile
      FOR SELECT USING (
        user_id = current_setting('app.current_user_id', true)::int
        OR current_setting('app.user_role', true) = 'admin'
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════
-- AUDIT_LOG TABLE (admin-only reads)
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'audit_select_admin' AND tablename = 'audit_log') THEN
    CREATE POLICY audit_select_admin ON audit_log
      FOR SELECT USING (
        current_setting('app.user_role', true) = 'admin'
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════
-- CONSENT_RECORD TABLE (append-only, admin reads)
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE consent_record ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'consent_insert_anon' AND tablename = 'consent_record') THEN
    CREATE POLICY consent_insert_anon ON consent_record
      FOR INSERT WITH CHECK (true);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'consent_select_admin' AND tablename = 'consent_record') THEN
    CREATE POLICY consent_select_admin ON consent_record
      FOR SELECT USING (
        current_setting('app.user_role', true) = 'admin'
        OR current_setting('role') = 'supabase_admin'
      );
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════════
-- NOTE: smart_bin, device, schedule, incident_log, sensor_health,
-- dispatch_assignment, firmware_release, and illegal_dump_report are
-- admin/worker operational tables. The Flask backend (service role)
-- handles all access. RLS is enabled as a safety net but the policies
-- are permissive for service-role callers.
-- ═══════════════════════════════════════════════════════════════════
ALTER TABLE smart_bin ENABLE ROW LEVEL SECURITY;
ALTER TABLE device ENABLE ROW LEVEL SECURITY;
ALTER TABLE schedule ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE sensor_health ENABLE ROW LEVEL SECURITY;
ALTER TABLE dispatch_assignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE firmware_release ENABLE ROW LEVEL SECURITY;
ALTER TABLE illegal_dump_report ENABLE ROW LEVEL SECURITY;

-- These operational tables are service-role-only (Flask backend).
-- Allow full access for the service role; block direct anon/authenticated
-- client access so no citizen can accidentally query operational data.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ops_service_only' AND tablename = 'smart_bin') THEN
    CREATE POLICY ops_service_only ON smart_bin
      FOR ALL USING (current_setting('role') = 'supabase_admin');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ops_service_only' AND tablename = 'device') THEN
    CREATE POLICY ops_service_only ON device
      FOR ALL USING (current_setting('role') = 'supabase_admin');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ops_service_only' AND tablename = 'schedule') THEN
    CREATE POLICY ops_service_only ON schedule
      FOR ALL USING (current_setting('role') = 'supabase_admin');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ops_service_only' AND tablename = 'incident_log') THEN
    CREATE POLICY ops_service_only ON incident_log
      FOR ALL USING (current_setting('role') = 'supabase_admin');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ops_service_only' AND tablename = 'sensor_health') THEN
    CREATE POLICY ops_service_only ON sensor_health
      FOR ALL USING (current_setting('role') = 'supabase_admin');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ops_service_only' AND tablename = 'dispatch_assignment') THEN
    CREATE POLICY ops_service_only ON dispatch_assignment
      FOR ALL USING (current_setting('role') = 'supabase_admin');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ops_service_only' AND tablename = 'firmware_release') THEN
    CREATE POLICY ops_service_only ON firmware_release
      FOR ALL USING (current_setting('role') = 'supabase_admin');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'ops_service_only' AND tablename = 'illegal_dump_report') THEN
    CREATE POLICY ops_service_only ON illegal_dump_report
      FOR ALL USING (current_setting('role') = 'supabase_admin');
  END IF;
END $$;

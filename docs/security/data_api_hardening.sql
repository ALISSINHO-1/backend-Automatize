-- REVIEW/INTEGRATION ARTIFACT. Not executed by startup, tests or Alembic.
-- RLS is already implemented by origin/HML:7b2d4e6f8a10, which depends on
-- 3c9e7a1b5d20. Reuse that original chain in the separately approved item 5.
-- This permission-only supplement MUST NOT recreate or enable RLS itself.
-- After integrating the original chain, review a descendant migration for
-- these REVOKEs only if its grants are still excessive. Do not apply now.
-- Run with the same SQL role used by FastAPI (DATABASE_URL); no credentials here.
-- This project accesses public domain tables via SQLAlchemy, not the Data API.
BEGIN;

DO $preflight$
DECLARE table_name text;
BEGIN
    IF current_user IN ('anon', 'authenticated', 'service_role') THEN
        RAISE EXCEPTION 'Use the reviewed FastAPI SQL role for this deployment.';
    END IF;
    FOREACH table_name IN ARRAY ARRAY['users','pedidos','ocorrencias','anexos','aceites_formais','auditoria_logs','historico_status_pedidos','etapas_operacionais','alembic_version'] LOOP
        IF to_regclass(format('public.%I', table_name)) IS NULL THEN
            RAISE EXCEPTION 'Missing domain table; integrate the original migrations first.';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname=table_name AND c.relrowsecurity
        ) THEN
            RAISE EXCEPTION 'RLS prerequisite absent: integrate the original 7b2d4e6f8a10 chain in item 5 first.';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_roles r ON r.rolname=current_user
            WHERE n.nspname='public' AND c.relname=table_name
              AND (r.rolsuper OR r.rolbypassrls OR (c.relowner=r.oid AND NOT c.relforcerowsecurity))
              AND has_table_privilege(c.oid,'SELECT') AND has_table_privilege(c.oid,'INSERT')
              AND has_table_privilege(c.oid,'UPDATE') AND has_table_privilege(c.oid,'DELETE')
        ) THEN
            RAISE EXCEPTION 'Backend privileges/RLS need review before deployment.';
        END IF;
    END LOOP;
    -- Existing views/RPCs must be reviewed separately; do not silently assume
    -- table REVOKEs make a definer view or SECURITY DEFINER RPC safe.
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('v','m')
          AND (has_table_privilege('anon',c.oid,'SELECT') OR has_table_privilege('authenticated',c.oid,'SELECT'))
    ) OR EXISTS (
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.prosecdef
          AND (has_function_privilege('anon',p.oid,'EXECUTE') OR has_function_privilege('authenticated',p.oid,'EXECUTE'))
    ) THEN
        RAISE EXCEPTION 'Review public views/SECURITY DEFINER functions before applying this plan.';
    END IF;
END;
$preflight$;

REVOKE SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE
    public.users, public.pedidos, public.ocorrencias, public.anexos,
    public.aceites_formais, public.auditoria_logs,
    public.historico_status_pedidos, public.etapas_operacionais, public.alembic_version
FROM anon, authenticated, PUBLIC;

-- Table REVOKEs do not revoke independent column grants.
DO $columns$
DECLARE col record;
BEGIN
    FOR col IN
        SELECT c.relname, a.attname FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid
        WHERE n.nspname='public' AND c.relname IN
            ('users','pedidos','ocorrencias','anexos','aceites_formais','auditoria_logs','historico_status_pedidos','etapas_operacionais','alembic_version')
          AND a.attnum>0 AND NOT a.attisdropped
    LOOP
        EXECUTE format('REVOKE SELECT (%I), INSERT (%I), UPDATE (%I), REFERENCES (%I) ON TABLE public.%I FROM anon, authenticated, PUBLIC',
            col.attname,col.attname,col.attname,col.attname,col.relname);
    END LOOP;
END;
$columns$;

-- No privileges or policies are changed in storage/auth schemas. Existing
-- service_role table privileges are preserved, not expanded.
DO $verify$
DECLARE tbl record; role_name text;
BEGIN
    FOR tbl IN SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname IN
          ('users','pedidos','ocorrencias','anexos','aceites_formais','auditoria_logs','historico_status_pedidos','etapas_operacionais','alembic_version')
    LOOP
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
            IF has_table_privilege(role_name,tbl.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               OR has_any_column_privilege(role_name,tbl.oid,'SELECT,INSERT,UPDATE,REFERENCES') THEN
                RAISE EXCEPTION 'Inherited client grants remain; review membership without removing other roles blindly.';
            END IF;
        END LOOP;
        -- Check each required privilege; comma lists mean ANY, not ALL.
        IF NOT (has_table_privilege(tbl.oid,'SELECT') AND has_table_privilege(tbl.oid,'INSERT')
                AND has_table_privilege(tbl.oid,'UPDATE') AND has_table_privilege(tbl.oid,'DELETE')) THEN
            RAISE EXCEPTION 'Backend privileges changed; transaction must be rolled back.';
        END IF;
        IF NOT (has_table_privilege('service_role',tbl.oid,'SELECT') AND has_table_privilege('service_role',tbl.oid,'INSERT')
                AND has_table_privilege('service_role',tbl.oid,'UPDATE') AND has_table_privilege('service_role',tbl.oid,'DELETE')) THEN
            RAISE EXCEPTION 'service_role privileges need explicit review; do not expand them automatically.';
        END IF;
    END LOOP;
END;
$verify$;
COMMIT;

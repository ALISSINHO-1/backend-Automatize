"""Fix trigger search paths and close direct domain Data API grants.

Revision ID: 9d4f2a6c8e11
Revises: 7b2d4e6f8a10

Domain access uses FastAPI/SQLAlchemy. Storage permissions are intentionally
outside this migration. No FORCE RLS: the existing SQL backend is an owner or
BYPASSRLS role. Deployment with a different role requires a separate review.
"""
from alembic import op

revision = "9d4f2a6c8e11"
down_revision = "7b2d4e6f8a10"
branch_labels = None
depends_on = None

TABLES = (
    "users", "pedidos", "ocorrencias", "anexos", "aceites_formais",
    "auditoria_logs", "historico_status_pedidos", "etapas_operacionais",
    "alembic_version",
)


def upgrade():
    # CREATE OR REPLACE preserves ownership and trigger dependencies. Business
    # conditions/messages/SQLSTATE are identical to 3c9e7a1b5d20.
    op.execute("""
        CREATE OR REPLACE FUNCTION public.bloquear_alteracao_aceite_formal()
        RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
        SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
            RAISE EXCEPTION 'O aceite formal e imutavel e nao pode ser alterado nem excluido.'
                USING ERRCODE = 'restrict_violation';
        END;
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION public.proteger_conclusao_pedido()
        RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
        SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.status = 'CONCLUIDO' THEN
                RAISE EXCEPTION 'Demandas CONCLUIDAS sao imutaveis.'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            IF NEW.status = 'CONCLUIDO' AND NOT EXISTS (
                SELECT 1 FROM public.aceites_formais WHERE pedido_id = NEW.id
            ) THEN
                RAISE EXCEPTION 'A conclusao exige aceite formal do cliente.'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    # Trigger execution does not need a client's EXECUTE privilege. Do not
    # expand service_role or replace arbitrary application policies.
    for function in ("bloquear_alteracao_aceite_formal", "proteger_conclusao_pedido"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{function}() FROM PUBLIC")
    for table in TABLES:
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC")
        op.execute(f"""
            DO $public_columns$ DECLARE col record;
            BEGIN
                FOR col IN SELECT attname FROM pg_attribute
                    WHERE attrelid='public.{table}'::regclass AND attnum>0 AND NOT attisdropped
                LOOP
                    EXECUTE format(
                        'REVOKE SELECT (%I), INSERT (%I), UPDATE (%I), REFERENCES (%I) ON TABLE public.{table} FROM PUBLIC',
                        col.attname,col.attname,col.attname,col.attname);
                END LOOP;
            END $public_columns$
        """)
    op.execute("""
        DO $permissions$
        DECLARE role_name text; table_name text; col record;
        BEGIN
            IF current_user IN ('anon','authenticated','service_role') THEN
                RAISE EXCEPTION 'Use a reviewed backend migration role.';
            END IF;
            FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
                    FOREACH table_name IN ARRAY ARRAY[
                        'users','pedidos','ocorrencias','anexos','aceites_formais',
                        'auditoria_logs','historico_status_pedidos','etapas_operacionais','alembic_version'
                    ] LOOP
                        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I', table_name, role_name);
                        -- Column grants are independent from table grants.
                        FOR col IN SELECT attname FROM pg_attribute
                            WHERE attrelid=format('public.%I',table_name)::regclass
                                AND attnum>0 AND NOT attisdropped
                        LOOP
                            EXECUTE format(
                                'REVOKE SELECT (%I), INSERT (%I), UPDATE (%I), REFERENCES (%I) ON TABLE public.%I FROM %I, PUBLIC',
                                col.attname,col.attname,col.attname,col.attname,table_name,role_name);
                        END LOOP;
                        IF has_table_privilege(role_name,format('public.%I',table_name),'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                            OR has_any_column_privilege(role_name,format('public.%I',table_name),'SELECT,INSERT,UPDATE,REFERENCES') THEN
                            RAISE EXCEPTION 'Inherited domain privileges require manual role review.';
                        END IF;
                    END LOOP;
                    EXECUTE format('REVOKE ALL ON FUNCTION public.bloquear_alteracao_aceite_formal() FROM %I',role_name);
                    EXECUTE format('REVOKE ALL ON FUNCTION public.proteger_conclusao_pedido() FROM %I',role_name);
                END IF;
            END LOOP;
        END;
        $permissions$
    """)


def downgrade():
    # Previous grants are deployment-specific. Never silently reopen access or
    # restore an unsafe search_path. Rollback needs an explicitly reviewed plan.
    raise RuntimeError("Security hardening cannot be downgraded automatically.")

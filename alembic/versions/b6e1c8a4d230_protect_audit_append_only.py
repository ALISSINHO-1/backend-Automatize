"""Protect audit payloads while preserving existing FK SET NULL semantics.

Revision ID: b6e1c8a4d230
Revises: 9d4f2a6c8e11
"""
from alembic import op

revision = "b6e1c8a4d230"
down_revision = "9d4f2a6c8e11"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION public.proteger_auditoria_log() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER
        SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
            IF TG_OP = 'UPDATE' AND pg_trigger_depth() > 1
                AND ROW(NEW.id,NEW.acao,NEW.detalhes,NEW.created_at)
                    IS NOT DISTINCT FROM ROW(OLD.id,OLD.acao,OLD.detalhes,OLD.created_at)
                AND (NEW.pedido_id IS NOT DISTINCT FROM OLD.pedido_id OR
                    (NEW.pedido_id IS NULL AND OLD.pedido_id IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM public.pedidos WHERE id=OLD.pedido_id)))
                AND (NEW.usuario_id IS NOT DISTINCT FROM OLD.usuario_id OR
                    (NEW.usuario_id IS NULL AND OLD.usuario_id IS NOT NULL
                        AND NOT EXISTS (SELECT 1 FROM public.users WHERE id=OLD.usuario_id)))
            THEN
                -- Only nested FK actions may detach a deleted parent. The
                -- payload, actor evidence in details and timestamp survive.
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Logs de auditoria sao imutaveis.'
                USING ERRCODE = 'restrict_violation';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_auditoria_logs_imutavel
        BEFORE UPDATE OR DELETE ON public.auditoria_logs
        FOR EACH ROW EXECUTE FUNCTION public.proteger_auditoria_log()
    """)
    op.execute("REVOKE ALL ON FUNCTION public.proteger_auditoria_log() FROM PUBLIC")
    op.execute("""
        DO $$ DECLARE role_name text;
        BEGIN
            FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
                    EXECUTE format('REVOKE ALL ON FUNCTION public.proteger_auditoria_log() FROM %I',role_name);
                END IF;
            END LOOP;
        END $$
    """)


def downgrade():
    raise RuntimeError("Audit evidence protection cannot be downgraded automatically.")

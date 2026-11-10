"""Bind formal acceptance to the demand owner without rewriting published DDL.

Revision ID: d1f6a8c20391
Revises: 84db17ce9f26
"""
from alembic import op


revision = "d1f6a8c20391"
down_revision = "84db17ce9f26"
branch_labels = None
depends_on = None


def upgrade():
    # Transactional DDL serializes validation with writers. Never repair or
    # remove an immutable legacy acceptance to make this migration succeed.
    op.execute("LOCK TABLE public.pedidos, public.aceites_formais IN SHARE ROW EXCLUSIVE MODE")
    op.execute("""
        DO $acceptance_preflight$ BEGIN
            IF EXISTS (
                SELECT 1 FROM public.aceites_formais a
                JOIN public.pedidos p ON p.id=a.pedido_id
                WHERE a.cliente_id<>p.cliente_id
                    OR NOT (a.versao_entregavel ~ '[^[:space:]]'
                        AND a.declaracao_aceite ~ '[^[:space:]]'
                        AND a.hash_validacao ~ '[^[:space:]]')
            ) THEN
                RAISE EXCEPTION 'Review legacy acceptance ownership/content before migration.'
                    USING ERRCODE='check_violation';
            END IF;
        END $acceptance_preflight$
    """)
    op.create_unique_constraint("uq_pedidos_id_cliente_id", "pedidos", ["id", "cliente_id"], schema="public")
    op.create_foreign_key(
        "fk_aceites_formais_pedido_cliente", "aceites_formais", "pedidos",
        ["pedido_id", "cliente_id"], ["id", "cliente_id"],
        source_schema="public", referent_schema="public",
    )
    op.create_check_constraint(
        "ck_aceites_formais_conteudo", "aceites_formais",
        "versao_entregavel ~ '[^[:space:]]' AND declaracao_aceite ~ '[^[:space:]]' "
        "AND hash_validacao ~ '[^[:space:]]'", schema="public",
    )


def downgrade():
    raise RuntimeError("Acceptance integrity requires a reviewed rollback/retention plan.")

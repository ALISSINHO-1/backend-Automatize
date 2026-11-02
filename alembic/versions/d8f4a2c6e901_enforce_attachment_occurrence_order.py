"""Enforce the attachment/occurrence order relationship without changing deletes.

Revision ID: d8f4a2c6e901
Revises: b6e1c8a4d230
"""
from alembic import op

revision = "d8f4a2c6e901"
down_revision = "b6e1c8a4d230"
branch_labels = None
depends_on = None


def upgrade():
    # Do not silently repair, delete or expose inconsistent legacy records.
    # This also compiles in Alembic's offline mode.
    op.execute("""
        DO $attachment_preflight$ BEGIN
            IF EXISTS (
                SELECT 1 FROM public.anexos a
                JOIN public.ocorrencias o ON o.id=a.ocorrencia_id
                WHERE a.pedido_id<>o.pedido_id
            ) THEN
                RAISE EXCEPTION 'Attachment/occurrence order mismatch; review legacy data before migration.'
                    USING ERRCODE='check_violation';
            END IF;
        END $attachment_preflight$
    """)
    op.create_unique_constraint("uq_ocorrencias_id_pedido_id", "ocorrencias", ["id", "pedido_id"], schema="public")
    op.create_foreign_key(
        "fk_anexos_ocorrencia_pedido", "anexos", "ocorrencias",
        ["ocorrencia_id", "pedido_id"], ["id", "pedido_id"],
        source_schema="public", referent_schema="public", deferrable=True, initially="DEFERRED",
    )
    # Existing pedido CASCADE and ocorrencia SET NULL FKs remain unchanged.


def downgrade():
    raise RuntimeError("Attachment integrity hardening requires a reviewed rollback plan.")

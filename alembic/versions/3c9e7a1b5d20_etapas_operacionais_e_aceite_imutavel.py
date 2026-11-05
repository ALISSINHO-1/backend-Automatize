"""etapas operacionais e imutabilidade do aceite formal

Revision ID: 3c9e7a1b5d20
Revises: fd3fe1dcfeab

- SCRUM-71: tabela de etapas operacionais (checklist que bloqueia a homologacao).
- SCRUM-72: um aceite por pedido; triggers impedem UPDATE/DELETE do aceite,
  qualquer alteracao de pedido CONCLUIDO e a conclusao sem aceite formal.
  As triggers valem para qualquer cliente do banco, nao so para a API.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa # type: ignore
from sqlalchemy.dialects import postgresql # type: ignore


revision: str = "3c9e7a1b5d20"
down_revision: Union[str, Sequence[str], None] = "fd3fe1dcfeab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "etapas_operacionais",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pedido_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("descricao", sa.String(length=255), nullable=False),
        sa.Column("concluida", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("concluida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluida_por_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("criado_por_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            "(concluida AND concluida_em IS NOT NULL AND concluida_por_id IS NOT NULL)"
            " OR (NOT concluida AND concluida_em IS NULL AND concluida_por_id IS NULL)",
            name="etapas_operacionais_conclusao_check",
        ),
        sa.ForeignKeyConstraint(["pedido_id"], ["pedidos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concluida_por_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["criado_por_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_etapas_operacionais_pedido_id", "etapas_operacionais", ["pedido_id"], unique=False)

    # Falha se ja houver mais de um aceite para o mesmo pedido: nesse caso os
    # registros duplicados precisam ser analisados antes da migracao.
    op.create_unique_constraint("uq_aceites_formais_pedido_id", "aceites_formais", ["pedido_id"])

    op.execute("""
        CREATE FUNCTION bloquear_alteracao_aceite_formal() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'O aceite formal e imutavel e nao pode ser alterado nem excluido.'
                USING ERRCODE = 'restrict_violation';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_aceites_formais_imutavel
        BEFORE UPDATE OR DELETE ON aceites_formais
        FOR EACH ROW EXECUTE FUNCTION bloquear_alteracao_aceite_formal()
    """)

    op.execute("""
        CREATE FUNCTION proteger_conclusao_pedido() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.status = 'CONCLUIDO' THEN
                RAISE EXCEPTION 'Demandas CONCLUIDAS sao imutaveis.'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            IF NEW.status = 'CONCLUIDO' AND NOT EXISTS (
                SELECT 1 FROM aceites_formais WHERE pedido_id = NEW.id
            ) THEN
                RAISE EXCEPTION 'A conclusao exige aceite formal do cliente.'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_pedidos_protege_conclusao
        BEFORE INSERT OR UPDATE OR DELETE ON pedidos
        FOR EACH ROW EXECUTE FUNCTION proteger_conclusao_pedido()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_pedidos_protege_conclusao ON pedidos")
    op.execute("DROP FUNCTION IF EXISTS proteger_conclusao_pedido()")
    op.execute("DROP TRIGGER IF EXISTS trg_aceites_formais_imutavel ON aceites_formais")
    op.execute("DROP FUNCTION IF EXISTS bloquear_alteracao_aceite_formal()")
    op.drop_constraint("uq_aceites_formais_pedido_id", "aceites_formais", type_="unique")
    op.drop_index("ix_etapas_operacionais_pedido_id", table_name="etapas_operacionais")
    op.drop_table("etapas_operacionais")

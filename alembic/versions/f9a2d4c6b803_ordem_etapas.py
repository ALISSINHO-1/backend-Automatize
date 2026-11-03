"""Adiciona ordem explicita preservando a sequencia existente das etapas.

Revision ID: f9a2d4c6b803
Revises: e3b7c1d9f402
"""
import sqlalchemy as sa
from alembic import op

revision = "f9a2d4c6b803"
down_revision = "e3b7c1d9f402"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("etapas_operacionais", sa.Column("ordem", sa.Integer(), nullable=True))
    op.execute("""
        WITH sequencia AS (
            SELECT id, row_number() OVER (PARTITION BY pedido_id ORDER BY created_at, id) AS posicao
            FROM etapas_operacionais
        )
        UPDATE etapas_operacionais e SET ordem=s.posicao FROM sequencia s WHERE e.id=s.id
    """)
    op.alter_column("etapas_operacionais", "ordem", nullable=False, server_default=sa.text("1"))
    op.create_check_constraint("ck_etapas_ordem_positiva", "etapas_operacionais", "ordem >= 1")


def downgrade():
    op.drop_constraint("ck_etapas_ordem_positiva", "etapas_operacionais", type_="check")
    op.drop_column("etapas_operacionais", "ordem")

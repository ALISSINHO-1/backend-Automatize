"""Registra a resolucao das ocorrencias (SCRUM-98).

Ocorrencias existentes ficam em aberto (campos nulos), o que e o estado
correto: nenhuma delas teve correcao registrada ate aqui.

Revision ID: e3b7c1d9f402
Revises: d8f4a2c6e901
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e3b7c1d9f402"
down_revision = "d8f4a2c6e901"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ocorrencias", sa.Column("resolvida_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ocorrencias", sa.Column("resolvida_por_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ocorrencias", sa.Column("descricao_resolucao", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_ocorrencias_resolvida_por_id_users", "ocorrencias", "users",
        ["resolvida_por_id"], ["id"],
    )
    op.create_check_constraint(
        "ck_ocorrencias_resolucao_completa", "ocorrencias",
        "(resolvida_em IS NULL) = (resolvida_por_id IS NULL) "
        "AND (resolvida_em IS NULL) = (descricao_resolucao IS NULL)",
    )


def downgrade():
    op.drop_constraint("ck_ocorrencias_resolucao_completa", "ocorrencias", type_="check")
    op.drop_constraint("fk_ocorrencias_resolvida_por_id_users", "ocorrencias", type_="foreignkey")
    op.drop_column("ocorrencias", "descricao_resolucao")
    op.drop_column("ocorrencias", "resolvida_por_id")
    op.drop_column("ocorrencias", "resolvida_em")

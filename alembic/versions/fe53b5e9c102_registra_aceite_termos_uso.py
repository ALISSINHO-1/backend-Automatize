"""Registra a versão e o momento do aceite dos Termos de Uso no cadastro."""

import sqlalchemy as sa
from alembic import op

revision = "fe53b5e9c102"
down_revision = "de24ab6719c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("termos_uso_versao", sa.String(32), nullable=True))
    op.add_column(
        "users", sa.Column("termos_uso_aceitos_em", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "termos_uso_aceitos_em")
    op.drop_column("users", "termos_uso_versao")

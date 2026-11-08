"""Adiciona a previsão opcional de entrega à demanda."""

import sqlalchemy as sa
from alembic import op

revision = "51cb39a0d826"
down_revision = "2a6d14c839ef"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pedidos", sa.Column("data_previsao", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("pedidos", "data_previsao")

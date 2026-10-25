"""create historico status pedidos

Revision ID: fd3fe1dcfeab
Revises: a4fa37701385
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa # type: ignore


# revision identifiers, used by Alembic.
revision: str = "fd3fe1dcfeab"
down_revision: Union[str, Sequence[str], None] = "a4fa37701385"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # enum_status JÁ EXISTE no PostgreSQL.
    # Aqui referenciamos o tipo existente diretamente para impedir
    # SQLAlchemy/Alembic de tentar executar CREATE TYPE novamente.

    op.execute("""
        CREATE TABLE historico_status_pedidos (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

            pedido_id UUID NOT NULL,

            status_anterior enum_status NOT NULL,
            status_novo enum_status NOT NULL,

            usuario_id UUID NOT NULL,

            created_at TIMESTAMPTZ
                NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT fk_historico_status_pedido
                FOREIGN KEY (pedido_id)
                REFERENCES pedidos(id)
                ON DELETE CASCADE,

            CONSTRAINT fk_historico_status_usuario
                FOREIGN KEY (usuario_id)
                REFERENCES users(id)
        )
    """)

    op.create_index(
        "ix_historico_status_pedidos_pedido_id",
        "historico_status_pedidos",
        ["pedido_id"],
        unique=False,
    )

    op.create_index(
        "ix_historico_status_pedidos_usuario_id",
        "historico_status_pedidos",
        ["usuario_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_historico_status_pedidos_usuario_id",
        table_name="historico_status_pedidos",
    )

    op.drop_index(
        "ix_historico_status_pedidos_pedido_id",
        table_name="historico_status_pedidos",
    )

    op.drop_table("historico_status_pedidos")
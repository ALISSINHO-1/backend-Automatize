"""initial_schema

Revision ID: fbfba8e84540
Revises:
Create Date: 2026-10-05 12:23:18.392529
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa # type: ignore
from sqlalchemy.dialects import postgresql # type: ignore


# revision identifiers, used by Alembic.
revision: str = "fbfba8e84540"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================
    # ENUMS
    # =========================================================

    op.execute(
        """
        CREATE TYPE enum_perfil AS ENUM (
            'ADMIN',
            'CLIENTE',
            'TECNICO'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE enum_status AS ENUM (
            'PLANEAMENTO',
            'EXECUCAO',
            'HOMOLOGACAO',
            'CONCLUIDO'
        )
        """
    )

    op.execute(
        """
        CREATE TYPE enum_tipo_ocorrencia AS ENUM (
            'ERRO',
            'SOLICITACAO_CORRECAO',
            'REGRESSO_ESTADO'
        )
        """
    )

    # =========================================================
    # USERS
    # =========================================================

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "perfil",
            postgresql.ENUM(
                "ADMIN",
                "CLIENTE",
                "TECNICO",
                name="enum_perfil",
                create_type=False,
            ),
            server_default=sa.text("'CLIENTE'::enum_perfil"),
            nullable=False,
        ),
        sa.Column(
            "ativo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # =========================================================
    # PEDIDOS
    # =========================================================

    op.create_table(
        "pedidos",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "codigo_identificador",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PLANEAMENTO",
                "EXECUCAO",
                "HOMOLOGACAO",
                "CONCLUIDO",
                name="enum_status",
                create_type=False,
            ),
            server_default=sa.text("'PLANEAMENTO'::enum_status"),
            nullable=False,
        ),
        sa.Column(
            "percentual_progresso",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("0.00"),
            nullable=True,
        ),
        sa.Column(
            "cliente_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "responsavel_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "percentual_progresso >= 0 AND percentual_progresso <= 100",
            name="pedidos_percentual_progresso_check",
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["responsavel_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo_identificador"),
    )

    # =========================================================
    # OCORRENCIAS
    # =========================================================

    op.create_table(
        "ocorrencias",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "pedido_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "autor_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "tipo",
            postgresql.ENUM(
                "ERRO",
                "SOLICITACAO_CORRECAO",
                "REGRESSO_ESTADO",
                name="enum_tipo_ocorrencia",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("motivo_regresso", sa.Text(), nullable=True),
        sa.Column(
            "status_anterior",
            postgresql.ENUM(
                "PLANEAMENTO",
                "EXECUCAO",
                "HOMOLOGACAO",
                "CONCLUIDO",
                name="enum_status",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "status_novo",
            postgresql.ENUM(
                "PLANEAMENTO",
                "EXECUCAO",
                "HOMOLOGACAO",
                "CONCLUIDO",
                name="enum_status",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["pedidos.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["autor_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # =========================================================
    # ANEXOS
    # =========================================================

    op.create_table(
        "anexos",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "pedido_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "ocorrencia_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "enviado_por_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "nome_arquivo",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "caminho_storage",
            sa.String(length=500),
            nullable=False,
        ),
        sa.Column(
            "extensao",
            sa.String(length=10),
            nullable=False,
        ),
        sa.Column(
            "tamanho_bytes",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["pedidos.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ocorrencia_id"],
            ["ocorrencias.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["enviado_por_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # =========================================================
    # ACEITES FORMAIS
    # =========================================================

    op.create_table(
        "aceites_formais",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "pedido_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "cliente_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "data_hora_aceite",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "versao_entregavel",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "declaracao_aceite",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "hash_validacao",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["pedidos.id"],
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # =========================================================
    # AUDITORIA
    # =========================================================

    op.create_table(
        "auditoria_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "pedido_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "acao",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "detalhes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["pedidos.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Ordem inversa por causa das foreign keys.
    op.drop_table("auditoria_logs")
    op.drop_table("aceites_formais")
    op.drop_table("anexos")
    op.drop_table("ocorrencias")
    op.drop_table("pedidos")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS enum_tipo_ocorrencia")
    op.execute("DROP TYPE IF EXISTS enum_status")
    op.execute("DROP TYPE IF EXISTS enum_perfil")
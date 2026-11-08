"""Adiciona histórico de mensagens por demanda e canal."""

import sqlalchemy as sa
from alembic import op

revision = "2a6d14c839ef"
down_revision = "f9a2d4c6b803"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_mensagens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pedido_id", sa.Uuid(), sa.ForeignKey("pedidos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("autor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("canal", sa.String(10), nullable=False),
        sa.Column("texto", sa.String(2000), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("canal IN ('cliente', 'interno')", name="chat_mensagens_canal_check"),
    )
    op.create_index("ix_chat_mensagens_conversa", "chat_mensagens", ["pedido_id", "canal", "criado_em", "id"])
    op.execute("ALTER TABLE public.chat_mensagens ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.chat_mensagens FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE role_name text;
        BEGIN
            FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                    EXECUTE format('REVOKE ALL ON TABLE public.chat_mensagens FROM %I', role_name);
                END IF;
            END LOOP;
        END $$
    """)


def downgrade():
    op.drop_table("chat_mensagens")

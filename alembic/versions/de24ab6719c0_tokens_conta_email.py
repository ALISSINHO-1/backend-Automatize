"""Tokens one-time para verificacao de email e recuperacao de senha.

Somente nova tabela/colunas. Nao executa em banco compartilhado automaticamente.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "de24ab6719c0"
down_revision = "c7d9f40a12b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "origem_cadastro", sa.String(16), nullable=False, server_default="LEGADO"
    ))
    op.add_column("users", sa.Column(
        "email_verificado_em", sa.DateTime(timezone=True), nullable=True
    ))
    op.add_column("users", sa.Column(
        "token_version", sa.Integer(), nullable=False, server_default="0"
    ))
    op.create_check_constraint(
        "ck_users_origem_cadastro", "users",
        "origem_cadastro IN ('LEGADO','PUBLICO')",
    )
    op.create_table(
        "tokens_conta",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("usuario_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("finalidade", sa.String(20), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "finalidade IN ('VERIFICAR_EMAIL', 'REDEFINIR_SENHA')",
            name="ck_tokens_conta_finalidade",
        ),
    )
    op.create_index("ix_tokens_conta_usuario_id", "tokens_conta", ["usuario_id"])
    op.execute("ALTER TABLE public.tokens_conta ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.tokens_conta FROM PUBLIC")
    op.execute("""
    DO $$
    DECLARE role_name text; column_name text;
    BEGIN
      FOREACH role_name IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
          EXECUTE format('REVOKE ALL ON public.tokens_conta FROM %I', role_name);
        END IF;
      END LOOP;
      FOR column_name IN SELECT attname FROM pg_attribute
          WHERE attrelid='public.tokens_conta'::regclass AND attnum > 0 AND NOT attisdropped
      LOOP
        EXECUTE format(
          'REVOKE SELECT (%I), INSERT (%I), UPDATE (%I), REFERENCES (%I) '
          || 'ON TABLE public.tokens_conta FROM PUBLIC',
          column_name, column_name, column_name, column_name
        );
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
            EXECUTE format(
              'REVOKE SELECT (%I), INSERT (%I), UPDATE (%I), REFERENCES (%I) '
              || 'ON TABLE public.tokens_conta FROM %I',
              column_name, column_name, column_name, column_name, role_name
            );
          END IF;
        END LOOP;
      END LOOP;
    END $$
    """)


def downgrade() -> None:
    raise RuntimeError("A remocao dos tokens requer plano de seguranca e retencao.")

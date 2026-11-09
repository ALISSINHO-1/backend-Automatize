"""Contas pendentes e base de vinculos DEV/SAAS sem acesso publico a tabelas.

A operacao e incremental. Nao migrar o Supabase principal sem ensaio
em copia restaurada, verificacao da role SQL e autorizacao do responsavel.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "c7d9f40a12b3"
down_revision = "84db17ce9f26"
branch_labels = None
depends_on = None

TABELAS = ("organizacoes", "organizacao_usuarios", "contratacoes")


def upgrade() -> None:
    # Contas existentes permanecem ATIVO; apenas novos cadastros publicos
    # recebem PENDENTE explicitamente pela API.
    op.add_column(
        "users",
        sa.Column(
            "situacao_cadastro", sa.String(length=16),
            nullable=False, server_default="ATIVO",
        ),
    )
    op.create_check_constraint(
        "ck_users_situacao_cadastro",
        "users",
        "situacao_cadastro IN ('ATIVO', 'PENDENTE')",
    )
    op.create_table(
        "organizacoes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("criado_por_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_organizacoes_criado_por_id", "organizacoes", ["criado_por_id"])
    op.create_table(
        "organizacao_usuarios",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("organizacao_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizacoes.id"), nullable=False),
        sa.Column("usuario_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("papel", sa.String(16), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organizacao_id", "usuario_id",
                            name="uq_organizacao_usuario"),
        sa.CheckConstraint("papel IN ('GESTOR', 'COLABORADOR')",
                           name="ck_organizacao_usuarios_papel"),
    )
    op.create_index("ix_organizacao_usuarios_usuario_id", "organizacao_usuarios", ["usuario_id"])
    op.create_table(
        "contratacoes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("situacao", sa.String(16), nullable=False),
        sa.Column("usuario_cliente_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("organizacao_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizacoes.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("situacao IN ('PENDENTE', 'ATIVA', 'SUSPENSA')",
                           name="ck_contratacoes_situacao"),
        sa.CheckConstraint(
            "(tipo = 'DEV' AND usuario_cliente_id IS NOT NULL AND organizacao_id IS NULL)"
            " OR (tipo = 'SAAS' AND organizacao_id IS NOT NULL AND usuario_cliente_id IS NULL)",
            name="ck_contratacoes_tipo_titular",
        ),
    )
    op.create_index("ix_contratacoes_usuario_cliente_id", "contratacoes", ["usuario_cliente_id"])
    op.create_index("ix_contratacoes_organizacao_id", "contratacoes", ["organizacao_id"])

    # As tabelas novas sao internas a FastAPI. NENHUMA Data API de usuario.
    for nome in TABELAS:
        op.execute(f"ALTER TABLE public.{nome} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE public.{nome} FROM PUBLIC")
        op.execute(f"""
            DO $revoga$
            DECLARE r text; col record;
            BEGIN
              FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                  EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I', '{nome}', r);
                END IF;
              END LOOP;
              FOR col IN
                SELECT attname FROM pg_attribute
                WHERE attrelid = 'public.{nome}'::regclass AND attnum > 0
                  AND NOT attisdropped
              LOOP
                EXECUTE format(
                  'REVOKE SELECT (%I), INSERT (%I), UPDATE (%I), REFERENCES (%I) '
                  || 'ON TABLE public.%I FROM PUBLIC',
                  col.attname, col.attname, col.attname, col.attname, '{nome}'
                );
                FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
                  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                    EXECUTE format(
                      'REVOKE SELECT (%I), INSERT (%I), UPDATE (%I), REFERENCES (%I) '
                      || 'ON TABLE public.%I FROM %I',
                      col.attname, col.attname, col.attname, col.attname, '{nome}', r
                    );
                  END IF;
                END LOOP;
              END LOOP;
            END $revoga$
        """)


def downgrade() -> None:
    # Nao apagar empresas, contratos e vinculos de negocio sem plano de retencao.
    raise RuntimeError("Downgrade de onboarding requer plano de migracao de dados.")

"""Adiciona o registro criptografado de movimentos do quadro."""

import sqlalchemy as sa
from alembic import op

revision = "84db17ce9f26"
down_revision = "51cb39a0d826"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "movimentos_quadro",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conteudo_cifrado", sa.LargeBinary(), nullable=False),
    )
    op.execute("ALTER TABLE public.movimentos_quadro ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.movimentos_quadro FROM PUBLIC")
    op.execute("""
        DO $$
        DECLARE role_name text;
        BEGIN
            FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                    EXECUTE format('REVOKE ALL ON TABLE public.movimentos_quadro FROM %I', role_name);
                END IF;
            END LOOP;
        END $$
    """)


def downgrade():
    raise RuntimeError("A tabela contém registros de auditoria; a remoção requer plano de retenção.")

"""habilita RLS em todas as tabelas

Revision ID: 7b2d4e6f8a10
Revises: 3c9e7a1b5d20

No Supabase o RLS das primeiras tabelas foi ligado pelo painel, mas as criadas
depois por migration (etapas_operacionais, historico_status_pedidos e a
alembic_version) ficaram "UNRESTRICTED": qualquer um com a chave publica lia e
gravava nelas pela Data API. Sem policies, o RLS bloqueia a Data API e a API
FastAPI continua funcionando, porque conecta com o dono das tabelas, que nao
passa pelo RLS. Em tabela que ja tem RLS o comando nao muda nada.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "7b2d4e6f8a10"
down_revision: Union[str, Sequence[str], None] = "3c9e7a1b5d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELAS = (
    "users",
    "pedidos",
    "ocorrencias",
    "anexos",
    "aceites_formais",
    "auditoria_logs",
    "historico_status_pedidos",
    "etapas_operacionais",
    "alembic_version",
)

# Estavam sem RLS antes desta migration; so estas voltam ao estado anterior no downgrade.
TABELAS_SEM_RLS_ANTES = (
    "historico_status_pedidos",
    "etapas_operacionais",
    "alembic_version",
)


def upgrade() -> None:
    for tabela in TABELAS:
        op.execute(f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for tabela in TABELAS_SEM_RLS_ANTES:
        op.execute(f"ALTER TABLE {tabela} DISABLE ROW LEVEL SECURITY")

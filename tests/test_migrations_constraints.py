from io import StringIO
from pathlib import Path
import re

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, UniqueConstraint

from app.core.database import Base
import app.domain.models  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]


def alembic_config(**kwargs):
    config = Config(str(ROOT / "alembic.ini"), **kwargs)
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return config


def test_revision_chain_and_offline_upgrade_create_all_models_once(monkeypatch):
    # Compile PostgreSQL DDL without opening any connection or reading live data.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://unit:unit@localhost/unit")
    output = StringIO()
    config = alembic_config(output_buffer=output)
    revisions = ScriptDirectory.from_config(config)
    assert revisions.get_heads() == ["7b2d4e6f8a10"]
    assert [item.revision for item in revisions.walk_revisions()] == [
        "7b2d4e6f8a10", "3c9e7a1b5d20", "fd3fe1dcfeab", "a4fa37701385", "fbfba8e84540",
    ]
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    tables = re.findall(r"CREATE TABLE (\w+)", sql)
    assert set(tables) - {"alembic_version"} == set(Base.metadata.tables)
    assert len(tables) == len(set(tables))
    for enum in ("enum_status", "enum_perfil", "enum_tipo_ocorrencia"):
        assert sql.count(f"CREATE TYPE {enum} AS ENUM") == 1
    assert "ON DELETE CASCADE" in sql
    assert "ON DELETE SET NULL" in sql
    assert "UNIQUE (email)" in sql
    assert "UNIQUE (codigo_identificador)" in sql
    assert "CHECK (percentual_progresso >= 0 AND percentual_progresso <= 100)" in sql
    assert "CREATE INDEX ix_historico_status_pedidos_pedido_id" in sql
    assert "CREATE INDEX ix_historico_status_pedidos_usuario_id" in sql
    assert "CREATE INDEX ix_etapas_operacionais_pedido_id" in sql
    assert "UNIQUE (pedido_id)" in sql
    assert "CREATE TRIGGER trg_aceites_formais_imutavel" in sql
    assert "CREATE TRIGGER trg_pedidos_protege_conclusao" in sql
    # Sem RLS o Supabase deixa a tabela aberta pela Data API (chave publica).
    for table in set(tables):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql


def test_foreign_keys_and_delete_policies_preserve_business_records():
    expected = {
        ("pedidos", "cliente_id"): ("users.id", None),
        ("pedidos", "responsavel_id"): ("users.id", None),
        ("ocorrencias", "pedido_id"): ("pedidos.id", "CASCADE"),
        ("ocorrencias", "autor_id"): ("users.id", None),
        ("anexos", "pedido_id"): ("pedidos.id", "CASCADE"),
        ("anexos", "ocorrencia_id"): ("ocorrencias.id", "SET NULL"),
        ("anexos", "enviado_por_id"): ("users.id", None),
        ("aceites_formais", "pedido_id"): ("pedidos.id", None),
        ("aceites_formais", "cliente_id"): ("users.id", None),
        ("auditoria_logs", "usuario_id"): ("users.id", "SET NULL"),
        ("auditoria_logs", "pedido_id"): ("pedidos.id", "SET NULL"),
        ("historico_status_pedidos", "pedido_id"): ("pedidos.id", "CASCADE"),
        ("historico_status_pedidos", "usuario_id"): ("users.id", None),
        ("etapas_operacionais", "pedido_id"): ("pedidos.id", "CASCADE"),
        ("etapas_operacionais", "concluida_por_id"): ("users.id", None),
        ("etapas_operacionais", "criado_por_id"): ("users.id", None),
    }
    actual = {}
    for name, table in Base.metadata.tables.items():
        assert [column.name for column in table.primary_key] == ["id"]
        assert not table.c.id.nullable
        for fk in table.foreign_keys:
            actual[name, fk.parent.name] = (fk.target_fullname, fk.ondelete)
            if fk.ondelete == "SET NULL":
                assert fk.parent.nullable
    assert actual == expected
    for table, column in (
        ("users", "email"),
        ("pedidos", "codigo_identificador"),
        ("aceites_formais", "pedido_id"),
    ):
        assert any(isinstance(item, UniqueConstraint) and list(item.columns.keys()) == [column]
                   for item in Base.metadata.tables[table].constraints)
    assert any(isinstance(item, CheckConstraint) and item.name == "pedidos_percentual_progresso_check"
               for item in Base.metadata.tables["pedidos"].constraints)
    assert {tuple(index.columns.keys()) for index in
            Base.metadata.tables["historico_status_pedidos"].indexes} == {
        ("pedido_id",), ("usuario_id",),
    }

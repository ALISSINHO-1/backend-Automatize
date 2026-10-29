"""HTTP + SQL real em SQLite; locks, triggers e migrations exigem o job PostgreSQL."""

from uuid import uuid4

import pytest
from sqlalchemy import JSON, DefaultClause, MetaData, create_engine, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.database import Base
from tests.integration.conftest import criar_usuario, storage
from tests.integration.test_demandas_acoes_api import (
    SECRET,
    atores,
    auth,
    client,
    demanda_id,
    test_anexos_listagem_sem_chaves_e_acesso_autorizado,
    test_filtros_totais_nao_paginados_e_sem_vazamento,
    test_ocorrencias_vinculo_autoria_auditoria_e_rollback,
    test_put_preserva_campos_protegidos_e_isolamento,
)


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg2://test@localhost/automatize_test",
        JWT_SECRET_KEY=SECRET,
    )


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("gen_random_uuid", 0, lambda: uuid4().hex)

    metadata = MetaData()
    for original in Base.metadata.tables.values():
        table = original.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            if column.server_default is not None and "::" in str(
                column.server_default.arg
            ):
                column.server_default = DefaultClause(
                    text(str(column.server_default.arg).split("::")[0])
                )
    metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


def test_documentacao_visualmente_agrupada_sem_rotas_duplicadas(client):
    schema = client.get("/openapi.json").json()
    tags = {tag["name"] for tag in schema["tags"]}
    assert {
        "Autenticação",
        "Demandas",
        "Homologação",
        "Ocorrências",
        "Anexos",
        "Auditoria",
    } <= tags
    operations = [
        op
        for path in schema["paths"].values()
        for op in path.values()
        if isinstance(op, dict) and "operationId" in op
    ]
    assert len({op["operationId"] for op in operations}) == len(operations)
    assert all(len(op["tags"]) == 1 and op["tags"][0] in tags for op in operations)
    assert "filter" in client.get("/docs").text
    assert '"docExpansion": "none"' in client.get("/docs").text

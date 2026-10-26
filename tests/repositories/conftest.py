"""Exercise actual SQL and FKs in an isolated in-memory database.

SQLite does not test PostgreSQL enums or row locks; those are checked through
PostgreSQL DDL/statement compilation and the read-only catalog audit.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import DefaultClause, MetaData, create_engine, event, text
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum
from app.domain.models.pedido import Pedido
from app.domain.models.user import User


@pytest.fixture
def persistence_db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("gen_random_uuid", 0, lambda: uuid4().hex)

    metadata = MetaData()
    for name in ("users", "pedidos", "ocorrencias", "anexos", "historico_status_pedidos"):
        table = Base.metadata.tables[name].to_metadata(metadata)
        # Adapt only PostgreSQL casts in this test's copied DDL, never models.
        for column in table.columns:
            if column.server_default is not None and "::" in str(column.server_default.arg):
                column.server_default = DefaultClause(text(str(column.server_default.arg).split("::")[0]))
    metadata.create_all(engine)
    try:
        with Session(engine, autoflush=False) as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def ownership(persistence_db):
    users = [User(id=uuid4(), nome=f"User {i}", email=f"user{i}@test.invalid", senha_hash="test-hash",
                  perfil=profile, ativo=True)
             for i, profile in enumerate([
                 PerfilEnum.CLIENTE, PerfilEnum.CLIENTE, PerfilEnum.CLIENTE,
                 PerfilEnum.TECNICO, PerfilEnum.TECNICO, PerfilEnum.ADMIN,
             ])]
    persistence_db.add_all(users)
    persistence_db.flush()
    c1, c2, c3, t1, t2, admin = users
    pedidos = [Pedido(id=uuid4(), codigo_identificador=f"P-{i}", titulo=f"Pedido {i}",
                      cliente_id=client.id, responsavel_id=tech.id if tech else None,
                      status=StatusPedidoEnum.PLANEAMENTO)
               for i, (client, tech) in enumerate([(c1, t1), (c1, t1), (c2, t2), (c1, t2), (c3, None)])]
    persistence_db.add_all(pedidos)
    persistence_db.commit()
    return SimpleNamespace(c1=c1, c2=c2, c3=c3, t1=t1, t2=t2, admin=admin, pedidos=pedidos)

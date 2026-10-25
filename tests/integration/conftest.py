"""Fixtures de integração com PostgreSQL real.

Defina TEST_DATABASE_URL com um banco descartável cujo nome contenha "test",
por exemplo postgresql+psycopg2://postgres@localhost:5432/automatize_test.
As migrations do Alembic são aplicadas uma vez (incluindo as triggers) e cada
teste roda dentro de uma transação desfeita ao final: os commits dos services
viram savepoints e nada fica gravado.
"""
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine # type: ignore
from sqlalchemy.engine import make_url # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.enums import PerfilEnum
from app.domain.models.user import User


ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL não definida; testes de integração com PostgreSQL ignorados.")
    if "test" not in (make_url(TEST_DATABASE_URL).database or ""):
        pytest.fail("TEST_DATABASE_URL deve apontar para um banco de testes (nome contendo 'test').")

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    database_url_original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        command.upgrade(config, "head")
    finally:
        if database_url_original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = database_url_original

    database_engine = create_engine(TEST_DATABASE_URL)
    yield database_engine
    database_engine.dispose()


@pytest.fixture
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def criar_usuario(db):
    def _criar(perfil: PerfilEnum = PerfilEnum.CLIENTE, *, ativo: bool = True) -> User:
        usuario = User(
            id=uuid4(),
            nome=f"{perfil.value.title()} de teste",
            email=f"{uuid4().hex}@example.com",
            senha_hash="nao-usado",
            perfil=perfil,
            ativo=ativo,
        )
        db.add(usuario)
        db.flush()
        return usuario

    return _criar


class FakeStorage:
    """Substitui o Supabase Storage: guarda os uploads em memória."""

    def __init__(self) -> None:
        self.arquivos: dict[str, tuple[bytes, str]] = {}

    def upload(self, *, pedido_id: UUID, nome_arquivo: str, conteudo: bytes, content_type: str) -> str:
        caminho = f"pedidos/{pedido_id}/{uuid4()}{Path(nome_arquivo).suffix.lower()}"
        self.arquivos[caminho] = (conteudo, content_type)
        return caminho

    def delete(self, caminho: str) -> None:
        self.arquivos.pop(caminho, None)


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()

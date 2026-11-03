"""Contratos HTTP com SQL real em SQLite; PostgreSQL fica na suite integration."""
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.domain.models import User
from app.domain.models.enums import PerfilEnum
from tests.integration.conftest import FakeStorage
from tests.integration.test_demandas_acoes_api import client, atores, auth, demanda_id
from tests.api_finalizacao_cases import *  # noqa: F403


@pytest.fixture
def db(persistence_db):
    return persistence_db


@pytest.fixture
def settings():
    return Settings(_env_file=None, DATABASE_URL="postgresql+psycopg2://test:test@localhost:5432/automatize_test",
                    JWT_SECRET_KEY="teste-http-isolado-" + "x" * 32)


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def criar_usuario(db):
    def criar(perfil=PerfilEnum.CLIENTE, *, ativo=True):
        usuario = User(id=uuid4(), nome="Usuario de teste", email=f"{uuid4()}@test.invalid",
                       senha_hash="unused", perfil=perfil, ativo=ativo)
        db.add(usuario)
        db.flush()
        return usuario
    return criar

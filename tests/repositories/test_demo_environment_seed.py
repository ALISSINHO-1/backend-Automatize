"""Integracao local com SQL/FKs reais em SQLite; nao e um teste do Supabase."""
import secrets

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import SecretStr, ValidationError
from sqlalchemy import event, func, select

from app.api.dependencies import get_current_user
from app.core.config import Settings
from app.core.security import verify_password
from app.domain.models.auditoria_log import AuditoriaLog
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum
from app.domain.models.ocorrencia import Ocorrencia
from app.domain.models.pedido import Pedido
from app.domain.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.demanda_service import DemandaQueryService
from scripts.seed_demo_environment import (
    DEMO_PEDIDO_CODIGO, DemoEnvironmentSettings, DemoSeedConflictError,
    seed_demo_environment,
)


@pytest.fixture
def demo():
    return DemoEnvironmentSettings(_env_file=None, **{
        f"DEMO_{perfil}_PASSWORD": SecretStr(secrets.token_urlsafe(18))
        for perfil in ("ADMIN", "TECNICO", "CLIENTE")
    })


def counts(db):
    return tuple(db.scalar(select(func.count()).select_from(model))
                 for model in (User, Pedido, Ocorrencia, AuditoriaLog))


def test_seed_persiste_tres_perfis_pedido_ocorrencia_e_auditoria(persistence_db, demo):
    result = seed_demo_environment(persistence_db, demo)
    persistence_db.expire_all()
    assert counts(persistence_db) == (3, 1, 1, 1)
    assert set(result.created_profiles) == set(PerfilEnum)
    pedido = persistence_db.get(Pedido, result.pedido_id)
    ocorrencia = persistence_db.get(Ocorrencia, result.ocorrencia_id)
    assert pedido.codigo_identificador == DEMO_PEDIDO_CODIGO
    assert pedido.status == StatusPedidoEnum.PLANEAMENTO
    assert pedido.cliente_id == result.user_ids[PerfilEnum.CLIENTE]
    assert pedido.responsavel_id == result.user_ids[PerfilEnum.TECNICO]
    assert ocorrencia.pedido_id == pedido.id
    assert ocorrencia.autor_id == pedido.cliente_id
    log = persistence_db.scalar(select(AuditoriaLog))
    assert log.usuario_id == result.user_ids[PerfilEnum.ADMIN]
    assert log.detalhes["ocorrencia_id"] == str(ocorrencia.id)
    for perfil, account in demo.accounts().items():
        user = persistence_db.get(User, result.user_ids[perfil])
        assert user.email == account.DEMO_USER_EMAIL
        assert user.perfil == perfil and user.ativo is True
        assert user.senha_hash != account.DEMO_USER_PASSWORD.get_secret_value()
        assert verify_password(account.DEMO_USER_PASSWORD.get_secret_value(), user.senha_hash)
        assert not any(account.DEMO_USER_PASSWORD.get_secret_value() in str(log.detalhes)
                       for account in demo.accounts().values())


def test_seed_repetido_preserva_ids_hashes_e_dados_editados(persistence_db, demo):
    first = seed_demo_environment(persistence_db, demo)
    hashes = {p: persistence_db.get(User, ident).senha_hash for p, ident in first.user_ids.items()}
    pedido = persistence_db.get(Pedido, first.pedido_id)
    pedido.titulo = "Titulo editado durante a apresentacao"
    persistence_db.commit()
    second = seed_demo_environment(persistence_db, demo)
    assert second.user_ids == first.user_ids
    assert second.pedido_id == first.pedido_id and second.ocorrencia_id == first.ocorrencia_id
    assert second.created_profiles == ()
    assert not second.pedido_created and not second.ocorrencia_created
    assert counts(persistence_db) == (3, 1, 1, 1)
    assert persistence_db.get(Pedido, first.pedido_id).titulo == pedido.titulo
    assert {p: persistence_db.get(User, ident).senha_hash for p, ident in first.user_ids.items()} == hashes


@pytest.mark.parametrize("conflict", ["senha", "perfil", "inativo", "caixa_email"])
def test_conta_existente_incompativel_nunca_e_sobrescrita(persistence_db, demo, conflict):
    result = seed_demo_environment(persistence_db, demo)
    user = persistence_db.get(User, result.user_ids[PerfilEnum.ADMIN])
    if conflict == "senha":
        user.senha_hash = "nao-e-um-hash-bcrypt"
    elif conflict == "perfil":
        user.perfil = PerfilEnum.CLIENTE
    elif conflict == "inativo":
        user.ativo = False
    else:
        user.email = user.email.upper()
    persistence_db.commit()
    before = (user.email, user.perfil, user.ativo, user.senha_hash)
    with pytest.raises(DemoSeedConflictError):
        seed_demo_environment(persistence_db, demo)
    persistence_db.refresh(user)
    assert (user.email, user.perfil, user.ativo, user.senha_hash) == before
    assert counts(persistence_db) == (3, 1, 1, 1)


def test_falha_na_ocorrencia_desfaz_todas_as_insercoes(persistence_db, demo):
    def fail(*args):
        raise RuntimeError("falha de persistencia simulada")
    event.listen(Ocorrencia, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            seed_demo_environment(persistence_db, demo)
    finally:
        event.remove(Ocorrencia, "before_insert", fail)
    assert counts(persistence_db) == (0, 0, 0, 0)
    assert persistence_db.is_active


def test_seed_nao_adota_pedido_existente_de_outro_cliente(persistence_db, demo, ownership):
    pedido = ownership.pedidos[0]
    pedido.codigo_identificador = DEMO_PEDIDO_CODIGO
    persistence_db.commit()
    before = counts(persistence_db)
    with pytest.raises(DemoSeedConflictError, match="outro vinculo"):
        seed_demo_environment(persistence_db, demo)
    assert counts(persistence_db) == before
    assert persistence_db.get(Pedido, pedido.id).cliente_id == ownership.c1.id


def test_seed_nao_faz_commit_de_alteracoes_alheias(persistence_db, demo, ownership):
    ownership.c1.nome = "Edicao ainda nao confirmada"
    with pytest.raises(DemoSeedConflictError, match="sessao exclusiva"):
        seed_demo_environment(persistence_db, demo)
    assert ownership.c1 in persistence_db.dirty
    persistence_db.rollback()


def test_login_jwt_e_escopos_usam_usuarios_persistidos(persistence_db, demo, ownership):
    result = seed_demo_environment(persistence_db, demo)
    configured = Settings(
        _env_file=None, DATABASE_URL="postgresql+psycopg2://localhost/test",
        JWT_SECRET_KEY=secrets.token_urlsafe(48),
    )
    users = {}
    for perfil, account in demo.accounts().items():
        token = AuthService(persistence_db, configured).authenticate(
            account.DEMO_USER_EMAIL, account.DEMO_USER_PASSWORD.get_secret_value(),
        )
        user = get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            persistence_db, configured,
        )
        assert user.id == result.user_ids[perfil] and user.perfil == perfil
        users[perfil] = user
    repo = UserRepository(persistence_db)
    tecnico, cliente = users[PerfilEnum.TECNICO], users[PerfilEnum.CLIENTE]
    assert tecnico in repo.list_tecnicos()
    assert repo.list_clientes_por_responsavel(responsavel_id=tecnico.id) == [cliente]
    assert repo.get_cliente_por_responsavel(ownership.c1.id, responsavel_id=tecnico.id) is None
    assert repo.get_cliente_proprio(usuario_id=cliente.id).id == cliente.id
    service = DemandaQueryService(persistence_db)
    for perfil, user in users.items():
        assert service.get_demand(user, result.pedido_id) is not None
    assert service.get_demand(tecnico, ownership.pedidos[0].id) is None
    assert service.get_demand(cliente, ownership.pedidos[0].id) is None
    assert service.list_demands(tecnico, offset=0, limit=100)[0].id == result.pedido_id
    assert service.list_demands(cliente, offset=0, limit=100)[0].id == result.pedido_id


@pytest.mark.parametrize("password", ["", "x" * 73, "é" * 37])
def test_senha_invalida_nao_vaza_em_erro(password):
    with pytest.raises(ValidationError) as exc:
        DemoEnvironmentSettings(
            _env_file=None, DEMO_ADMIN_PASSWORD=password,
            DEMO_TECNICO_PASSWORD=SecretStr(secrets.token_urlsafe(18)),
            DEMO_CLIENTE_PASSWORD=SecretStr(secrets.token_urlsafe(18)),
        )
    assert "input_value" not in str(exc.value)
    if password:
        assert password not in str(exc.value)


def test_emails_repetidos_recusados_e_segredos_ocultos(demo):
    assert all(account.DEMO_USER_PASSWORD.get_secret_value() not in repr(demo)
               for account in demo.accounts().values())
    with pytest.raises(ValidationError):
        DemoEnvironmentSettings(
            _env_file=None, **(demo.model_dump() | {"DEMO_ADMIN_EMAIL": demo.DEMO_CLIENTE_EMAIL}),
        )

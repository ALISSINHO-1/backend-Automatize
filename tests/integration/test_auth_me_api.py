"""Exercise the existing JSON login and /auth/me with real PostgreSQL users."""
import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import hash_password
from app.domain.models.enums import PerfilEnum
from app.main import create_app
from tests.integration.test_demandas_acoes_api import settings  # noqa: F401


@pytest.fixture
def identity_client(db, settings):
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client


@pytest.fixture
def login_user(db, criar_usuario, identity_client):
    def login(perfil):
        user = criar_usuario(perfil)
        password = "synthetic-login-password"
        user.senha_hash = hash_password(password)
        db.flush()
        response = identity_client.post("/auth/login", json={"email": user.email, "senha": password})
        assert response.status_code == 200
        return user, {"Authorization": f"Bearer {response.json()['access_token']}"}

    return login


@pytest.mark.parametrize("perfil", list(PerfilEnum))
def test_login_e_me_retornam_somente_o_usuario_do_token(
    identity_client, login_user, criar_usuario, perfil,
):
    owner, authorization = login_user(perfil)
    other = criar_usuario(PerfilEnum.ADMIN)

    response = identity_client.get(
        "/auth/me", headers=authorization,
        params={"id": str(other.id), "usuario_id": str(other.id), "user_id": str(other.id)},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(owner.id), "nome": owner.nome,
        "email": owner.email, "perfil": perfil.value,
    }
    assert owner.senha_hash not in response.text


@pytest.mark.parametrize("change", ["deactivated", "deleted"])
def test_me_revalida_usuario_persistido_depois_do_login(
    db, identity_client, login_user, change,
):
    user, authorization = login_user(PerfilEnum.CLIENTE)
    if change == "deactivated":
        user.ativo = False
    else:
        db.delete(user)
    db.flush()
    db.expire_all()

    response = identity_client.get("/auth/me", headers=authorization)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Não foi possível autenticar."}


def test_me_retorna_perfil_atual_do_banco(identity_client, login_user, db):
    user, authorization = login_user(PerfilEnum.CLIENTE)
    user.perfil = PerfilEnum.TECNICO
    db.flush()
    db.expire_all()

    response = identity_client.get("/auth/me", headers=authorization)

    assert response.status_code == 200
    assert response.json()["perfil"] == "TECNICO"


@pytest.mark.parametrize("authorization", [None, "Bearer not-a-jwt"], ids=["missing", "invalid"])
def test_me_recusa_credenciais_invalidas(identity_client, authorization):
    headers = {} if authorization is None else {"Authorization": authorization}

    response = identity_client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Não foi possível autenticar."}


def test_perfil_expoe_somente_dados_do_proprio_usuario(identity_client, login_user):
    user, authorization = login_user(PerfilEnum.TECNICO)
    response = identity_client.get("/auth/me/detalhes", headers=authorization)
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(user.id)
    assert payload["perfil"] == "TECNICO"
    assert payload["ativo"] is True
    assert "senha_hash" not in payload
    assert "token_version" not in payload


def test_edicao_do_proprio_nome_nao_altera_perfil(identity_client, login_user, db):
    user, authorization = login_user(PerfilEnum.CLIENTE)
    response = identity_client.patch(
        "/auth/me", headers=authorization, json={"nome": "  Cliente   Atualizado  "}
    )
    assert response.status_code == 200
    assert response.json()["nome"] == "Cliente Atualizado"
    assert response.json()["perfil"] == "CLIENTE"
    db.refresh(user)
    assert user.nome == "Cliente Atualizado"


def test_usuario_nao_pode_elevar_privilegios_na_edicao(identity_client, login_user):
    _user, authorization = login_user(PerfilEnum.CLIENTE)
    response = identity_client.patch(
        "/auth/me", headers=authorization, json={"nome": "Teste", "perfil": "ADMIN"}
    )
    assert response.status_code == 422


def test_troca_de_senha_invalida_tokens_antigos(identity_client, login_user, db):
    user, authorization = login_user(PerfilEnum.ADMIN)
    antiga = user.token_version or 0
    incorreta = identity_client.post(
        "/auth/me/senha", headers=authorization,
        json={"senha_atual": "senha-errada", "nova_senha": "nova-senha-segura-123"}
    )
    assert incorreta.status_code == 400
    assert user.token_version == antiga
    resposta = identity_client.post(
        "/auth/me/senha", headers=authorization,
        json={"senha_atual": "synthetic-login-password", "nova_senha": "nova-senha-segura-123"}
    )
    assert resposta.status_code == 204
    db.refresh(user)
    assert user.token_version == antiga + 1
    assert identity_client.get("/auth/me", headers=authorization).status_code == 401
    novo_login = identity_client.post("/auth/login", json={
        "email": user.email, "senha": "nova-senha-segura-123"
    })
    assert novo_login.status_code == 200


def test_perfil_exige_sessao(identity_client):
    assert identity_client.get("/auth/me/detalhes").status_code == 401
    assert identity_client.patch("/auth/me", json={"nome": "Teste"}).status_code == 401
    assert identity_client.post("/auth/me/senha", json={
        "senha_atual": "uma-senha", "nova_senha": "outra-senha-segura"
    }).status_code == 401

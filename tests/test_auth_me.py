"""GET /auth/me: identidade do dono do token, usada pelo front para escolher as telas por perfil."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.domain.models.enums import PerfilEnum
from tests.test_demandas_auth import api, bearer, fake_db, make_token, make_user  # noqa: F401


@pytest.mark.parametrize("perfil", list(PerfilEnum))
def test_me_retorna_id_nome_email_e_perfil(api, fake_db, perfil):
    client, _application, _settings = api
    user = make_user(perfil)
    fake_db.users[user.id] = user

    response = client.get("/auth/me", headers=bearer(make_token(str(user.id))))

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "nome": user.nome,
        "email": user.email,
        "perfil": perfil.value,
    }


def test_me_nao_expoe_hash_da_senha(api, fake_db):
    client, _application, _settings = api
    user = make_user(PerfilEnum.ADMIN, password_hash="hash-secreto")
    fake_db.users[user.id] = user

    response = client.get("/auth/me", headers=bearer(make_token(str(user.id))))

    assert "senha_hash" not in response.json()
    assert "hash-secreto" not in response.text


def test_me_sem_token_retorna_401_generico(api, fake_db):
    client, _application, _settings = api

    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Não foi possível autenticar."}


def test_me_com_usuario_inativo_retorna_401(api, fake_db):
    client, _application, _settings = api
    user = make_user(PerfilEnum.ADMIN, active=False)
    fake_db.users[user.id] = user

    response = client.get("/auth/me", headers=bearer(make_token(str(user.id))))

    assert response.status_code == 401


@pytest.mark.parametrize("kind", ["malformed", "expired", "wrong-signature"])
def test_me_token_invalido_retorna_401_generico(api, fake_db, kind):
    client, _application, _settings = api
    user = make_user()
    fake_db.users[user.id] = user
    now = int(datetime.now(timezone.utc).timestamp())
    tokens = {
        "malformed": "not-a-jwt",
        "expired": make_token(str(user.id), claims={"iat": now - 60, "exp": now - 1}),
        "wrong-signature": make_token(str(user.id), key="other-test-signing-key-" + "x" * 32),
    }

    response = client.get("/auth/me", headers=bearer(tokens[kind]))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Não foi possível autenticar."}


def test_me_usuario_inexistente_retorna_401_generico(api, fake_db):
    client, _application, _settings = api

    response = client.get("/auth/me", headers=bearer(make_token(str(uuid4()))))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Não foi possível autenticar."}


def test_me_ignora_identidade_fornecida_fora_do_subject(api, fake_db):
    client, _application, _settings = api
    owner = make_user(PerfilEnum.CLIENTE)
    other = make_user(PerfilEnum.ADMIN)
    fake_db.users.update({owner.id: owner, other.id: other})
    token = make_token(str(owner.id), claims={"perfil": "ADMIN", "user_id": str(other.id)})

    response = client.get(
        "/auth/me",
        headers=bearer(token),
        params={"id": str(other.id), "user_id": str(other.id), "usuario_id": str(other.id)},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(owner.id)
    assert response.json()["perfil"] == "CLIENTE"


def test_me_falha_de_persistencia_permanece_erro_do_servidor(api, fake_db):
    client, _application, _settings = api
    fake_db.error = RuntimeError("private-database-error")

    response = client.get("/auth/me", headers=bearer(make_token(str(uuid4()))))

    assert response.status_code == 500
    assert "private-database-error" not in response.text


def test_me_documenta_o_bearer_e_o_contrato_de_identidade(api):
    client, _application, _settings = api
    document = client.get("/openapi.json").json()
    operation = document["paths"]["/auth/me"]["get"]

    assert operation["security"] == [{"BearerAuth": []}]
    assert "401" in operation["responses"]
    assert not operation.get("parameters")
    schema = document["components"]["schemas"]["UsuarioAtualResponse"]
    assert set(schema["properties"]) == {"id", "nome", "email", "perfil"}

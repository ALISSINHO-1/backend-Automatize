"""GET /auth/me: identidade do dono do token, usada pelo front para escolher as telas por perfil."""
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

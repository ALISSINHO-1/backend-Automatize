"""Security contract for pending public accounts."""
from app.core.security import hash_password
from app.domain.models.enums import PerfilEnum
from tests.test_demandas_auth import api, bearer, fake_db, make_token, make_user  # noqa: F401


def test_public_registration_is_disabled_by_default(api, fake_db):
    client, _app, settings = api
    assert settings.PUBLIC_SIGNUP_ENABLED is False
    result = client.post("/auth/cadastro", json={
        "nome": "Cliente Novo", "email": "novo@example.com", "senha": "SenhaSegura123"
    })
    assert result.status_code == 503
    assert not fake_db.users


def test_signup_rejects_role_injection_and_bad_password(api, fake_db):
    client, _, _ = api
    body = {"nome": "Cliente Novo", "email": "novo@example.com",
            "senha": "SenhaSegura123", "perfil": "ADMIN"}
    assert client.post("/auth/cadastro", json=body).status_code == 422
    body.pop("perfil")
    for password in ("123", "é" * 37):
        body["senha"] = password
        assert client.post("/auth/cadastro", json=body).status_code == 422


def test_pending_account_has_context_but_no_operational_access(api, fake_db):
    client, _, _ = api
    account = make_user(PerfilEnum.CLIENTE, password_hash=hash_password("segredo seguro"))
    account.situacao_cadastro = "PENDENTE"
    fake_db.users[account.id] = account
    headers = bearer(make_token(str(account.id)))
    result = client.get("/auth/contexto", headers=headers)
    assert result.status_code == 200
    assert result.json() == {
        "id": str(account.id), "perfil": "CLIENTE",
        "situacao_cadastro": "PENDENTE", "ambientes": [],
    }
    for path in ("/auth/me", "/demandas", "/usuarios"):
        assert client.get(path, headers=headers).status_code == 401

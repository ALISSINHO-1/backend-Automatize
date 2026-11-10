"""Security contract for pending public accounts."""
from app.core.security import hash_password
from app.domain.models.enums import PerfilEnum
from app.services.cadastro_publico_service import TERMOS_USO_VERSAO
from tests.test_demandas_auth import api, bearer, fake_db, make_token, make_user  # noqa: F401


def cadastro_valido():
    return {
        "nome": "Cliente Novo", "email": "novo@example.com", "senha": "SenhaSegura123",
        "termos_aceitos": True, "termos_versao": TERMOS_USO_VERSAO,
    }


def test_public_registration_is_disabled_by_default(api, fake_db):
    client, _app, settings = api
    assert settings.PUBLIC_SIGNUP_ENABLED is False
    result = client.post("/auth/cadastro", json=cadastro_valido())
    assert result.status_code == 503
    assert not fake_db.users


def test_signup_rejects_role_injection_and_bad_password(api, fake_db):
    client, _, _ = api
    body = {**cadastro_valido(), "perfil": "ADMIN"}
    assert client.post("/auth/cadastro", json=body).status_code == 422
    body.pop("perfil")
    for password in ("123", "é" * 37):
        body["senha"] = password
        assert client.post("/auth/cadastro", json=body).status_code == 422


def test_signup_requires_explicit_terms_acceptance(api, fake_db):
    client, _, _ = api
    body = cadastro_valido()
    for field in ("termos_aceitos", "termos_versao"):
        assert client.post(
            "/auth/cadastro", json={key: value for key, value in body.items() if key != field}
        ).status_code == 422
    for invalid in (False, "true", 1):
        assert client.post(
            "/auth/cadastro", json={**body, "termos_aceitos": invalid}
        ).status_code == 422
    assert not fake_db.users


def test_signup_rejects_stale_terms_before_captcha(api, fake_db, monkeypatch):
    client, _, settings = api
    monkeypatch.setattr(settings, "PUBLIC_SIGNUP_ENABLED", True)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", "dummy")
    monkeypatch.setattr(settings, "TURNSTILE_EXPECTED_HOSTNAME", "example.com")
    monkeypatch.setattr("app.api.v1.endpoints.cadastro.EmailSender.ready", lambda _: True)
    response = client.post("/auth/cadastro", json={**cadastro_valido(), "termos_versao": "0.9"})
    assert response.status_code == 409
    assert not fake_db.users


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
        "situacao_cadastro": "PENDENTE", "origem_cadastro": "LEGADO",
        "email_verificado": False, "acesso_dev": False, "ambientes": [],
    }
    for path in ("/auth/me", "/demandas", "/usuarios"):
        assert client.get(path, headers=headers).status_code == 401

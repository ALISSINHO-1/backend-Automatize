"""Security contract for pending public accounts."""
from pydantic import SecretStr

from app.core.security import hash_password
from app.core.config import Settings
from app.main import cadastro_configuracao_pendente
from app.domain.models.enums import PerfilEnum
from app.services.cadastro_publico_service import TERMOS_USO_VERSAO
from tests.test_demandas_auth import api, bearer, fake_db, make_token, make_user  # noqa: F401


def test_diagnostico_nao_expoe_segredos():
    config = Settings(_env_file=None, SMTP_PASSWORD="minha_senha_sensivel",
                      TURNSTILE_SECRET_KEY="segredo_sensivel", PUBLIC_SIGNUP_ENABLED=True)
    pendencias = cadastro_configuracao_pendente(config)
    assert "SMTP_PASSWORD" not in pendencias
    assert "TURNSTILE_SECRET_KEY" not in pendencias
    assert "SMTP_HOST" in pendencias
    assert "TURNSTILE_SITE_KEY" in pendencias
    assert "PUBLIC_APP_BASE_URL" in pendencias
    assert "minha_senha_sensivel" not in str(pendencias)
    assert "segredo_sensivel" not in str(pendencias)


def cadastro_valido():
    return {
        "nome": "Cliente Novo", "email": "novo@example.com", "senha": "SenhaSegura123",
        "termos_aceitos": True, "termos_versao": TERMOS_USO_VERSAO,
    }


def test_conta_config_nao_expoe_segredos_e_vem_desativada(api):
    client, _, _settings = api
    result = client.get("/auth/conta/config")
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json() == {
        "cadastro_habilitado": False,
        "recuperacao_habilitada": False,
        "turnstile_site_key": "",
    }


def test_conta_config_habilita_auto_cadastro_quando_seguranca_esta_pronta(
    api, monkeypatch
):
    client, _, settings = api
    monkeypatch.setattr(settings, "PUBLIC_SIGNUP_ENABLED", True)
    monkeypatch.setattr(settings, "TURNSTILE_SITE_KEY", "site-publica")
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", SecretStr("nao-expor-este-segredo"))
    monkeypatch.setattr(settings, "TURNSTILE_EXPECTED_HOSTNAME", "automatize-dev-hml.pages.dev")
    monkeypatch.setattr("app.api.v1.endpoints.cadastro.EmailSender.ready", lambda _: True)
    result = client.get("/auth/conta/config")
    assert result.status_code == 200
    assert result.json() == {
        "cadastro_habilitado": True,
        "recuperacao_habilitada": False,
        "turnstile_site_key": "site-publica",
    }
    assert "nao-expor-este-segredo" not in result.text


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
    monkeypatch.setattr(settings, "TURNSTILE_SITE_KEY", "site-publica")
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

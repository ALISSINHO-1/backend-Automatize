from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core import security
from app.core.security import hash_password, verify_password
from app.core.database import get_db
from app.domain.models.user import User


_password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_PASSWORD = "senha correta"


class FakeSession:
    def __init__(self, user: User | None = None, error: Exception | None = None):
        self.user = user
        self.error = error

    def scalar(self, statement):
        if self.error:
            raise self.error
        return self.user

    def close(self):
        pass


def make_user(*, active: bool = True, password_hash: str | None = None) -> User:
    user = User()
    user.id = UUID("8e4a3846-2b52-4167-97e4-83eef0b25b33")
    user.nome = "Cliente Teste"
    user.email = "cliente@example.com"
    user.senha_hash = password_hash or _password_context.hash(_PASSWORD)
    user.ativo = active
    return user


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app.core.config import Settings
    from app.main import create_app

    configured_settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg2://unit:unit@localhost:5432/unit_test",
        JWT_SECRET_KEY="injected-login-secret-" + "x" * 32,
        ACCESS_TOKEN_EXPIRE_MINUTES=7,
    )
    application = create_app(configured_settings)
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client, application, configured_settings
    application.dependency_overrides.clear()


def set_session(application, session: FakeSession) -> None:
    def override_db():
        yield session

    application.dependency_overrides[get_db] = override_db


def login(client: TestClient, *, password: str = _PASSWORD):
    return client.post(
        "/auth/login",
        json={"email": "cliente@example.com", "senha": password},
    )


@pytest.mark.parametrize(
    "password",
    ["a" * 72, "é" * 36],
    ids=["72-ascii-bytes", "36-multibyte-characters-72-bytes"],
)
def test_hash_and_verification_accept_exactly_72_utf8_bytes(password):
    assert len(password.encode("utf-8")) == 72

    password_hash = hash_password(password)

    assert verify_password(password, password_hash)


@pytest.mark.parametrize("password", ["a" * 73, "é" * 37])
def test_hash_generation_rejects_more_than_72_utf8_bytes_before_bcrypt(
    password,
    monkeypatch,
):
    bcrypt_calls = []
    monkeypatch.setattr(
        security._password_context,
        "hash",
        lambda plain_password: bcrypt_calls.append(plain_password),
    )

    with pytest.raises(ValueError, match="72 bytes") as error:
        hash_password(password)

    assert bcrypt_calls == []
    assert password not in str(error.value)


def test_hashing_preserves_spaces_and_does_not_normalize_unicode():
    password = " caf\u00e9 "
    password_hash = hash_password(password)

    assert verify_password(password, password_hash)
    assert not verify_password(password.strip(), password_hash)
    assert not verify_password(" cafe\u0301 ", password_hash)


@pytest.mark.parametrize(
    "password",
    ["a" * 73, "a" * 72 + "suffix", "é" * 37],
    ids=["73-ascii-bytes", "same-72-byte-prefix", "37-multibyte-characters"],
)
def test_login_rejects_password_over_72_bytes_and_runs_bounded_dummy_check(
    auth_client,
    monkeypatch,
    password,
):
    client, application, _ = auth_client
    prefix = "a" * 72
    user = make_user(password_hash=hash_password(prefix))
    set_session(application, FakeSession(user))

    calls = []
    original_verify = security._password_context.verify

    def track_verify(plain_password, stored_hash, *args, **kwargs):
        calls.append((plain_password, stored_hash))
        return original_verify(plain_password, stored_hash, *args, **kwargs)

    monkeypatch.setattr(security._password_context, "verify", track_verify)

    response = login(client, password=password)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert password not in response.text
    assert calls == [(security._DUMMY_PASSWORD, security._DUMMY_PASSWORD_HASH)]
    assert len(calls[0][0].encode("utf-8")) <= security.MAX_BCRYPT_PASSWORD_BYTES

    calls.clear()
    incorrect_password_response = login(client, password="senha errada")
    assert response.json() == incorrect_password_response.json()

def test_login_accepts_exactly_72_utf8_bytes(auth_client):
    client, application, _ = auth_client
    password = "é" * 36
    user = make_user(password_hash=hash_password(password))
    set_session(application, FakeSession(user))

    response = login(client, password=password)

    assert response.status_code == 200


def test_valid_login_returns_token_signed_with_injected_settings(auth_client):
    client, application, configured_settings = auth_client
    user = make_user()
    set_session(application, FakeSession(user))

    before = datetime.now(timezone.utc)
    response = login(client)
    after = datetime.now(timezone.utc)

    assert response.status_code == 200
    assert response.json().keys() == {"access_token", "token_type"}
    assert response.json()["token_type"] == "bearer"
    token = response.json()["access_token"]
    payload = jwt.decode(
        token,
        configured_settings.JWT_SECRET_KEY,
        algorithms=["HS256"],
    )
    assert payload["sub"] == str(user.id)
    assert UUID(payload["sub"]) == user.id
    issued_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    assert int(before.timestamp()) <= payload["iat"] <= int(after.timestamp())
    assert expires_at == issued_at + timedelta(minutes=7)
    with pytest.raises(JWTError):
        jwt.decode(token, "different-key" + "x" * 32, algorithms=["HS256"])
    assert not any(
        value in response.text
        for value in (user.senha_hash, _PASSWORD, configured_settings.JWT_SECRET_KEY)
    )


@pytest.mark.parametrize(
    ("user", "password"),
    [
        (make_user(), "senha errada"),
        (None, _PASSWORD),
        (make_user(active=False), _PASSWORD),
        (make_user(password_hash="hash-inválido"), _PASSWORD),
        (make_user(password_hash="$2b$12$short"), _PASSWORD),
    ],
    ids=[
        "wrong-password",
        "missing-user",
        "inactive-user",
        "unrecognized-hash",
        "malformed-bcrypt-hash",
    ],
)
def test_invalid_authentication_is_generic_and_does_not_leak(auth_client, user, password):
    client, application, _ = auth_client
    set_session(application, FakeSession(user))

    response = login(client, password=password)

    assert response.status_code == 401
    assert response.json() == {"detail": "Credenciais inválidas."}
    assert response.headers["www-authenticate"] == "Bearer"
    assert all(secret not in response.text for secret in (_PASSWORD, "hash-inválido"))


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"email": "cliente@example.com"},
        {"senha": _PASSWORD},
        {"email": "não-é-email", "senha": _PASSWORD},
        {"email": "cliente@example.com", "senha": ""},
        {"email": "cliente@example.com", "senha": _PASSWORD, "extra": "x"},
        {"email": "cliente@example.com", "senha": 123456789},
        {
            "email": "cliente@example.com",
            "senha": "validation-secret-" + ("x" * 1024),
        },
        {"email": "validation-secret@example", "senha": _PASSWORD},
    ],
)
def test_invalid_input_returns_422(auth_client, body):
    client, _, _ = auth_client
    response = client.post("/auth/login", json=body)

    assert response.status_code == 422
    assert all("input" not in issue for issue in response.json()["detail"])
    assert _PASSWORD not in response.text
    assert "validation-secret" not in response.text


def test_persistence_failure_is_not_mapped_to_invalid_credentials(auth_client):
    client, application, _ = auth_client
    set_session(application, FakeSession(error=RuntimeError("database-secret")))

    response = login(client)

    assert response.status_code == 500
    assert "database-secret" not in response.text
    assert response.status_code != 401


def test_login_contract_is_documented_in_openapi(auth_client):
    client, _, _ = auth_client
    operation = client.get("/openapi.json").json()["paths"]["/auth/login"]["post"]

    assert "200" in operation["responses"]
    assert "401" in operation["responses"]
    assert "422" in operation["responses"]
    assert "/api/v1/auth/login" not in client.get("/openapi.json").json()["paths"]

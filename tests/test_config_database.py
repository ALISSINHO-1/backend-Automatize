from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request

from app.core.config import Settings
from app.core.database import (
    create_database_engine,
    create_session_factory,
    get_db,
)


def settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "DATABASE_URL": "postgresql+psycopg2://unit:unit@localhost:5432/unit_test",
        "JWT_SECRET_KEY": "a" * 40,
    }
    values.update(overrides)
    return Settings(**values)


def test_database_url_is_required_for_application() -> None:
    configured = settings(DATABASE_URL=None)

    with pytest.raises(ValueError, match="DATABASE_URL é obrigatória") as error:
        configured.validate_application_configuration()

    assert "unit:unit" not in str(error.value)


@pytest.mark.parametrize(
    "database_url",
    [
        "",
        "sqlite:///local.db",
        "mysql+pymysql://user:password@localhost/app",
        "postgresql+asyncpg://user:password@localhost/app",
    ],
)
def test_database_url_requires_postgresql_psycopg2(database_url: str) -> None:
    configured = settings(DATABASE_URL=database_url)

    with pytest.raises(ValueError) as error:
        configured.validate_database_configuration()

    assert "password" not in str(error.value)
    assert "DATABASE_URL" in str(error.value)


def test_malformed_database_url_error_does_not_include_url() -> None:
    secret_url = "postgresql://private-user:private-password@host:badport/db"
    configured = settings(DATABASE_URL=secret_url)

    with pytest.raises(ValueError) as error:
        configured.validate_database_configuration()

    assert secret_url not in str(error.value)
    assert "private-password" not in str(error.value)


@pytest.mark.parametrize("secret", [None, "", "too-short", "SUBSTITUA_POR_CHAVE_GERADA_LOCALMENTE"])
def test_jwt_secret_is_required_long_and_not_a_placeholder(secret: str | None) -> None:
    configured = settings(JWT_SECRET_KEY=secret)

    with pytest.raises(ValueError, match="JWT_SECRET_KEY") as error:
        configured.validate_application_configuration()

    assert "too-short" not in str(error.value)
    assert "SUBSTITUA" not in str(error.value)


def test_jwt_configuration_and_token_expiration() -> None:
    configured = settings(
        JWT_ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=15,
    )
    configured.validate_application_configuration()

    assert configured.JWT_ALGORITHM == "HS256"
    assert configured.ACCESS_TOKEN_EXPIRE_MINUTES == 15

    with pytest.raises(ValueError, match="JWT_ALGORITHM"):
        settings(JWT_ALGORITHM="HS512")
    with pytest.raises(ValueError):
        settings(ACCESS_TOKEN_EXPIRE_MINUTES=0)


def test_injected_settings_create_engine_without_connecting() -> None:
    configured = settings(
        DATABASE_URL="postgresql+psycopg2://injected:secret@db.example:5432/injected_db"
    )

    engine = create_database_engine(configured)
    try:
        assert engine.url.drivername == "postgresql+psycopg2"
        assert engine.url.host == "db.example"
        assert engine.pool._pre_ping is True
        assert engine.hide_parameters is True
    finally:
        engine.dispose()


def test_database_url_is_hidden_from_settings_representation():
    configured = settings(DATABASE_URL="postgresql://private-user:private-password@localhost/db")
    assert "private-password" not in repr(configured)
    assert "private-user" not in repr(configured)


def test_remote_database_uses_tls_by_default_without_exposing_url():
    from sqlalchemy.engine import make_url
    configured = settings(DATABASE_URL="postgresql://unit:private@db.example/app")
    assert make_url(configured.validate_database_configuration()).query["sslmode"] == "require"


@pytest.mark.parametrize("sslmode", ["disable", "allow", "prefer", "invalid"])
def test_remote_database_rejects_plaintext_fallback(sslmode):
    configured = settings(DATABASE_URL=f"postgresql://unit:private@db.example/app?sslmode={sslmode}")
    with pytest.raises(ValueError) as error:
        configured.validate_database_configuration()
    assert "private" not in str(error.value)


@pytest.mark.parametrize("sslmode", ["require", "verify-ca", "verify-full"])
def test_explicit_secure_tls_configuration_is_preserved(sslmode):
    from sqlalchemy.engine import make_url
    url = f"postgresql://unit:private@db.example/app?sslmode={sslmode}"
    checked = make_url(settings(DATABASE_URL=url).validate_database_configuration())
    assert checked.query["sslmode"] == sslmode
    assert checked.query["gssencmode"] == "disable"
    assert checked.host == "db.example"


def test_local_development_database_does_not_require_tls():
    url = "postgresql://unit:private@localhost/app"
    assert settings(DATABASE_URL=url).validate_database_configuration() == url


def request_with_factory(factory) -> Request:
    application = FastAPI()
    application.state.session_factory = factory
    return Request({"type": "http", "app": application})


def test_get_db_closes_session_after_success_without_commit() -> None:
    session = MagicMock()
    dependency = get_db(request_with_factory(lambda: session))

    assert next(dependency) is session
    with pytest.raises(StopIteration):
        next(dependency)

    session.close.assert_called_once()
    session.commit.assert_not_called()


def test_get_db_closes_session_after_error_without_commit() -> None:
    session = MagicMock()
    dependency = get_db(request_with_factory(lambda: session))

    assert next(dependency) is session
    with pytest.raises(RuntimeError, match="request failed"):
        dependency.throw(RuntimeError("request failed"))

    session.close.assert_called_once()
    session.commit.assert_not_called()


def test_session_factory_uses_the_injected_engine() -> None:
    configured = settings()
    engine = create_database_engine(configured)
    try:
        factory = create_session_factory(engine)
        assert factory.kw["bind"] is engine
        assert factory.kw["autocommit"] is False
    finally:
        engine.dispose()

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_components(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from app.core.config import Settings
    from app.main import create_app

    return Settings, create_app


def valid_settings(Settings, **overrides):
    values = {
        "_env_file": None,
        "DATABASE_URL": "postgresql+psycopg2://unit:unit@localhost:5432/unit_test",
        "JWT_SECRET_KEY": "unit-test-secret-" + "x" * 32,
        "cors_origins": [],
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def client(app_components) -> Generator[TestClient, None, None]:
    Settings, create_app = app_components
    with TestClient(create_app(valid_settings(Settings))) as test_client:
        yield test_client


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_in_openapi(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "get" in response.json()["paths"]["/health"]


def test_domain_routers_have_expected_prefixes() -> None:
    from app.api.v1.endpoints.auth import router as auth_router
    from app.api.v1.endpoints.demandas import router as demandas_router
    from app.api.v1.endpoints.demandas_acoes import router as demandas_acoes_router
    from app.api.v1.router import endpoint_routers

    assert auth_router.prefix == "/auth"
    assert auth_router.tags == ["Autenticação"]
    assert demandas_router.prefix == "/demandas"
    assert demandas_router.tags == ["Demandas"]
    assert [route.path for route in auth_router.routes] == ["/auth/login"]
    assert [route.path for route in demandas_router.routes] == [
        "/demandas",
        "/demandas/{id}",
    ]
    assert endpoint_routers == (auth_router, demandas_router, demandas_acoes_router)
    assert demandas_acoes_router.prefix == "/demandas"


def test_settings_parse_json_cors_origins(monkeypatch, app_components) -> None:
    Settings, _ = app_components
    monkeypatch.setenv(
        "CORS_ORIGINS",
        '["http://localhost:3000","http://localhost:8080"]',
    )

    configured_settings = Settings(_env_file=None)

    assert configured_settings.cors_origins == [
        "http://localhost:3000",
        "http://localhost:8080",
    ]


def test_settings_reject_wildcard_cors_origin(app_components) -> None:
    Settings, _ = app_components

    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(_env_file=None, cors_origins=["*"])


def test_unconfigured_origin_is_not_authorized(app_components) -> None:
    Settings, create_app = app_components
    with TestClient(create_app(valid_settings(Settings))) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_configured_origin_is_authorized(app_components) -> None:
    Settings, create_app = app_components
    application_settings = valid_settings(
        Settings,
        cors_origins=["http://localhost:3000"],
    )
    with TestClient(create_app(application_settings)) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_health_does_not_open_a_database_connection(app_components, monkeypatch) -> None:
    Settings, create_app = app_components
    from sqlalchemy.engine import Engine

    def unexpected_connect(*args, **kwargs):
        raise AssertionError("health must not connect to PostgreSQL")

    monkeypatch.setattr(Engine, "connect", unexpected_connect)
    application = create_app(valid_settings(Settings))
    with TestClient(application) as test_client:
        assert test_client.get("/health").json() == {"status": "ok"}


def test_application_validates_required_settings_at_startup(app_components) -> None:
    Settings, create_app = app_components
    unconfigured = Settings(_env_file=None, DATABASE_URL=None, JWT_SECRET_KEY=None)

    with pytest.raises(ValueError, match="DATABASE_URL é obrigatória"):
        with TestClient(create_app(unconfigured)):
            pass

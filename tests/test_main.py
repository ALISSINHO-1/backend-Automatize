from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_components(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from app.core.config import Settings
    from app.main import create_app

    return Settings, create_app


@pytest.fixture
def client(app_components) -> Generator[TestClient, None, None]:
    Settings, create_app = app_components
    application = create_app(Settings(_env_file=None, cors_origins=[]))
    with TestClient(application) as test_client:
        yield test_client


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_in_openapi(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "get" in response.json()["paths"]["/health"]


def test_settings_parse_json_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
    app_components,
) -> None:
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

    with pytest.raises(ValueError, match=r"não pode conter '\*'"):
        Settings(_env_file=None, cors_origins=["*"])


def test_unconfigured_origin_is_not_authorized(app_components) -> None:
    Settings, create_app = app_components
    application = create_app(Settings(_env_file=None, cors_origins=[]))
    with TestClient(application) as client:
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
    application = create_app(
        Settings(
            _env_file=None,
            cors_origins=["http://localhost:3000"],
        )
    )
    with TestClient(application) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

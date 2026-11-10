from contextlib import asynccontextmanager
import logging
from urllib.parse import urlparse
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import router as api_v1_router
from app.core.config import Settings, settings
from app.core.database import create_database_engine, create_session_factory

logger = logging.getLogger(__name__)


def cadastro_configuracao_pendente(settings: Settings) -> list[str]:
    """Somente nomes das variáveis faltantes, jamais segredos ou dados pessoais."""
    campos = {
        "SMTP_HOST": settings.SMTP_HOST,
        "SMTP_USERNAME": settings.SMTP_USERNAME,
        "SMTP_PASSWORD": settings.SMTP_PASSWORD,
        "SMTP_FROM_EMAIL": settings.SMTP_FROM_EMAIL,
        "TURNSTILE_SITE_KEY": settings.TURNSTILE_SITE_KEY,
        "TURNSTILE_SECRET_KEY": settings.TURNSTILE_SECRET_KEY,
        "TURNSTILE_EXPECTED_HOSTNAME": settings.TURNSTILE_EXPECTED_HOSTNAME,
        "PUBLIC_APP_BASE_URL": settings.PUBLIC_APP_BASE_URL,
    }
    faltantes = [nome for nome, valor in campos.items() if not valor]
    app_url = settings.PUBLIC_APP_BASE_URL or ""
    if app_url:
        parsed = urlparse(app_url)
        if (parsed.scheme != "https" or not parsed.netloc or
                parsed.username or parsed.password or parsed.query or parsed.fragment):
            faltantes.append("PUBLIC_APP_BASE_URL_FORMATO")
    return faltantes



def create_app(app_settings: Settings | None = None) -> FastAPI:
    configured_settings = app_settings if app_settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configured_settings.validate_application_configuration()
        if configured_settings.PUBLIC_SIGNUP_ENABLED:
            pendencias = cadastro_configuracao_pendente(configured_settings)
            if pendencias:
                logger.warning("Cadastro publico indisponivel; revisar variaveis: %s",
                               ", ".join(pendencias))
            else:
                logger.info("Cadastro publico: parametros basicos presentes; teste de SMTP e Turnstile pendente")
        database_engine = create_database_engine(configured_settings)
        application.state.engine = database_engine
        application.state.session_factory = create_session_factory(database_engine)
        try:
            yield
        finally:
            database_engine.dispose()

    application = FastAPI(
        title="Automatize API",
        description="API para gestão de ordens de serviço, integração mobile e homologação formal.",
        version="1.0.0",
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        # Pydantic's default error payload includes the rejected input. That can
        # disclose passwords (or other secrets) sent to the login endpoint.
        safe_errors = [
            {
                key: item[key]
                for key in ("type", "loc", "msg")
                if key in item
            }
            for item in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})

    application.state.settings = configured_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_v1_router)

    @application.get("/", tags=["Root"])
    def read_root() -> dict[str, str]:
        return {
            "message": "Automatize API",
            "sistema": "Automatize API",
            "status": "Online",
            "docs": "/docs",
        }

    @application.get(
        "/health",
        tags=["Health"],
        summary="Verifica se a aplicação está ativa",
        description="Verificação de que a aplicação está ativa.",
    )
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app(settings)

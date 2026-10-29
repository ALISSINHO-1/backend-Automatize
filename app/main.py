from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import router as api_v1_router
from app.api.openapi import DESCRIPTION, TAGS
from app.core.config import Settings, settings
from app.core.database import create_database_engine, create_session_factory


def create_app(app_settings: Settings | None = None) -> FastAPI:
    configured_settings = app_settings if app_settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configured_settings.validate_application_configuration()
        database_engine = create_database_engine(configured_settings)
        application.state.engine = database_engine
        application.state.session_factory = create_session_factory(database_engine)
        try:
            yield
        finally:
            database_engine.dispose()

    application = FastAPI(
        title="Automatize API",
        description=DESCRIPTION,
        openapi_tags=TAGS,
        swagger_ui_parameters={
            "docExpansion": "none", "filter": True, "displayRequestDuration": True,
            "defaultModelsExpandDepth": -1, "syntaxHighlight.theme": "obsidian",
            "persistAuthorization": False,
        },
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
        expose_headers=["X-Total-Count", "X-Counts-By-Status"],
    )
    application.include_router(api_v1_router)

    @application.get("/", tags=["Sistema"], summary="Identifica a API")
    def read_root() -> dict[str, str]:
        return {
            "message": "Automatize API",
            "sistema": "Automatize API",
            "status": "Online",
            "docs": "/docs",
        }

    @application.get(
        "/health",
        tags=["Sistema"],
        summary="Verifica se a aplicação está ativa",
        description="Verificação de que a aplicação está ativa.",
    )
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app(settings)

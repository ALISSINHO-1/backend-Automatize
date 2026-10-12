from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router
from app.core.config import Settings, settings


def create_app(app_settings: Settings | None = None) -> FastAPI:
    configured_settings = app_settings or Settings()

    application = FastAPI(title="Automatize API")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_v1_router, prefix="/api/v1")

    @application.get("/", tags=["Root"])
    def read_root() -> dict[str, str]:
        return {"message": "Automatize API"}

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

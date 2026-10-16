from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


_JWT_PLACEHOLDERS = {
    "change-me",
    "replace-me",
    "your-secret-key",
    "your-jwt-secret-key",
    "placeholder",
}


def validate_database_url(value: str | None) -> str:
    """Validate a PostgreSQL URL without opening a connection or exposing it."""
    if not value or not value.strip():
        raise ValueError("DATABASE_URL é obrigatória.")

    try:
        parsed = make_url(value)
    except Exception:
        raise ValueError(
            "DATABASE_URL inválida; informe uma URL PostgreSQL com psycopg2."
        ) from None

    if parsed.drivername not in {"postgresql", "postgresql+psycopg2"}:
        raise ValueError("DATABASE_URL deve usar PostgreSQL com o driver psycopg2.")
    if not parsed.database:
        raise ValueError("DATABASE_URL deve informar o banco de dados.")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    DATABASE_URL: str | None = None
    STORAGE_BUCKET_NAME: str = "evidencias-anexos"
    cors_origins: list[str] = Field(default_factory=list, validation_alias="CORS_ORIGINS")
    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_cors_origin(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError(
                "CORS_ORIGINS não pode conter '*' quando credenciais estão habilitadas."
            )
        return origins

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def restrict_jwt_algorithm(cls, algorithm: str) -> str:
        if algorithm != "HS256":
            raise ValueError("JWT_ALGORITHM deve ser HS256 nesta etapa.")
        return algorithm

    def validate_database_configuration(self) -> str:
        """Validate only database settings, for Alembic and database utilities."""
        return validate_database_url(self.DATABASE_URL)

    def validate_application_configuration(self) -> None:
        """Validate settings required to start the API; this never connects."""
        self.validate_database_configuration()
        if not self.JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY é obrigatória.")
        if len(self.JWT_SECRET_KEY.strip()) < 32:
            raise ValueError("JWT_SECRET_KEY deve ter pelo menos 32 caracteres.")
        if (
            self.JWT_SECRET_KEY.strip().lower() in _JWT_PLACEHOLDERS
            or self.JWT_SECRET_KEY.strip().lower().startswith("substitua_")
        ):
            raise ValueError("JWT_SECRET_KEY não pode usar um placeholder.")


settings = Settings()

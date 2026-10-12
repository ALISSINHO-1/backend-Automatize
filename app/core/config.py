from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    DATABASE_URL: str = ""
    STORAGE_BUCKET_NAME: str = "evidencias-anexos"
    cors_origins: list[str] = Field(default_factory=list)

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_cors_origin(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError(
                "CORS_ORIGINS não pode conter '*' quando credenciais estão habilitadas."
            )
        return origins


settings = Settings()

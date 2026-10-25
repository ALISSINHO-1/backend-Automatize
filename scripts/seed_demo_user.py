"""Run manually with `python -m scripts.seed_demo_user` against a dev database."""

import sys

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import create_database_engine, create_session_factory
from app.core.security import hash_password, password_exceeds_bcrypt_limit
from app.domain.models.enums import PerfilEnum
from app.domain.models.user import User
from app.domain.schemas.auth_schema import LoginRequest
from app.repositories.user_repository import UserRepository


class DemoUserSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        hide_input_in_errors=True,
    )

    DEMO_USER_NAME: str = Field(min_length=1, max_length=255)
    DEMO_USER_EMAIL: str = Field(min_length=3, max_length=255)
    DEMO_USER_PASSWORD: SecretStr

    @field_validator("DEMO_USER_NAME")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("DEMO_USER_NAME não pode ser vazio.")
        return value

    @field_validator("DEMO_USER_EMAIL")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return LoginRequest.validate_email_shape(value)

    @field_validator("DEMO_USER_PASSWORD")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        plain = value.get_secret_value()
        if not plain or password_exceeds_bcrypt_limit(plain):
            raise ValueError("DEMO_USER_PASSWORD deve ter de 1 a 72 bytes UTF-8.")
        return value


def seed_demo_user(db: Session, demo: DemoUserSettings) -> tuple[User, bool]:
    """Create a CLIENTE once. Existing accounts and passwords remain untouched."""
    repository = UserRepository(db)
    existing = repository.get_by_email(demo.DEMO_USER_EMAIL)
    if existing is not None:
        return existing, False

    try:
        user = repository.create({
            "nome": demo.DEMO_USER_NAME,
            "email": demo.DEMO_USER_EMAIL,
            "senha_hash": hash_password(demo.DEMO_USER_PASSWORD.get_secret_value()),
            "perfil": PerfilEnum.CLIENTE,
            "ativo": True,
        })
        db.commit()
    except IntegrityError:
        db.rollback()
        # Another invocation may have won the unique-email race.
        existing = repository.get_by_email(demo.DEMO_USER_EMAIL)
        if existing is None:
            raise
        return existing, False
    except Exception:
        db.rollback()
        raise
    return user, True


def main() -> int:
    engine = None
    try:
        demo = DemoUserSettings()
        engine = create_database_engine(Settings())
        with create_session_factory(engine)() as db:
            _, created = seed_demo_user(db, demo)
        print("Usuário de demonstração criado." if created else
              "E-mail já cadastrado; conta existente preservada.")
        return 0
    except Exception:
        print("Seed não concluído. Verifique a configuração e o banco de desenvolvimento.",
              file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

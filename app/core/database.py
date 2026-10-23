from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import Settings


# Keep one metadata registry for every model, including imports made by Alembic.
Base = declarative_base()

# These names remain available for existing imports. Applications bind their own
# factory from their injected Settings during startup.
engine: Engine | None = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def create_database_engine(configured_settings: Settings) -> Engine:
    database_url = configured_settings.validate_database_configuration()
    return create_engine(database_url, pool_pre_ping=True)


def create_session_factory(database_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=database_engine,
    )


def get_db(request: Request) -> Generator[Session, None, None]:
    """Yield one request session and always close it, without committing."""
    factory = (
        getattr(request.app.state, "session_factory", SessionLocal)
    )
    db = factory()
    try:
        yield db
    finally:
        db.close()

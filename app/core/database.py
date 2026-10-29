from collections.abc import Generator
from collections.abc import Mapping
from typing import Any

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import Settings
from app.core.postgres_tls import parameters_from_url, secure_connect_parameters
from sqlalchemy.engine import make_url


# Keep one metadata registry for every model, including imports made by Alembic.
Base = declarative_base()

# These names remain available for existing imports. Applications bind their own
# factory from their injected Settings during startup.
engine: Engine | None = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def create_database_engine(
    configured_settings: Settings,
    *,
    connect_args: Mapping[str, Any] | None = None,
) -> Engine:
    database_url = make_url(configured_settings.validate_database_configuration())
    # Keep the declared psycopg2 contract even when SQLAlchemy changes defaults.
    if database_url.drivername == "postgresql":
        database_url = database_url.set(drivername="postgresql+psycopg2")
    effective = parameters_from_url(make_url(database_url))
    effective.update(connect_args or {})
    checked = secure_connect_parameters(effective)
    engine = create_engine(
        database_url, pool_pre_ping=True, hide_parameters=True, connect_args=checked
    )

    @event.listens_for(engine, "do_connect")
    def validate_final_driver_parameters(dialect, connection_record, cargs, cparams):
        if cargs:
            raise ValueError("DSN posicional PostgreSQL não permitido.")
        checked_final = secure_connect_parameters(cparams)
        cparams.clear()
        cparams.update(checked_final)

    return engine


def create_session_factory(database_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=database_engine,
    )


def get_db(request: Request) -> Generator[Session, None, None]:
    """Yield one request session and always close it, without committing."""
    factory = getattr(request.app.state, "session_factory", SessionLocal)
    db = factory()
    try:
        yield db
    finally:
        db.close()

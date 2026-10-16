"""Check PostgreSQL connectivity only when run as a script."""

import sys

from sqlalchemy import create_engine, text

from app.core.config import Settings


def main() -> int:
    engine = None
    try:
        configured_settings = Settings()
        database_url = configured_settings.validate_database_configuration()
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("Conexão PostgreSQL verificada com SELECT 1.")
        return 0
    except Exception:
        print(
            "Falha na verificação PostgreSQL. Confira DATABASE_URL e a disponibilidade do banco.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

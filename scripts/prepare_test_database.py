"""Cria apenas os papeis Supabase de teste em PostgreSQL LOCAL descartavel."""
import os

from sqlalchemy import create_engine

from scripts.isolated_database import require_isolated_database


def main():
    url = require_isolated_database(os.environ["TEST_DATABASE_URL"])
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.begin() as db:
            db.exec_driver_sql("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
                        CREATE ROLE anon NOLOGIN;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
                        CREATE ROLE authenticated NOLOGIN;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
                        CREATE ROLE service_role NOLOGIN BYPASSRLS;
                    END IF;
                END $$
            """)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

"""Regression checks for the three previously exposed public tables.

Run only with an isolated PostgreSQL test database prepared by the CI fixture.
These tests do not modify Supabase shared environments.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

TABLES = ("etapas_operacionais", "historico_status_pedidos", "alembic_version")
CLIENT_ROLES = ("anon", "authenticated")


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("role", CLIENT_ROLES)
def test_internal_tables_are_not_accessible_by_data_api_roles(engine, table, role):
    with engine.connect() as connection:
        row = connection.execute(
            text("""
                SELECT c.relrowsecurity AS rls,
                       has_table_privilege(:role, c.oid,
                           'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS table_grants,
                       has_any_column_privilege(:role, c.oid,
                           'SELECT,INSERT,UPDATE,REFERENCES') AS column_grants
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relname = :table
            """),
            {"role": role, "table": table},
        ).mappings().one()
        assert row["rls"] is True
        assert row["table_grants"] is False
        assert row["column_grants"] is False

    with engine.connect() as connection:
        connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
        with pytest.raises(DBAPIError) as error:
            connection.exec_driver_sql(f"SELECT * FROM public.{table} LIMIT 1")
        assert getattr(error.value.orig, "pgcode", None) == "42501"


def test_backend_sql_role_retains_reads_and_alembic_version_write(engine):
    """A rolled-back no-op UPDATE verifies the migrator's SQL privileges."""
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            for table in TABLES:
                connection.exec_driver_sql(f"SELECT * FROM public.{table} LIMIT 0")
            connection.exec_driver_sql(
                "UPDATE public.alembic_version SET version_num = version_num"
            )
        finally:
            transaction.rollback()

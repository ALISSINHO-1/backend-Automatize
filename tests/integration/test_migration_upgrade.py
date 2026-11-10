from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.infrastructure.database.data_api_security import PROTECTED_TABLES
from scripts.isolated_database import require_isolated_database
from tests.integration.conftest import ROOT


def fresh_database(engine):
    require_isolated_database(engine.url.render_as_string(hide_password=False))
    name = f"audit_{uuid4().hex}_test"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.exec_driver_sql(f'CREATE DATABASE "{name}"')
    return create_engine(engine.url.set(database=name), hide_parameters=True)


def upgrade(engine, monkeypatch, revision="head", *, driver="postgresql+psycopg2"):
    monkeypatch.setenv("DATABASE_URL", engine.url.set(drivername=driver).render_as_string(hide_password=False))
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(config, revision)
    return config


@pytest.mark.parametrize("driver", ["postgresql", "postgresql+psycopg2"])
def test_upgrade_existing_schema_revokes_real_table_and_column_grants(engine, monkeypatch, driver):
    scratch = fresh_database(engine)
    try:
        # Exercise Alembic with both accepted URL forms against an empty DB.
        upgrade(scratch, monkeypatch, "3c9e7a1b5d20", driver=driver)
        with scratch.begin() as c:
            c.exec_driver_sql("GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role")
            c.exec_driver_sql("GRANT ALL ON ALL TABLES IN SCHEMA public TO anon,authenticated,service_role")
            c.exec_driver_sql("GRANT SELECT(nome) ON public.users TO PUBLIC")
            c.exec_driver_sql("INSERT INTO public.users (nome,email,senha_hash) VALUES ('Synthetic','upgrade@test.invalid','unused')")
        config = upgrade(scratch, monkeypatch, driver=driver)
        command.check(config)
        with scratch.connect() as c:
            assert c.exec_driver_sql("SELECT count(*) FROM public.users").scalar_one() == 1
            assert c.exec_driver_sql("SELECT version_num FROM public.alembic_version").scalar_one() == "fe53b5e9c102"
            for table in PROTECTED_TABLES:
                service_role_leitura = c.execute(
                    text("SELECT has_table_privilege('service_role',:table,'SELECT')"),
                    {"table": f"public.{table}"},
                ).scalar_one()
                assert service_role_leitura == (table not in {"chat_mensagens", "movimentos_quadro"})
                for role in ("anon", "authenticated"):
                    params = {"role": role, "table": f"public.{table}"}
                    assert not c.execute(text("SELECT has_table_privilege(:role,:table,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"), params).scalar_one()
                    assert not c.execute(text("SELECT has_any_column_privilege(:role,:table,'SELECT,INSERT,UPDATE,REFERENCES')"), params).scalar_one()
    finally:
        scratch.dispose()

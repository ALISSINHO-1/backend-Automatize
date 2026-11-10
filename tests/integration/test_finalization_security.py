"""Additional invariants for SCRUM-82/103 and complete restore evidence."""
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.infrastructure.database.data_api_security import IncompleteVisibilityError, PROTECTED_TABLES
from scripts.audit_technical_state import inspect_catalog
from scripts.validate_hml_restore import fingerprint
from tests.integration.test_demand_service_db import atores, demanda, service  # noqa: F401
from tests.integration.test_concurrency_postgres import committed_order  # noqa: F401
from tests.integration.test_migration_upgrade import fresh_database, upgrade


INSERT = text("""
    INSERT INTO public.aceites_formais
      (pedido_id,cliente_id,versao_entregavel,declaracao_aceite,hash_validacao)
    VALUES (:pedido,:cliente,:versao,:declaracao,:hash)
""")


def acceptance(pedido_id, cliente_id, **changes):
    return dict(pedido=pedido_id, cliente=cliente_id, versao="v1",
                declaracao="Aceite sintético para teste", hash="synthetic", **changes)


def test_postgres_recusa_aceite_de_outro_cliente(db, atores, demanda):
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(INSERT, acceptance(demanda.id, atores["outro_cliente"].id))
    assert error.value.orig.pgcode == "23503"
    assert error.value.orig.diag.constraint_name == "fk_aceites_formais_pedido_cliente"


@pytest.mark.parametrize("campo", ["versao", "declaracao", "hash"])
@pytest.mark.parametrize("valor", ["", " \t\n"])
def test_postgres_recusa_conteudo_aceite_vazio(db, atores, demanda, campo, valor):
    values = acceptance(demanda.id, atores["cliente"].id)
    values[campo] = valor
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(INSERT, values)
    assert error.value.orig.pgcode == "23514"


def test_cliente_da_evidencia_nao_pode_ser_trocado_antes_da_conclusao(db, atores, demanda):
    db.execute(INSERT, acceptance(demanda.id, atores["cliente"].id))
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(text("UPDATE public.pedidos SET cliente_id=:other WHERE id=:pedido"),
                       {"other": atores["outro_cliente"].id, "pedido": demanda.id})
    assert error.value.orig.pgcode == "23503"


@pytest.mark.parametrize("inconsistencia", ["cliente", "conteudo"])
def test_migration_interrompe_legado_invalido_sem_reparar_registros(engine, monkeypatch, inconsistencia):
    scratch = fresh_database(engine)
    try:
        upgrade(scratch, monkeypatch, "84db17ce9f26")
        owner, other, pedido = uuid4(), uuid4(), uuid4()
        with scratch.begin() as connection:
            for user in (owner, other):
                connection.execute(text("INSERT INTO public.users(id,nome,email,senha_hash) VALUES (:id,'Synthetic',:email,'unused')"),
                                   {"id": user, "email": f"{user}@test.invalid"})
            connection.execute(text("INSERT INTO public.pedidos(id,codigo_identificador,titulo,cliente_id) VALUES (:id,:code,'Synthetic',:owner)"),
                               {"id": pedido, "code": str(pedido), "owner": owner})
            values = acceptance(pedido, other if inconsistencia == "cliente" else owner)
            if inconsistencia == "conteudo":
                values["declaracao"] = " "
            connection.execute(INSERT, values)
        with pytest.raises(DBAPIError) as error:
            upgrade(scratch, monkeypatch)
        assert error.value.orig.pgcode == "23514"
        with scratch.connect() as connection:
            assert connection.exec_driver_sql("SELECT version_num FROM public.alembic_version").scalar_one() == "84db17ce9f26"
            assert connection.exec_driver_sql("SELECT count(*) FROM public.aceites_formais").scalar_one() == 1
            assert "uq_pedidos_id_cliente_id" not in {c["name"] for c in inspect(connection).get_unique_constraints("pedidos")}
    finally:
        scratch.dispose()


def test_migration_da_head_integrada_preserva_aceite_e_auditoria_validos(engine, monkeypatch):
    scratch = fresh_database(engine)
    try:
        upgrade(scratch, monkeypatch, "84db17ce9f26")
        owner, pedido = uuid4(), uuid4()
        with scratch.begin() as connection:
            connection.execute(text("INSERT INTO public.users(id,nome,email,senha_hash) VALUES (:id,'Synthetic',:email,'unused')"),
                               {"id": owner, "email": f"{owner}@test.invalid"})
            connection.execute(text("INSERT INTO public.pedidos(id,codigo_identificador,titulo,cliente_id) VALUES (:id,:code,'Synthetic',:owner)"),
                               {"id": pedido, "code": str(pedido), "owner": owner})
            connection.execute(INSERT, acceptance(pedido, owner))
            connection.execute(text("INSERT INTO public.auditoria_logs(usuario_id,pedido_id,acao) VALUES (:owner,:pedido,'SYNTHETIC_LEGACY')"),
                               {"owner": owner, "pedido": pedido})
        config = upgrade(scratch, monkeypatch)
        command.check(config)
        with scratch.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM public.aceites_formais").scalar_one() == 1
            assert connection.exec_driver_sql("SELECT count(*) FROM public.auditoria_logs").scalar_one() == 1
            assert connection.exec_driver_sql("SELECT convalidated FROM pg_constraint WHERE conname='fk_aceites_formais_pedido_cliente'").scalar_one()
    finally:
        scratch.dispose()


@pytest.mark.parametrize("table", ["chat_mensagens", "movimentos_quadro"])
def test_backup_inclui_e_detecta_mudanca_em_tabelas_integradas(engine, monkeypatch, table):
    # Independent commits belong in a private scratch DB, never in the shared
    # fixture DB where existing regressions legitimately expect an empty audit.
    database = fresh_database(engine)
    try:
        upgrade(database, monkeypatch)
        owner, pedido_id = uuid4(), uuid4()
        with database.begin() as connection:
            connection.execute(text("INSERT INTO public.users(id,nome,email,senha_hash) VALUES (:id,'Synthetic',:email,'unused')"),
                               {"id": owner, "email": f"{owner}@test.invalid"})
            connection.execute(text("INSERT INTO public.pedidos(id,codigo_identificador,titulo,cliente_id) VALUES (:id,:code,'Synthetic',:owner)"),
                               {"id": pedido_id, "code": str(pedido_id), "owner": owner})
            if table == "chat_mensagens":
                connection.execute(text("INSERT INTO public.chat_mensagens(id,pedido_id,autor_id,canal,texto) VALUES (:id,:pedido,:autor,'interno','Synthetic')"),
                                   {"id": uuid4(), "pedido": pedido_id, "autor": owner})
            else:
                connection.execute(text("INSERT INTO public.movimentos_quadro(id,conteudo_cifrado) VALUES (:id,:content)"),
                                   {"id": uuid4(), "content": b"synthetic ciphertext"})
        before = fingerprint(database)
        assert set(before) == set(PROTECTED_TABLES)
        assert before[table][0] > 0
        with database.begin() as connection:
            if table == "chat_mensagens":
                connection.exec_driver_sql("UPDATE public.chat_mensagens SET texto='Changed'")
            else:
                connection.exec_driver_sql("UPDATE public.movimentos_quadro SET conteudo_cifrado=decode('0001','hex')")
        assert before[table] != fingerprint(database)[table]
    finally:
        database.dispose()


@pytest.mark.parametrize("table", ["chat_mensagens", "movimentos_quadro"])
@pytest.mark.parametrize("column_grant", [False, True])
def test_auditoria_de_public_inclui_tabelas_integradas(engine, table, column_grant):
    with engine.connect() as connection:
        grant = "SELECT(id)" if column_grant else "SELECT"
        connection.exec_driver_sql(f"GRANT {grant} ON public.{table} TO PUBLIC")
        connection.commit()
        try:
            report = inspect_catalog(connection, "synthetic-unconfigured-bucket")
            rows = report["public_column_grants" if column_grant else "public_grants"]
            assert any(row["table_name"] == table for row in rows)
        finally:
            connection.rollback()
            connection.exec_driver_sql(f"REVOKE {grant} ON public.{table} FROM PUBLIC")
            connection.commit()


def test_backup_recusa_visibilidade_filtrada_por_rls(engine):
    from unittest.mock import Mock
    with engine.connect() as connection:
        role = f"backup_filtered_{uuid4().hex}"
        connection.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN NOBYPASSRLS")
        connection.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {role}")
        connection.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}")
        connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
        with pytest.raises(IncompleteVisibilityError):
            fingerprint(Mock(connect=lambda: connection))


def test_fk_serializa_troca_concorrente_do_cliente(engine, committed_order):
    _, owner, pedido = committed_order
    with engine.connect() as acceptance_writer, engine.connect() as reassignment:
        acceptance_writer.execute(INSERT, acceptance(pedido, owner))
        reassignment.exec_driver_sql("SET LOCAL lock_timeout='200ms'")
        with pytest.raises(DBAPIError) as error:
            reassignment.execute(text("UPDATE public.pedidos SET cliente_id=:other WHERE id=:pedido"),
                                 {"other": uuid4(), "pedido": pedido})
        assert error.value.orig.pgcode == "55P03"
        reassignment.rollback()
        acceptance_writer.rollback()


def test_grant_herdado_interrompe_hardening_sem_remover_membership(engine, monkeypatch):
    database = fresh_database(engine)
    role = f"legacy_reader_{uuid4().hex}"
    try:
        upgrade(database, monkeypatch, "7b2d4e6f8a10")
        with database.begin() as connection:
            connection.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN")
            connection.exec_driver_sql(f"GRANT SELECT ON public.users TO {role}")
            connection.exec_driver_sql(f"GRANT {role} TO anon")
        with pytest.raises(DBAPIError) as error:
            upgrade(database, monkeypatch)
        assert error.value.orig.pgcode == "P0001"
        with database.connect() as connection:
            assert connection.exec_driver_sql("SELECT version_num FROM public.alembic_version").scalar_one() == "7b2d4e6f8a10"
            assert connection.execute(text("SELECT pg_has_role('anon',:role,'MEMBER')"), {"role": role}).scalar_one()
    finally:
        with database.begin() as connection:
            connection.exec_driver_sql(f"REVOKE {role} FROM anon")
            connection.exec_driver_sql(f"REVOKE SELECT ON public.users FROM {role}")
            connection.exec_driver_sql(f"DROP ROLE {role}")
        database.dispose()

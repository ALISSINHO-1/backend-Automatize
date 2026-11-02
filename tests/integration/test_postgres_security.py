import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.infrastructure.database.data_api_security import PROTECTED_TABLES
from tests.integration.test_demand_service_db import (  # noqa: F401
    atores, demanda, service, _concluida,
)
from tests.integration.test_concurrency_postgres import committed_order  # noqa: F401


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("table", PROTECTED_TABLES)
def test_domain_grants_are_closed_and_rls_enabled(engine, role, table):
    with engine.connect() as connection:
        flags = connection.execute(text("""
            SELECT c.relrowsecurity,
                has_table_privilege(:role,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') AS any_grant,
                has_any_column_privilege(:role,c.oid,'SELECT,INSERT,UPDATE,REFERENCES') AS column_grant
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname=:table
        """), {"role": role, "table": table}).mappings().one()
        assert flags["relrowsecurity"] is True
        assert not flags["any_grant"] and not flags["column_grant"]
    for statement in (f'SELECT * FROM public.{table}',
                      f'INSERT INTO public.{table} DEFAULT VALUES',
                      f'DELETE FROM public.{table} WHERE false',
                      f'UPDATE public.{table} SET ' + ('version_num=version_num' if table == 'alembic_version' else 'id=id') + ' WHERE false'):
        with engine.connect() as connection:
            connection.exec_driver_sql(f'SET LOCAL ROLE {role}')
            with pytest.raises(DBAPIError) as error:
                connection.exec_driver_sql(statement)
            assert error.value.orig.pgcode == "42501"
    # RLS and row triggers do not protect TRUNCATE or ownership operations.
    # These attempts run only through the guarded disposable engine fixture.
    for statement in (f'TRUNCATE TABLE public.{table}',
                      f'ALTER TABLE public.{table} ADD COLUMN security_probe integer'):
        with engine.connect() as connection:
            connection.exec_driver_sql(f'SET LOCAL ROLE {role}')
            with pytest.raises(DBAPIError) as error:
                connection.exec_driver_sql(statement)
            assert error.value.orig.pgcode == "42501"


def test_trigger_functions_have_safe_paths_and_are_not_definer(engine):
    with engine.connect() as c:
        rows = c.exec_driver_sql("""
            SELECT p.proname,p.proconfig,p.prosecdef,
                has_function_privilege('anon',p.oid,'EXECUTE') AS anon,
                has_function_privilege('authenticated',p.oid,'EXECUTE') AS authenticated
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='public' AND p.proname IN
                ('bloquear_alteracao_aceite_formal','proteger_conclusao_pedido','proteger_auditoria_log')
        """).mappings().all()
        assert len(rows) == 3
        for row in rows:
            assert row["proconfig"] == ["search_path=pg_catalog, pg_temp"]
            assert not row["prosecdef"] and not row["anon"] and not row["authenticated"]


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("function", ["bloquear_alteracao_aceite_formal", "proteger_conclusao_pedido", "proteger_auditoria_log"])
def test_client_roles_cannot_execute_protected_trigger_functions(engine, role, function):
    with engine.connect() as connection:
        connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
        with pytest.raises(DBAPIError) as error:
            connection.exec_driver_sql(f"SELECT public.{function}()")
        assert error.value.orig.pgcode == "42501"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_rls_denies_existing_rows_even_if_select_is_temporarily_granted(engine, committed_order, role):
    _, _, order_id = committed_order
    with engine.connect() as c:
        transaction = c.begin()
        try:
            assert c.execute(text("SELECT count(*) FROM public.pedidos WHERE id=:id"), {"id": order_id}).scalar_one() == 1
            c.exec_driver_sql(f"GRANT SELECT ON public.pedidos TO {role}")
            c.exec_driver_sql(f"SET LOCAL ROLE {role}")
            assert c.execute(text("SELECT count(*) FROM public.pedidos WHERE id=:id"), {"id": order_id}).scalar_one() == 0
        finally:
            transaction.rollback()


def test_temp_shadow_acceptance_cannot_allow_completion(db, demanda):
    # A temporary relation named aceites_formais used to shadow the public
    # table in an invoker function with mutable search_path.
    db.execute(text("CREATE TEMP TABLE aceites_formais (pedido_id uuid) ON COMMIT DROP"))
    db.execute(text("INSERT INTO pg_temp.aceites_formais VALUES (:id)"), {"id": demanda.id})
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(text("UPDATE public.pedidos SET status='CONCLUIDO' WHERE id=:id"), {"id": demanda.id})
    assert error.value.orig.pgcode == "23001"


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_formal_acceptance_is_immutable_under_hostile_search_path(db, service, atores, demanda, operation):
    _concluida(service, atores, demanda)
    db.execute(text("SET LOCAL search_path=pg_temp,public,pg_catalog"))
    sql = ("UPDATE public.aceites_formais SET declaracao_aceite='tampered' WHERE pedido_id=:id"
           if operation == "UPDATE" else "DELETE FROM public.aceites_formais WHERE pedido_id=:id")
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(text(sql), {"id": demanda.id})
    assert error.value.orig.pgcode == "23001"


@pytest.mark.parametrize("sql", [
    "UPDATE public.auditoria_logs SET acao='AUDIT_PROBE' WHERE pedido_id=:id",
    "UPDATE public.auditoria_logs SET usuario_id=NULL WHERE pedido_id=:id",
    "DELETE FROM public.auditoria_logs WHERE pedido_id=:id",
])
def test_audit_payloads_cannot_be_changed_or_deleted(db, demanda, sql):
    with pytest.raises(DBAPIError) as error:
        with db.begin_nested():
            db.execute(text(sql), {"id": demanda.id})
    assert error.value.orig.pgcode == "23001"


def test_audit_retains_payload_when_order_fk_is_detached(db, service, atores, demanda):
    from app.domain.models import AuditoriaLog
    from sqlalchemy import select
    order_id = demanda.id
    before = {row.id: (row.acao, row.detalhes, row.created_at) for row in db.scalars(
        select(AuditoriaLog).where(AuditoriaLog.pedido_id == order_id)
    )}
    service.excluir(atores["admin"], order_id)
    db.expire_all()
    for log_id, payload in before.items():
        saved = db.get(AuditoriaLog, log_id)
        assert saved.pedido_id is None
        assert (saved.acao, saved.detalhes, saved.created_at) == payload

"""Least-privilege runtime proposal, exercised only in the disposable cluster."""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.exceptions import TransicaoEstadoInvalidaException
from app.domain.models.enums import StatusPedidoEnum as Status
from app.infrastructure.database.data_api_security import DOMAIN_TABLES
from scripts.audit_technical_state import inspect_catalog
from tests.integration.test_demand_service_db import atores, demanda, service  # noqa: F401


@pytest.fixture
def runtime_db(db, demanda):
    # Role and grants are transactional and rolled back with the existing db
    # fixture. No production role, password, owner or membership is modified.
    role = f"runtime_{uuid4().hex}"
    db.execute(text(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS"))
    db.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
    evidence = {"aceites_formais", "auditoria_logs", "historico_status_pedidos"}
    for table in DOMAIN_TABLES:
        privileges = "SELECT,INSERT" if table in evidence else "SELECT,INSERT,UPDATE,DELETE"
        db.execute(text(f"GRANT {privileges} ON TABLE public.{table} TO {role}"))
    db.execute(text(f"SET LOCAL ROLE {role}"))
    yield db


def test_restricted_runtime_preserves_the_existing_lifecycle(runtime_db, service, atores, demanda):
    flags = runtime_db.execute(text(
        "SELECT rolsuper,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user"
    )).one()
    assert not any(flags)
    assert runtime_db.execute(text("SELECT has_schema_privilege(current_user,'public','CREATE')")).scalar_one() is False
    service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)
    with pytest.raises(TransicaoEstadoInvalidaException):
        service.alterar_status(atores["tecnico"], demanda.id, Status.HOMOLOGACAO)
    stage = service.adicionar_etapa(atores["tecnico"], demanda.id, descricao="Validate runtime role")
    with pytest.raises(TransicaoEstadoInvalidaException):
        service.alterar_status(atores["tecnico"], demanda.id, Status.HOMOLOGACAO)
    service.concluir_etapa(atores["tecnico"], demanda.id, stage.id)
    service.alterar_status(atores["tecnico"], demanda.id, Status.HOMOLOGACAO)
    service.aprovar_homologacao(atores["cliente"], demanda.id, versao_entregavel="runtime-v1",
                              declaracao_aceite="Accept the synthetic runtime delivery.")
    assert demanda.status == Status.CONCLUIDO
    # CURRENT_TIMESTAMP is fixed by the fixture's outer transaction. Verify
    # persisted evidence without assuming it sorts after application timestamps.
    events = service.listar_estados(atores["cliente"], demanda.id)
    assert sum(event["novo_estado"] == Status.CONCLUIDO for event in events) == 1
    assert service.listar_auditoria(atores["admin"], demanda.id)


@pytest.mark.parametrize("statement", [
    "UPDATE public.aceites_formais SET versao_entregavel='tampered' WHERE false",
    "DELETE FROM public.aceites_formais WHERE false",
    "UPDATE public.auditoria_logs SET acao='tampered' WHERE false",
    "DELETE FROM public.auditoria_logs WHERE false",
    "UPDATE public.historico_status_pedidos SET status_novo=status_anterior WHERE false",
    "DELETE FROM public.historico_status_pedidos WHERE false",
    "TRUNCATE TABLE public.aceites_formais",
    "TRUNCATE TABLE public.auditoria_logs",
    "TRUNCATE TABLE public.historico_status_pedidos",
    "TRUNCATE TABLE public.etapas_operacionais",
    "SELECT * FROM public.alembic_version",
    "UPDATE public.alembic_version SET version_num=version_num",
    "ALTER TABLE public.pedidos DISABLE TRIGGER USER",
    "CREATE TABLE public.forbidden_runtime_table (id integer)",
], ids=["acceptance-update", "acceptance-delete", "audit-update", "audit-delete",
        "history-update", "history-delete", "acceptance-truncate", "audit-truncate",
        "history-truncate", "stages-truncate", "alembic-read", "alembic-write",
        "disable-triggers", "create-table"])
def test_restricted_runtime_cannot_change_evidence_or_administer_schema(runtime_db, statement):
    with pytest.raises(DBAPIError) as error:
        with runtime_db.begin_nested():
            runtime_db.execute(text(statement))
    assert error.value.orig.pgcode == "42501"


def test_catalog_audit_is_readonly_and_reports_storage_absence_explicitly(engine):
    with engine.connect() as connection:
        report = inspect_catalog(connection, "synthetic-unconfigured-bucket")
        assert connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
    assert report["readonly"] is True
    assert report["revision"] == ["e3b7c1d9f402"]
    assert report["findings"] == []
    assert report["public_grants"] == []
    assert report["public_column_grants"] == []
    assert len(report["functions"]) == len(report["triggers"]) == 3
    assert report["storage_available"] is False
    assert report["bucket"] == report["storage_grants"] == []
    assert report["integrity_counts"] == {
        "attachment_occurrence_mismatches": 0, "completed_without_acceptance": 0,
        "duplicate_acceptances": 0,
    }

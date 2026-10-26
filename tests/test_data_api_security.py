from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from app.infrastructure.database.data_api_security import (
    DOMAIN_TABLES, PRIVILEGES, PROTECTED_TABLES, assess_access, inspect_access,
)


def restricted_catalog():
    return [dict(table_name=table, role_name=role, rls=True, backend_bypasses_rls=role=="backend",
                 **{privilege: role in {"backend", "service_role"} for privilege in PRIVILEGES})
            for table in PROTECTED_TABLES for role in ("anon", "authenticated", "backend", "service_role")]


def test_backend_only_access_passes_catalog_assessment():
    # Synthetic catalog facts, not a real PostgreSQL permission-denial test.
    assert assess_access(restricted_catalog()) == []


@pytest.mark.parametrize("table", ["historico_status_pedidos", "etapas_operacionais", "aceites_formais", "auditoria_logs"])
@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("privilege", ["select", "insert", "update", "delete", "truncate"])
def test_untrusted_direct_access_is_flagged_even_if_rls_is_enabled(table, role, privilege):
    catalog = restricted_catalog()
    target = next(row for row in catalog if row["table_name"]==table and row["role_name"]==role)
    target[privilege] = True
    findings = assess_access(catalog)
    assert any(f.table==table and f.role==role and f.issue=="direct_client_privileges" for f in findings)


def test_history_without_rls_is_detected_independently_of_grants():
    catalog = restricted_catalog()
    for row in catalog:
        if row["table_name"] == "historico_status_pedidos":
            row["rls"] = False
    assert any(f.issue=="rls_disabled" and f.table=="historico_status_pedidos" for f in assess_access(catalog))


@pytest.mark.parametrize("privilege", ["select", "insert", "update", "delete", "backend_bypasses_rls"])
def test_hardening_must_preserve_legitimate_backend_access(privilege):
    catalog = restricted_catalog()
    target = next(row for row in catalog if row["table_name"]=="pedidos" and row["role_name"]=="backend")
    target[privilege] = False
    assert any(f.issue=="backend_access_requires_review" for f in assess_access(catalog))


def test_missing_pending_migration_table_is_not_silently_approved():
    catalog = [row for row in restricted_catalog() if row["table_name"]!="etapas_operacionais"]
    assert any(f.table=="etapas_operacionais" and f.issue=="missing_table" for f in assess_access(catalog))


def test_inspection_only_selects_bound_catalog_metadata():
    connection = MagicMock()
    facts = restricted_catalog()
    connection.execute.return_value.mappings.return_value.all.return_value = facts
    original = deepcopy(facts)
    assert inspect_access(connection) == facts
    statement, parameters = connection.execute.call_args.args
    assert str(statement).strip().startswith("SELECT")
    assert ":tables" in str(statement)
    assert parameters["tables"] == list(PROTECTED_TABLES)
    assert "has_any_column_privilege" in str(statement)
    assert facts == original
    connection.commit.assert_not_called()


def test_migration_metadata_is_protected_without_becoming_a_domain_model():
    assert "alembic_version" not in DOMAIN_TABLES
    catalog = restricted_catalog()
    for row in catalog:
        if row["table_name"] == "alembic_version":
            row["rls"] = False
    findings = assess_access(catalog)
    assert any(f.table=="alembic_version" and f.issue=="rls_disabled" for f in findings)


def test_client_cannot_be_approved_with_write_access_to_revision_metadata():
    catalog = restricted_catalog()
    target = next(row for row in catalog if row["table_name"]=="alembic_version" and row["role_name"]=="anon")
    target["update"] = True
    assert any(f.table=="alembic_version" and f.role=="anon" and f.issue=="direct_client_privileges" for f in assess_access(catalog))

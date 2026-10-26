"""Read-only checks for a backend-only Supabase domain data access model."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


DOMAIN_TABLES = (
    "users", "pedidos", "ocorrencias", "anexos", "aceites_formais",
    "auditoria_logs", "historico_status_pedidos", "etapas_operacionais",
)
# The existing HML migration 7b2d4e6f8a10 also protects Alembic's metadata.
PROTECTED_TABLES = (*DOMAIN_TABLES, "alembic_version")
CLIENT_ROLES = ("anon", "authenticated")
PRIVILEGES = ("select", "insert", "update", "delete", "truncate", "references", "trigger")


@dataclass(frozen=True)
class DataApiFinding:
    table: str
    issue: str
    role: str | None = None


def assess_access(rows: Sequence[Mapping[str, Any]]) -> list[DataApiFinding]:
    """Evaluate catalog facts, not simulated RLS behavior or HTTP authorization."""
    findings: list[DataApiFinding] = []
    for table in PROTECTED_TABLES:
        table_rows = [row for row in rows if row["table_name"] == table]
        if not table_rows:
            findings.append(DataApiFinding(table, "missing_table"))
            continue
        if not table_rows[0]["rls"]:
            findings.append(DataApiFinding(table, "rls_disabled"))
        for row in table_rows:
            if row["role_name"] in CLIENT_ROLES and any(row.get(privilege, False) for privilege in PRIVILEGES):
                findings.append(DataApiFinding(table, "direct_client_privileges", row["role_name"]))
            if row["role_name"] == "backend" and (
                not all(row.get(p, False) for p in ("select", "insert", "update", "delete"))
                or not row["backend_bypasses_rls"]
            ):
                findings.append(DataApiFinding(table, "backend_access_requires_review", "backend"))
        for role in (*CLIENT_ROLES, "backend", "service_role"):
            if not any(row["role_name"] == role for row in table_rows):
                findings.append(DataApiFinding(table, "missing_role", role))
    return findings


def inspect_access(connection: Connection) -> list[dict[str, Any]]:
    """Only SELECTs. Returns permissions and flags, never rows or credentials."""
    rows = connection.execute(text("""
        SELECT c.relname AS table_name,
            CASE WHEN r.rolname = current_user THEN 'backend' ELSE r.rolname END AS role_name,
            c.relrowsecurity AS rls,
            (r.rolsuper OR r.rolbypassrls OR (c.relowner=r.oid AND NOT c.relforcerowsecurity)) AS backend_bypasses_rls,
            (has_table_privilege(r.oid,c.oid,'SELECT') OR has_any_column_privilege(r.oid,c.oid,'SELECT')) AS select,
            (has_table_privilege(r.oid,c.oid,'INSERT') OR has_any_column_privilege(r.oid,c.oid,'INSERT')) AS insert,
            (has_table_privilege(r.oid,c.oid,'UPDATE') OR has_any_column_privilege(r.oid,c.oid,'UPDATE')) AS update,
            has_table_privilege(r.oid,c.oid,'DELETE') AS delete,
            has_table_privilege(r.oid,c.oid,'TRUNCATE') AS truncate,
            (has_table_privilege(r.oid,c.oid,'REFERENCES') OR has_any_column_privilege(r.oid,c.oid,'REFERENCES')) AS references,
            has_table_privilege(r.oid,c.oid,'TRIGGER') AS trigger
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN pg_roles r
        WHERE n.nspname='public' AND c.relkind IN ('r','p')
            AND c.relname=ANY(:tables)
            AND (r.rolname=ANY(:roles) OR r.rolname=current_user)
        ORDER BY c.relname, role_name
    """), {"tables": list(PROTECTED_TABLES), "roles": [*CLIENT_ROLES, "service_role"]}).mappings().all()
    return [dict(row) for row in rows]

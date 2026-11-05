from pathlib import Path

import pytest

from tests.integration.test_storage_inventory_visibility import storage_catalog  # noqa: F401


@pytest.mark.parametrize("mode", ["private", "missing", "public", "unset"])
def test_reviewed_sql_executes_readonly_without_object_paths_or_app_rows(storage_catalog, mode):
    script = Path("docs/security/supabase-readonly-preflight.sql").read_text(encoding="utf-8")
    snapshots = []
    if mode == "public":
        with storage_catalog.begin() as c:
            c.exec_driver_sql("UPDATE storage.buckets SET public=true")
    with storage_catalog.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.exec_driver_sql("SET automatize.audit_bucket='does-not-exist'" if mode == "missing"
                         else "RESET automatize.audit_bucket" if mode == "unset"
                         else "SET automatize.audit_bucket='synthetic-private'")
        try:
            for statement in script.split(";\n"):
                if not statement.strip():
                    continue
                result = c.exec_driver_sql(statement)
                if result.returns_rows:
                    snapshots.append(list(result.mappings()))
        finally:
            c.exec_driver_sql("ROLLBACK")
            c.exec_driver_sql("RESET automatize.audit_bucket")
    assert next(rows[0] for rows in snapshots if rows and "read_only" in rows[0])["read_only"] == "on"
    stats = next(rows[0] for rows in snapshots if rows and "catalog_objects" in rows[0])
    if mode == "private":
        assert stats["full_visibility_required"] is True
        assert stats["catalog_objects"] == stats["objects_without_reference"] == 1
        assert stats["references_without_object"] == 0
    else:
        assert stats["full_visibility_required"] is False
        assert stats["catalog_objects"] is stats["objects_without_reference"] is stats["references_without_object"] is None
    footer = next(rows[0] for rows in snapshots if rows and "cleanup_authorized" in rows[0])
    assert footer["cleanup_authorized"] is footer["deployment_authorized"] is False

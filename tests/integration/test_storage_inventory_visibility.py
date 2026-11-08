"""Storage catalog simulation in a fresh guarded PostgreSQL database only."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from scripts.reconcile_storage import inventory
from tests.integration.test_migration_upgrade import fresh_database, upgrade


@pytest.fixture
def storage_catalog(engine, monkeypatch):
    database = fresh_database(engine)
    upgrade(database, monkeypatch)
    object_id = uuid4()
    path = f"pedidos/{uuid4()}/{uuid4()}.pdf"
    old = datetime.now(timezone.utc)-timedelta(days=3)
    with database.begin() as c:
        # Stand-in catalog; no real SDK or Supabase connection exists here.
        c.exec_driver_sql("CREATE SCHEMA storage")
        c.exec_driver_sql("CREATE TABLE storage.buckets(id text PRIMARY KEY,public boolean NOT NULL)")
        c.exec_driver_sql("CREATE TABLE storage.objects(id uuid PRIMARY KEY,bucket_id text REFERENCES storage.buckets(id),name text,created_at timestamptz,updated_at timestamptz)")
        c.exec_driver_sql("INSERT INTO storage.buckets VALUES ('synthetic-private',false)")
        c.execute(text("INSERT INTO storage.objects VALUES (:id,'synthetic-private',:path,:old,:old)"),
                  {"id":object_id,"path":path,"old":old})
        c.exec_driver_sql("GRANT USAGE ON SCHEMA storage TO anon")
    yield database
    database.dispose()


def test_complete_inventory_is_readonly_and_never_authorizes_delete(storage_catalog):
    with storage_catalog.connect() as c:
        result = inventory(c, "synthetic-private")
        assert c.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
    assert result["complete_snapshot"] is True
    assert result["counts"]["storage_objects"] == 1
    assert result["counts"]["orphan_candidates_requiring_review"] == 1
    assert result["apply_supported"] is False
    assert all(row["delete"] is False for row in result["objects"])


@pytest.mark.parametrize("reason", ["missing-bucket", "public-bucket"])
def test_invalid_bucket_never_becomes_an_empty_complete_inventory(storage_catalog, reason):
    bucket = "does-not-exist" if reason == "missing-bucket" else "synthetic-private"
    if reason == "public-bucket":
        with storage_catalog.begin() as c:
            c.exec_driver_sql("UPDATE storage.buckets SET public=true")
    with storage_catalog.connect() as c, pytest.raises(ValueError, match="private application bucket"):
        inventory(c, bucket)


@pytest.mark.parametrize("table", ["objects", "buckets"])
@pytest.mark.parametrize("blocked_by", ["grants", "rls"])
def test_incomplete_storage_visibility_is_not_proof_of_absence(storage_catalog, table, blocked_by):
    with storage_catalog.begin() as c:
        c.exec_driver_sql("ALTER TABLE public.anexos DISABLE ROW LEVEL SECURITY")
        c.exec_driver_sql("ALTER TABLE public.pedidos DISABLE ROW LEVEL SECURITY")
        c.exec_driver_sql("GRANT SELECT ON public.anexos,public.pedidos TO anon")
        c.exec_driver_sql("GRANT SELECT ON storage.objects,storage.buckets TO anon")
        if blocked_by == "rls":
            c.exec_driver_sql(f"ALTER TABLE storage.{table} ENABLE ROW LEVEL SECURITY")
        else:
            c.exec_driver_sql(f"REVOKE SELECT ON storage.{table} FROM anon")
    with storage_catalog.connect() as c:
        c.exec_driver_sql("SET ROLE anon")
        c.commit()
        try:
            with pytest.raises(ValueError, match="Storage catalog visibility"):
                inventory(c, "synthetic-private")
        finally:
            c.rollback()
            c.exec_driver_sql("RESET ROLE")
            c.commit()


def test_filtered_domain_rows_are_refused_even_with_full_storage_access(storage_catalog):
    with storage_catalog.begin() as c:
        c.exec_driver_sql("GRANT SELECT ON public.anexos,public.pedidos,storage.objects,storage.buckets TO anon")
    with storage_catalog.connect() as c:
        c.exec_driver_sql("SET ROLE anon")
        c.commit()
        try:
            with pytest.raises(ValueError, match="Complete domain visibility"):
                inventory(c, "synthetic-private")
        finally:
            c.rollback()
            c.exec_driver_sql("RESET ROLE")
            c.commit()

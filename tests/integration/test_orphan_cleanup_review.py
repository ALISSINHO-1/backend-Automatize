"""Controlled-cleanup rehearsal: real DB visibility, simulated Storage, no delete."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from threading import Event
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.infrastructure.storage.cleanup_review import receipt_digest, review_candidate
from app.infrastructure.storage.reconciliation import ObjectEvidence


class SimulatedStorage:
    def __init__(self, obj):
        self.obj = obj
        self.calls = 0
        self.on_second = None
        self.fail_on = None
        self.delete = Mock(side_effect=AssertionError("Deletion must never be called"))

    def head(self, _object_id):
        self.calls += 1
        if self.calls == self.fail_on:
            raise TimeoutError("private provider details must not escape")
        if self.calls == 2 and self.on_second:
            self.on_second()
        return self.obj


@pytest.fixture
def scenario(engine):
    now = datetime.now(timezone.utc)
    order, user = uuid4(), uuid4()
    obj = ObjectEvidence(f"pedidos/{order}/{uuid4()}.pdf", now-timedelta(days=3),
                         now-timedelta(days=2), uuid4(), "generation-1")
    state = {"obj": obj, "storage": SimulatedStorage(obj), "now": now,
             "order": order, "user": user, "engine": engine, "created": False}
    yield state
    if state["created"]:
        # Only this test's synthetic rows in the guarded disposable cluster.
        with engine.begin() as c:
            c.execute(text("DELETE FROM public.pedidos WHERE id=:id"), {"id": order})
            c.execute(text("DELETE FROM public.users WHERE id=:id"), {"id": user})


def receipt(obj):
    result = {"dry_run": True, "complete_snapshot": True, "bucket_sha256": "b"*64,
              "objects": [{"storage_object_id": str(obj.storage_id),
                           "object_sha256": sha256(obj.path.encode()).hexdigest(),
                           "created_at": obj.created_at.isoformat() if obj.created_at else None,
                           "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
                           "version": obj.version, "reason": "orphan_candidate_requires_review", "delete": False}]}
    result["inventory_sha256"] = receipt_digest(result)
    return result


def review(s, manifest=None, **overrides):
    manifest = manifest or receipt(s["obj"])
    options = {"approved_inventory_sha256": manifest["inventory_sha256"],
               "approved_ids": frozenset({s["obj"].storage_id}), "bucket_sha256": "b"*64,
               "storage_probe": s["storage"].head, "uploads_coordinated": True,
               "conditional_delete_supported": True, "now": s["now"]}
    options.update(overrides)
    with s["engine"].connect() as c:
        result = review_candidate(c, manifest, s["obj"].storage_id, **options)
    assert result["delete"] is False
    s["storage"].delete.assert_not_called()
    assert s["obj"].path not in str(result)
    return result["reason"]


def create_reference(s, include_attachment=True):
    with s["engine"].begin() as c:
        c.execute(text("INSERT INTO public.users(id,nome,email,senha_hash) VALUES (:id,'Synthetic',:email,'unused')"),
                  {"id": s["user"], "email": f"{s['user']}@test.invalid"})
        c.execute(text("INSERT INTO public.pedidos(id,codigo_identificador,titulo,cliente_id) VALUES (:id,:code,'Synthetic',:user)"),
                  {"id": s["order"], "code": str(s["order"]), "user": s["user"]})
        if include_attachment:
            c.execute(text("INSERT INTO public.anexos(pedido_id,enviado_por_id,nome_arquivo,caminho_storage,extensao,tamanho_bytes) "
                           "VALUES (:order,:user,'synthetic.pdf',:path,'pdf',1)"),
                      {"order": s["order"], "user": s["user"], "path": s["obj"].path})
    s["created"] = True


def test_even_successful_simulation_never_authorizes_real_execution(scenario):
    assert review(scenario) == "execution_not_enabled"


@pytest.mark.parametrize("fail_on", [1, 2], ids=["first-head-timeout", "second-head-timeout"])
def test_storage_network_uncertainty_fails_closed(scenario, fail_on):
    scenario["storage"].fail_on = fail_on
    assert review(scenario) == "review_unavailable"


def test_new_reference_committed_between_checks_is_visible(scenario):
    ready, committed = Event(), Event()
    def writer():
        assert ready.wait(5)
        try:
            create_reference(scenario)
        finally:
            committed.set()
    def pause():
        ready.set()
        assert committed.wait(5)
    scenario["storage"].on_second = pause
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        assert review(scenario) == "reference_added"
        future.result(timeout=5)


def test_existing_order_is_not_an_orphan_even_without_metadata(scenario):
    create_reference(scenario, include_attachment=False)
    assert review(scenario) == "existing_order_requires_review"


@pytest.mark.parametrize("change", ["identity", "version", "path"])
def test_object_replacement_during_second_check_never_deletes(scenario, change):
    obj = scenario["obj"]
    replacement = {"identity": replace(obj, storage_id=uuid4()),
                   "version": replace(obj, version="generation-2"),
                   "path": replace(obj, path=f"pedidos/{uuid4()}/{uuid4()}.pdf")}[change]
    scenario["storage"].on_second = lambda: setattr(scenario["storage"], "obj", replacement)
    assert review(scenario) == "object_changed_during_review"


@pytest.mark.parametrize("kind", ["recent", "missing-timestamp", "naive-timestamp", "unknown-path"])
def test_unsafe_objects_are_refused_even_when_human_approved(scenario, kind):
    obj = scenario["obj"]
    obj = {"recent": replace(obj, updated_at=scenario["now"]),
           "missing-timestamp": replace(obj, created_at=None),
           "naive-timestamp": replace(obj, updated_at=obj.updated_at.replace(tzinfo=None)),
           "unknown-path": replace(obj, path="foreign/object.pdf")}[kind]
    scenario["obj"] = scenario["storage"].obj = obj
    expected = {"recent":"recent_or_inflight", "missing-timestamp":"missing_timestamp",
                "naive-timestamp":"ambiguous_timestamp", "unknown-path":"unknown_path"}[kind]
    assert review(scenario) == expected


@pytest.mark.parametrize("missing", ["approval", "version", "coordination", "conditional-api"])
def test_required_guarantees_are_not_inferred(scenario, missing):
    if missing == "version":
        obj = replace(scenario["obj"], version=None)
        scenario["obj"] = scenario["storage"].obj = obj
    options = {"approval":{"approved_ids":frozenset()}, "version":{},
               "coordination":{"uploads_coordinated":False},
               "conditional-api":{"conditional_delete_supported":False}}[missing]
    expected = {"approval":"object_not_human_approved", "version":"object_version_not_proven",
                "coordination":"uploads_not_coordinated", "conditional-api":"conditional_delete_not_supported"}[missing]
    assert review(scenario, **options) == expected


def test_receipt_tampering_is_refused_before_storage_access(scenario):
    manifest = receipt(scenario["obj"])
    manifest["objects"][0]["storage_object_id"] = str(uuid4())
    assert review(scenario, manifest) == "invalid_or_unapproved_receipt"
    assert scenario["storage"].calls == 0


def test_disappeared_object_is_a_noop_and_not_a_path_delete(scenario):
    scenario["storage"].obj = None
    assert review(scenario) == "object_missing_no_action"


def test_change_after_last_check_still_has_no_execution_permission(scenario):
    assert review(scenario) == "execution_not_enabled"
    scenario["storage"].obj = replace(scenario["obj"], storage_id=uuid4(), version="generation-3")
    scenario["storage"].delete.assert_not_called()


def check_connection(s, connection):
    manifest = receipt(s["obj"])
    result = review_candidate(connection, manifest, s["obj"].storage_id,
        approved_inventory_sha256=manifest["inventory_sha256"],
        approved_ids=frozenset({s["obj"].storage_id}), bucket_sha256="b"*64,
        storage_probe=s["storage"].head, uploads_coordinated=True,
        conditional_delete_supported=True, now=s["now"])
    assert result["delete"] is False
    s["storage"].delete.assert_not_called()
    return result


@pytest.mark.parametrize("select_granted", [False, True], ids=["no-select", "rls-hides-rows"])
def test_incomplete_database_visibility_is_refused_before_storage_probe(scenario, select_granted):
    engine = scenario["engine"]
    if select_granted:
        with engine.begin() as c:
            c.exec_driver_sql("GRANT SELECT ON public.anexos,public.pedidos TO anon")
    try:
        with engine.connect() as c:
            catalog_shadow = False
            c.exec_driver_sql("SET ROLE anon")
            c.commit()
            try:
                if select_granted:
                    # Forge catalog rows pointing at a public-readable catalog
                    # table. Unqualified pg_class would misreport RLS coverage.
                    c.exec_driver_sql('CREATE TEMP TABLE pg_class (oid oid,relname name,relnamespace oid,relkind "char")')
                    catalog_shadow = True
                    c.exec_driver_sql("INSERT INTO pg_temp.pg_class SELECT 'pg_catalog.pg_class'::regclass,v.name,'public'::regnamespace,'r' FROM (VALUES ('anexos'),('pedidos')) v(name)")
                    c.exec_driver_sql("SET search_path=pg_temp,pg_catalog")
                    c.commit()
                assert check_connection(scenario, c)["reason"] == "database_visibility_incomplete"
                assert scenario["storage"].calls == 0
            finally:
                c.rollback()
                if catalog_shadow:
                    c.exec_driver_sql("DROP TABLE pg_temp.pg_class")
                    c.exec_driver_sql("RESET search_path")
                c.exec_driver_sql("RESET ROLE")
                c.commit()
    finally:
        if select_granted:
            with engine.begin() as c:
                c.exec_driver_sql("REVOKE SELECT ON public.anexos,public.pedidos FROM anon")


def test_database_disconnect_during_revalidation_fails_closed_and_recovers(scenario):
    with scenario["engine"].connect() as c:
        scenario["storage"].on_second = c.invalidate
        result = check_connection(scenario, c)
        assert result["reason"] == "review_unavailable"
        assert not c.in_transaction()
    with scenario["engine"].connect() as recovered:
        assert recovered.exec_driver_sql("SELECT 1").scalar_one() == 1


@pytest.mark.parametrize("mode", ["old-snapshot", "already-in-transaction"])
def test_historical_or_active_transaction_cannot_be_reused(scenario, mode):
    with scenario["engine"].connect() as c:
        if mode == "old-snapshot":
            c.execution_options(isolation_level="REPEATABLE READ")
        else:
            c.exec_driver_sql("SELECT 1")
        assert check_connection(scenario, c)["reason"] == "fresh_transaction_required"
        assert scenario["storage"].calls == 0


def test_duplicate_approved_candidate_is_ambiguous(scenario):
    manifest = receipt(scenario["obj"])
    manifest["objects"].append(dict(manifest["objects"][0]))
    manifest["inventory_sha256"] = receipt_digest(manifest)
    assert review(scenario, manifest) == "not_an_inventoried_candidate"
    assert scenario["storage"].calls == 0


def test_already_referenced_object_is_refused(scenario):
    create_reference(scenario)
    assert review(scenario) == "reference_added"


def test_refusal_result_is_a_sanitized_audit_record(scenario):
    with scenario["engine"].connect() as c:
        result = check_connection(scenario, c)
    assert set(result) == {"delete", "reason", "storage_object_id", "inventory_sha256", "reviewed_at"}
    assert result["storage_object_id"] == str(scenario["obj"].storage_id)
    assert result["inventory_sha256"] == receipt(scenario["obj"])["inventory_sha256"]
    assert datetime.fromisoformat(result["reviewed_at"]).tzinfo is not None
    assert scenario["obj"].path not in str(result)

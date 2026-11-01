from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.infrastructure.storage.reconciliation import ObjectEvidence, classify_objects, reconcile_inventory
from scripts.isolated_database import require_isolated_database
import pytest


def test_reconciliation_never_deletes_ambiguous_recent_or_referenced_objects():
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=2)
    order_id = uuid4()
    paths = [f"pedidos/{order_id}/{uuid4()}.pdf" for _ in range(4)]
    rows = [ObjectEvidence(paths[0], old, old), ObjectEvidence(paths[1], now, now),
            ObjectEvidence(paths[2], None, None), ObjectEvidence("foreign/file.pdf", old, old)]
    findings = classify_objects(rows, {paths[0]}, {order_id}, now=now, complete=True)
    assert [f["reason"] for f in findings] == [
        "referenced", "recent_or_inflight", "missing_timestamp", "unknown_path",
    ]
    assert all(f["delete"] is False for f in findings)
    obj = ObjectEvidence(paths[3], old, old)
    assert classify_objects([obj], set(), {order_id}, now=now, complete=True)[0]["reason"] == "existing_order_requires_review"
    assert classify_objects([obj], set(), set(), now=now, complete=True)[0]["reason"] == "orphan_candidate_requires_review"
    assert classify_objects([obj], set(), set(), now=now)[0]["reason"] == "incomplete_inventory"
    assert paths[0] not in str(findings)


def test_inventory_detects_missing_objects_and_unreferenced_files_without_deleting():
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=2)
    order_id = uuid4()
    referenced, missing, unreferenced = [f"pedidos/{order_id}/{uuid4()}.pdf" for _ in range(3)]
    objects = [ObjectEvidence(referenced, old, old), ObjectEvidence(unreferenced, old, old)]
    report = reconcile_inventory(objects, {referenced, missing}, {order_id}, now=now, complete=True)
    assert report["counts"]["objects_without_record"] == 1
    assert report["counts"]["references_without_object"] == 1
    assert report["references_without_object"][0]["reason"] == "missing_object_in_configured_bucket"
    assert all(row["delete"] is False for row in report["objects"] + report["references_without_object"])
    assert all(path not in str(report) for path in (referenced, missing, unreferenced))


def test_incomplete_inventory_does_not_report_false_missing_files():
    report = reconcile_inventory([], {"unknown/path.pdf"}, set(), complete=False)
    assert report["references_without_object"] == []
    assert report["counts"]["references_without_object"] is None


@pytest.mark.parametrize("target", [
    "postgresql://postgres@remote.example:5432/automatize_test",
    "postgresql://postgres@localhost:5432/production",
    "postgresql://postgres@localhost/automatize_test",
    "postgresql://postgres@localhost:5432/automatize_test?host=remote.example",
    "sqlite:///:memory:", "",
])
def test_isolated_write_guard_rejects_unsafe_destinations(target):
    with pytest.raises(ValueError):
        require_isolated_database(target)

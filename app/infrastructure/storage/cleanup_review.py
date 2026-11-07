"""Second-check rehearsal for a human-reviewed receipt; never deletes objects.

There is deliberately no production Storage adapter or mutation method here.
A successful rehearsal is not an authorization to call Storage.remove().
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Callable, Mapping
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.infrastructure.storage.reconciliation import ObjectEvidence, classify_objects
from app.infrastructure.database.data_api_security import (
    IncompleteVisibilityError, require_complete_visibility,
)


def receipt_digest(receipt: Mapping) -> str:
    payload = {key: value for key, value in receipt.items() if key != "inventory_sha256"}
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def review_candidate(
    connection: Connection,
    receipt: Mapping,
    object_id: UUID,
    *,
    approved_inventory_sha256: str,
    approved_ids: frozenset[UUID],
    bucket_sha256: str,
    storage_probe: Callable[[UUID], ObjectEvidence | None],
    uploads_coordinated: bool = False,
    conditional_delete_supported: bool = False,
    now: datetime | None = None,
) -> dict:
    """Compare fresh DB/Storage facts with approved evidence, failing closed.

    Use a fresh READ COMMITTED connection, not the historical inventory's
    REPEATABLE READ snapshot. Flags document simulated preconditions only;
    even when every check passes, execution remains disabled.
    """
    now = now or datetime.now(timezone.utc)

    def result(reason):
        return {"delete": False, "reason": reason, "storage_object_id": str(object_id),
                "inventory_sha256": approved_inventory_sha256, "reviewed_at": now.isoformat()}

    try:
        digest = receipt_digest(receipt)
        if (receipt.get("inventory_sha256") != digest or approved_inventory_sha256 != digest
                or receipt.get("bucket_sha256") != bucket_sha256
                or receipt.get("complete_snapshot") is not True or receipt.get("dry_run") is not True):
            return result("invalid_or_unapproved_receipt")
        if object_id not in approved_ids:
            return result("object_not_human_approved")
        entries = [row for row in receipt.get("objects", []) if row.get("storage_object_id") == str(object_id)]
        if len(entries) != 1 or entries[0].get("reason") != "orphan_candidate_requires_review":
            return result("not_an_inventoried_candidate")
        baseline = entries[0]
        if connection.in_transaction() or connection.get_isolation_level() != "READ COMMITTED":
            return result("fresh_transaction_required")

        with connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
                return result("readonly_verification_required")
            require_complete_visibility(connection, ("anexos", "pedidos"))
            current = storage_probe(object_id)
            if current is None:
                return result("object_missing_no_action")
            if current.storage_id != object_id:
                return result("object_identity_changed")
            if (sha256(current.path.encode()).hexdigest() != baseline.get("object_sha256")
                    or (current.created_at.isoformat() if current.created_at else None) != baseline.get("created_at")
                    or (current.updated_at.isoformat() if current.updated_at else None) != baseline.get("updated_at")):
                return result("object_metadata_changed")

            def referenced():
                return connection.execute(text(
                    "SELECT EXISTS(SELECT 1 FROM public.anexos WHERE caminho_storage=:path)"
                ), {"path": current.path}).scalar_one()

            if referenced():
                return result("reference_added")
            # classify_objects checks canonical paths before interpreting the UUID.
            eligibility = classify_objects([current], set(), set(), now=now, complete=True)[0]["reason"]
            if eligibility != "orphan_candidate_requires_review":
                return result(eligibility)
            order_id = UUID(current.path.split("/")[1])

            def order_exists():
                return connection.execute(text(
                    "SELECT EXISTS(SELECT 1 FROM public.pedidos WHERE id=:id)"
                ), {"id": order_id}).scalar_one()

            if order_exists():
                return result("existing_order_requires_review")
            # A second HEAD/read can detect replacement and network uncertainty;
            # it cannot make a subsequent path-based delete atomic.
            latest = storage_probe(object_id)
            if latest != current:
                return result("object_changed_during_review")
            if referenced():
                return result("reference_added")
            if order_exists():
                return result("existing_order_requires_review")
            if not baseline.get("version") or current.version != baseline["version"]:
                return result("object_version_not_proven")
            if not uploads_coordinated:
                return result("uploads_not_coordinated")
            if not conditional_delete_supported:
                return result("conditional_delete_not_supported")
            return result("execution_not_enabled")
    except IncompleteVisibilityError:
        return result("database_visibility_incomplete")
    except Exception:
        # Network/driver errors can contain secrets or object paths.
        return result("review_unavailable")

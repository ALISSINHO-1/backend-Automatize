"""Conservative dry-run evidence. This module never deletes a Storage object."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import PurePosixPath
from uuid import UUID

from app.infrastructure.storage.file_validation import MIME_POR_EXTENSAO


@dataclass(frozen=True)
class ObjectEvidence:
    path: str
    created_at: datetime | None
    updated_at: datetime | None
    storage_id: UUID | None = None


def classify_objects(objects, references, order_ids, *, now=None, complete=False):
    now = now or datetime.now(timezone.utc)
    result = []
    for obj in objects:
        reason = "ambiguous"
        digest = sha256(obj.path.encode()).hexdigest()
        parts = obj.path.split("/")
        try:
            valid = (len(parts) == 3 and parts[0] == "pedidos"
                     and str(UUID(parts[1])) == parts[1]
                     and str(UUID(PurePosixPath(parts[2]).stem)) == PurePosixPath(parts[2]).stem
                     and PurePosixPath(parts[2]).suffix in MIME_POR_EXTENSAO)
        except (ValueError, IndexError):
            valid = False
        if not complete:
            reason = "incomplete_inventory"
        elif obj.path in references:
            reason = "referenced"
        elif not valid:
            reason = "unknown_path"
        elif obj.created_at is None or obj.updated_at is None:
            reason = "missing_timestamp"
        elif obj.created_at.tzinfo is None or obj.updated_at.tzinfo is None:
            reason = "ambiguous_timestamp"
        elif max(obj.created_at, obj.updated_at) > now - timedelta(hours=24):
            reason = "recent_or_inflight"
        elif UUID(parts[1]) in order_ids:
            # An order without metadata may represent an uncertain commit or an
            # upload still being reconciled. Never infer safe deletion here.
            reason = "existing_order_requires_review"
        else:
            reason = "orphan_candidate_requires_review"
        result.append({"object_sha256": digest, "reason": reason, "delete": False})
    return result


def reconcile_inventory(objects, references, order_ids, *, now=None, complete=False):
    """Compare both directions in one complete snapshot; never authorize deletion.

    A missing catalog object is evidence about the configured bucket, not proof
    about physical bytes or other buckets. Incomplete inventories cannot prove
    absence, so their missing-object counts remain unknown.
    """
    objects = list(objects)
    ids = [str(obj.storage_id) for obj in objects if obj.storage_id is not None]
    if len({obj.path for obj in objects}) != len(objects) or len(set(ids)) != len(ids):
        raise ValueError("Ambiguous Storage inventory; duplicate objects detected.")
    references = set(references)
    findings = classify_objects(objects, references, order_ids, now=now, complete=complete)
    paths = {obj.path for obj in objects}
    missing = sorted(references - paths) if complete else []
    return {
        "dry_run": True,
        "complete_snapshot": complete,
        "objects": findings,
        "references_without_object": [{
            "object_sha256": sha256(path.encode()).hexdigest(),
            "reason": "missing_object_in_configured_bucket",
            "delete": False,
        } for path in missing],
        "counts": {
            "database_references": len(references),
            "storage_objects": len(objects),
            "objects_without_record": len(paths - references) if complete else None,
            "references_without_object": len(missing) if complete else None,
            "orphan_candidates_requiring_review": sum(
                row["reason"] == "orphan_candidate_requires_review" for row in findings
            ),
        },
    }

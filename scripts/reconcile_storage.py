"""Read-only orphan inventory with review IDs; destructive apply is refused."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from sqlalchemy import text

from app.core.config import Settings
from app.core.database import create_database_engine
from app.infrastructure.storage.reconciliation import ObjectEvidence, reconcile_inventory


def inventory(connection, bucket):
    connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
        raise RuntimeError("Read-only snapshot required")
    # SQL metadata inventory avoids SDK pagination gaps and never downloads files.
    refs = set(connection.exec_driver_sql("SELECT caminho_storage FROM public.anexos").scalars())
    orders = set(connection.exec_driver_sql("SELECT id FROM public.pedidos").scalars())
    objects = [ObjectEvidence(*row) for row in connection.execute(text(
        "SELECT name,created_at,updated_at,id FROM storage.objects WHERE bucket_id=:bucket ORDER BY id"
    ), {"bucket": bucket})]
    now = connection.exec_driver_sql("SELECT CURRENT_TIMESTAMP").scalar_one()
    result = reconcile_inventory(
        objects, refs, orders, now=now, complete=True,
    )
    # Only opaque object IDs and path hashes leave the process. This receipt is
    # review evidence, never a deletion authorization or a storage version lock.
    result["schema_version"] = 1
    result["generated_at"] = now.isoformat()
    result["bucket_sha256"] = sha256(bucket.encode()).hexdigest()
    result["apply_supported"] = False
    by_digest = {sha256(obj.path.encode()).hexdigest(): obj for obj in objects}
    for finding in result["objects"]:
        obj = by_digest[finding["object_sha256"]]
        finding.update({
            "storage_object_id": str(obj.storage_id),
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
        })
    receipt = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["inventory_sha256"] = sha256(receipt.encode()).hexdigest()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Generate a read-only inventory (default).")
    mode.add_argument("--apply", action="store_true", help="Unsupported: refuses all deletion before connecting.")
    parser.add_argument("--output", type=Path, help="Save the review receipt locally; no secrets or object paths.")
    args = parser.parse_args(argv)
    if args.apply:
        parser.error("Apply disabled: conditional object deletion and writer coordination require an approved operational design.")
    engine = None
    try:
        settings = Settings()
        engine = create_database_engine(settings, connect_args={
            "connect_timeout": 8,
            "options": "-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=3000",
        })
        with engine.connect() as connection:
            result = inventory(connection, settings.STORAGE_BUCKET_NAME)
        if args.output:
            # Exclusive creation prevents overwriting previously reviewed evidence.
            with args.output.open("x", encoding="utf-8") as output:
                output.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        return 0
    except Exception:
        print(json.dumps({"dry_run": True, "complete_snapshot": False, "error": "Inventory unavailable"}))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only orphan inventory. No apply/delete option; no object names exported."""
import json

from sqlalchemy import text

from app.core.config import Settings
from app.core.database import create_database_engine
from app.infrastructure.storage.reconciliation import ObjectEvidence, reconcile_inventory


def inventory(connection, bucket):
    connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    assert connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() == "on"
    # SQL metadata inventory avoids SDK pagination gaps and never downloads files.
    refs = set(connection.exec_driver_sql("SELECT caminho_storage FROM public.anexos").scalars())
    orders = set(connection.exec_driver_sql("SELECT id FROM public.pedidos").scalars())
    objects = [ObjectEvidence(*row) for row in connection.execute(text(
        "SELECT name,created_at,updated_at FROM storage.objects WHERE bucket_id=:bucket"
    ), {"bucket": bucket})]
    now = connection.exec_driver_sql("SELECT CURRENT_TIMESTAMP").scalar_one()
    return reconcile_inventory(
        objects, refs, orders, now=now, complete=True,
    )


def main():
    engine = None
    try:
        settings = Settings()
        engine = create_database_engine(settings, connect_args={"connect_timeout": 8})
        with engine.connect() as connection:
            result = inventory(connection, settings.STORAGE_BUCKET_NAME)
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

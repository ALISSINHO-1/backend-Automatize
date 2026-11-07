from datetime import datetime, timezone
from hashlib import sha256
import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.infrastructure.storage.reconciliation import ObjectEvidence, reconcile_inventory
from scripts import reconcile_storage


def test_apply_is_refused_before_reading_settings_or_connecting(monkeypatch):
    settings = MagicMock()
    engine = MagicMock()
    monkeypatch.setattr(reconcile_storage, "Settings", settings)
    monkeypatch.setattr(reconcile_storage, "create_database_engine", engine)
    with pytest.raises(SystemExit) as error:
        reconcile_storage.main(["--apply"])
    assert error.value.code == 2
    settings.assert_not_called()
    engine.assert_not_called()


def test_inventory_receipt_has_ids_and_hashes_but_no_object_names(monkeypatch):
    now = datetime(2026, 11, 2, tzinfo=timezone.utc)
    object_id, order_id = uuid4(), uuid4()
    path = f"pedidos/{order_id}/{uuid4()}.pdf"
    connection = MagicMock()
    connection.exec_driver_sql.side_effect = [None, MagicMock(scalar_one=lambda: "on"),
        MagicMock(scalars=lambda: []), MagicMock(scalars=lambda: []), MagicMock(scalar_one=lambda: now)]
    connection.execute.return_value = [(path, now, now, object_id)]
    visibility = MagicMock()
    monkeypatch.setattr(reconcile_storage, "require_complete_inventory_access", visibility)
    result = reconcile_storage.inventory(connection, "synthetic-bucket")
    visibility.assert_called_once_with(connection, "synthetic-bucket")
    assert result["objects"][0]["storage_object_id"] == str(object_id)
    assert result["objects"][0]["object_sha256"] == sha256(path.encode()).hexdigest()
    assert result["apply_supported"] is False
    assert result["dry_run"] and result["complete_snapshot"]
    assert path not in json.dumps(result) and "synthetic-bucket" not in json.dumps(result)
    assert len(result["inventory_sha256"]) == 64
    assert all(row["delete"] is False for row in result["objects"])


@pytest.mark.parametrize("collision", ["path", "id"])
def test_ambiguous_inventory_aborts_instead_of_authorizing_cleanup(collision):
    now = datetime.now(timezone.utc)
    first = ObjectEvidence(f"pedidos/{uuid4()}/{uuid4()}.pdf", now, now, uuid4())
    second = ObjectEvidence(first.path if collision == "path" else f"pedidos/{uuid4()}/{uuid4()}.pdf",
                            now, now, first.storage_id if collision == "id" else uuid4())
    with pytest.raises(ValueError, match="Ambiguous"):
        reconcile_inventory([first, second], set(), set(), complete=True)


def test_explicit_dry_run_saves_receipt_and_never_overwrites(monkeypatch, tmp_path, capsys):
    engine = MagicMock()
    monkeypatch.setattr(reconcile_storage, "Settings", MagicMock())
    monkeypatch.setattr(reconcile_storage, "create_database_engine", lambda *a, **k: engine)
    result = {"dry_run": True, "complete_snapshot": True, "apply_supported": False}
    monkeypatch.setattr(reconcile_storage, "inventory", lambda *a: result)
    output = tmp_path / "receipt.json"
    assert reconcile_storage.main(["--dry-run", "--output", str(output)]) == 0
    assert json.loads(output.read_text()) == result
    assert reconcile_storage.main(["--dry-run", "--output", str(output)]) == 2
    assert json.loads(output.read_text()) == result
    engine.dispose.assert_called()

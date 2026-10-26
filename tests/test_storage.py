import importlib
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.infrastructure.storage import supabase_storage as infrastructure
from app.infrastructure.storage.supabase_storage import (
    StorageDeleteError, StorageUploadError, SupabaseStorage,
)


def test_storage_settings_preserve_auth_and_default_bucket():
    configured = Settings(_env_file=None, SUPABASE_URL="https://example.supabase.co",
                          SUPABASE_KEY="test-storage-secret")
    assert configured.STORAGE_BUCKET_NAME == "evidencias-anexos"
    assert configured.JWT_ALGORITHM == "HS256"
    assert "test-storage-secret" not in repr(configured)


def test_legacy_module_import_is_lazy_and_shares_infrastructure_factory(monkeypatch):
    factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(infrastructure, "create_supabase_client", factory)
    import app.core.storage as legacy
    importlib.reload(legacy)
    try:
        factory.assert_not_called()
        assert legacy.create_supabase_client is factory
        assert legacy.supabase is legacy.supabase
        factory.assert_called_once()
    finally:
        # Restore the real factory on the cached compatibility module.
        monkeypatch.undo()
        importlib.reload(legacy)


def test_missing_storage_credentials_do_not_create_client(monkeypatch):
    monkeypatch.setattr(infrastructure, "settings", Settings(
        _env_file=None, SUPABASE_URL=None, SUPABASE_KEY=None,
    ))
    client_factory = MagicMock()
    monkeypatch.setattr(infrastructure, "create_client", client_factory)
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        infrastructure.create_supabase_client()
    client_factory.assert_not_called()


def test_upload_uses_default_bucket_unique_paths_and_correct_options():
    client = MagicMock()
    storage = SupabaseStorage(client=client)
    pedido_id = uuid4()
    paths = [storage.upload(pedido_id=pedido_id, nome_arquivo="../../evidencia.PDF",
                            conteudo=b"test", content_type="application/pdf") for _ in range(2)]
    assert paths[0] != paths[1]
    assert all(path.startswith(f"pedidos/{pedido_id}/") and path.endswith(".pdf") for path in paths)
    assert all(".." not in path for path in paths)
    client.storage.from_.assert_called_with("evidencias-anexos")
    client.storage.from_.return_value.upload.assert_called_with(
        path=paths[1], file=b"test",
        file_options={"content-type": "application/pdf", "upsert": "false"},
    )
    storage.delete(paths[0])
    client.storage.from_.return_value.remove.assert_called_once_with([paths[0]])


def test_storage_wraps_provider_failures():
    client = MagicMock()
    storage = SupabaseStorage(client=client)
    client.storage.from_.return_value.upload.side_effect = RuntimeError("provider secret")
    with pytest.raises(StorageUploadError) as error:
        storage.upload(pedido_id=uuid4(), nome_arquivo="test.pdf", conteudo=b"x", content_type="application/pdf")
    assert "provider secret" not in str(error.value)
    client.storage.from_.return_value.remove.side_effect = RuntimeError("provider secret")
    with pytest.raises(StorageDeleteError):
        storage.delete("pedidos/test/test.pdf")

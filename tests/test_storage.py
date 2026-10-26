import importlib
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.infrastructure.storage import supabase_storage as infrastructure
from app.infrastructure.storage.supabase_storage import (
    StorageDeleteError, StorageUploadError, SupabaseStorage,
)
from tests.attachment_samples import pdf


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
    paths = [storage.upload(pedido_id=pedido_id, nome_arquivo="evidencia.PDF",
                            conteudo=pdf(), content_type="application/pdf") for _ in range(2)]
    assert paths[0] != paths[1]
    assert all(path.startswith(f"pedidos/{pedido_id}/") and path.endswith(".pdf") for path in paths)
    assert all(".." not in path for path in paths)
    client.storage.from_.assert_called_with("evidencias-anexos")
    client.storage.from_.return_value.upload.assert_called_with(
        path=paths[1], file=pdf(),
        file_options={"content-type": "application/pdf", "upsert": "false"},
    )
    storage.delete(paths[0])
    client.storage.from_.return_value.remove.assert_called_once_with([paths[0]])


def test_storage_wraps_provider_failures():
    client = MagicMock()
    storage = SupabaseStorage(client=client)
    client.storage.from_.return_value.upload.side_effect = RuntimeError("provider secret")
    with pytest.raises(StorageUploadError) as error:
        storage.upload(pedido_id=uuid4(), nome_arquivo="test.pdf", conteudo=pdf(), content_type="application/pdf")
    assert "provider secret" not in str(error.value)
    client.storage.from_.return_value.remove.side_effect = RuntimeError("provider secret")
    with pytest.raises(StorageDeleteError):
        storage.delete(f"pedidos/{uuid4()}/{uuid4()}.pdf")


@pytest.mark.parametrize("path", [
    "../file.pdf", "/pedidos/file.pdf", "pedidos/../../other.pdf",
    "pedidos\\a\\b.pdf", "https://example.com/file.pdf",
    f"pedidos/{uuid4()}/file.pdf", f"pedidos/{uuid4()}/{uuid4()}.html",
    f"pedidos/{uuid4()}/{uuid4()}.pdf/../other",
])
def test_delete_rejects_unsafe_paths_without_provider_call(path):
    client = MagicMock()
    with pytest.raises(StorageDeleteError):
        SupabaseStorage(client=client).delete(path)
    client.storage.from_.assert_not_called()


@pytest.mark.parametrize("name", ["../../file.pdf", "..\\file.pdf", "file.pdf:stream"])
def test_upload_rejects_path_traversal_without_provider_call(name):
    from app.infrastructure.storage.file_validation import ArquivoInvalidoError
    client = MagicMock()
    with pytest.raises(ArquivoInvalidoError):
        SupabaseStorage(client=client).upload(pedido_id=uuid4(), nome_arquivo=name,
                                            conteudo=pdf(), content_type="application/pdf")
    client.storage.from_.assert_not_called()


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_ambiguous_upload_error_compensates_only_generated_object(cleanup_fails):
    client = MagicMock()
    bucket = client.storage.from_.return_value
    bucket.upload.side_effect = RuntimeError("key=provider-private-secret")
    if cleanup_fails:
        bucket.remove.side_effect = RuntimeError("provider-private-secret")
    storage = SupabaseStorage(client=client, bucket="private-test")
    with pytest.raises(StorageUploadError) as error:
        storage.upload(pedido_id=uuid4(), nome_arquivo="e.pdf", conteudo=pdf(), content_type="application/octet-stream")
    path = bucket.upload.call_args.kwargs["path"]
    bucket.remove.assert_called_once_with([path])
    assert error.value.caminho_storage == path
    assert error.value.compensacao_pendente is cleanup_fails
    assert "provider-private-secret" not in str(error.value)
    assert error.value.__suppress_context__
    assert bucket.upload.call_args.kwargs["file_options"]["content-type"] == "application/pdf"
    client.storage.from_.assert_called_with("private-test")


def test_successful_storage_remove_can_be_repeated():
    client = MagicMock()
    client.storage.from_.return_value.remove.return_value = []
    storage = SupabaseStorage(client=client)
    path = f"pedidos/{uuid4()}/{uuid4()}.pdf"
    storage.delete(path)
    storage.delete(path)
    assert client.storage.from_.return_value.remove.call_count == 2


@pytest.mark.parametrize("url", ["http://remote.example", "https://user:password@example.com", "https://example.com/?key=x"])
def test_storage_rejects_insecure_configuration_without_leaking_values(monkeypatch, url):
    monkeypatch.setattr(infrastructure, "settings", Settings(_env_file=None, SUPABASE_URL=url, SUPABASE_KEY="private-key"))
    factory = MagicMock()
    monkeypatch.setattr(infrastructure, "create_client", factory)
    with pytest.raises(RuntimeError) as error:
        infrastructure.create_supabase_client()
    assert url not in str(error.value)
    assert "private-key" not in str(error.value)
    factory.assert_not_called()

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.infrastructure.storage.supabase_storage import (
    StorageReadError,
    SupabaseStorage,
)


@pytest.fixture
def signed_storage():
    bucket = MagicMock()
    client = SimpleNamespace(
        supabase_url="https://files.example/",
        storage=SimpleNamespace(from_=lambda _: bucket),
    )
    return SupabaseStorage(client=client, bucket="private-evidence"), bucket


def test_signed_link_uses_short_expiry_and_validates_origin(signed_storage):
    storage, bucket = signed_storage
    path = f"pedidos/{uuid4()}/{uuid4()}.pdf"
    bucket.create_signed_url.return_value = {
        "signedURL": "https://files.example/storage/v1/object/sign/private-evidence/file?token=short"
    }
    assert storage.signed_url(path).startswith("https://files.example/")
    bucket.create_signed_url.assert_called_once_with(path, 60)
    bucket.create_signed_url.return_value = {
        "signedURL": "https://attacker.example/steal"
    }
    with pytest.raises(StorageReadError):
        storage.signed_url(path)


def test_invalid_path_never_requests_link(signed_storage):
    storage, bucket = signed_storage
    with pytest.raises(StorageReadError):
        storage.signed_url("../another-bucket/file.pdf")
    bucket.create_signed_url.assert_not_called()


def test_storage_errors_do_not_expose_credentials(signed_storage):
    storage, bucket = signed_storage
    bucket.create_signed_url.side_effect = RuntimeError("private-service-key")
    with pytest.raises(StorageReadError) as error:
        storage.signed_url(f"pedidos/{uuid4()}/{uuid4()}.pdf")
    assert "private-service-key" not in str(error.value)

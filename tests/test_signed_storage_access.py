from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.infrastructure.storage.supabase_storage import SupabaseStorage, StorageReadError


def test_link_assinado_delega_expiracao_ao_storage():
    client = MagicMock()
    client.storage.get_bucket.return_value = {"public": False}
    api = client.storage.from_.return_value
    api.create_signed_url.return_value = {"signedURL": "https://storage.example.com/object/sign/file?token=temporary"}
    caminho = f"pedidos/{uuid4()}/{uuid4()}.pdf"
    url = SupabaseStorage(client=client, bucket="evidencias-anexos").create_signed_url(caminho, expires_in=300)
    api.create_signed_url.assert_called_once_with(caminho, 300)
    assert url.startswith("https://")


@pytest.mark.parametrize("caminho", ["../arquivo.pdf", "pedidos/not-uuid/a.pdf", f"pedidos/{uuid4()}/../segredo.pdf"])
def test_caminho_invalido_nunca_e_assinado(caminho):
    client = MagicMock()
    client.storage.get_bucket.return_value = {"public": False}
    with pytest.raises(StorageReadError):
        SupabaseStorage(client=client, bucket="evidencias-anexos").create_signed_url(caminho)
    client.storage.from_.assert_not_called()


@pytest.mark.parametrize("resposta", [{}, {"signedURL": "javascript:alert(1)"}, {"signedURL": "https://user:password@host/file"}])
def test_resposta_invalida_nao_vaza_detalhes(resposta):
    client = MagicMock()
    client.storage.get_bucket.return_value = {"public": False}
    client.storage.from_.return_value.create_signed_url.return_value = resposta
    with pytest.raises(StorageReadError, match="Nao foi possivel"):
        SupabaseStorage(client=client, bucket="evidencias-anexos").create_signed_url(f"pedidos/{uuid4()}/{uuid4()}.pdf")


from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.infrastructure.storage.supabase_storage import SupabaseStorage, StorageReadError


@pytest.mark.parametrize("metadata", [{"public": False}, SimpleNamespace(public=False)])
def test_link_exige_bucket_privado_e_delega_ttl(metadata):
    client = MagicMock()
    client.storage.get_bucket.return_value = metadata
    api = client.storage.from_.return_value
    api.create_signed_url.return_value = {"signedURL": "https://storage.test.invalid/private?token=temporary"}
    path = f"pedidos/{uuid4()}/{uuid4()}.png"
    assert SupabaseStorage(client=client).create_signed_url(path).startswith("https://")
    api.create_signed_url.assert_called_once_with(path, 300)


@pytest.mark.parametrize("public", [True, None, "false", 0])
def test_privacidade_desconhecida_ou_publica_nunca_assina(public):
    client = MagicMock()
    client.storage.get_bucket.return_value = {"public": public}
    with pytest.raises(StorageReadError):
        SupabaseStorage(client=client).create_signed_url(f"pedidos/{uuid4()}/{uuid4()}.png")
    client.storage.from_.assert_not_called()


@pytest.mark.parametrize("ttl", [0, -1, 601, True, "300"])
def test_ttl_invalido_nao_chega_ao_provedor(ttl):
    client = MagicMock()
    with pytest.raises(StorageReadError):
        SupabaseStorage(client=client).create_signed_url(f"pedidos/{uuid4()}/{uuid4()}.png", expires_in=ttl)
    client.storage.get_bucket.assert_not_called()


@pytest.mark.parametrize("url", ["javascript:alert(1)", "http://remote.invalid/file", "https://user:password@host/file", "https://host/file#fragment"])
def test_url_insegura_nao_e_retornada(url):
    client = MagicMock()
    client.storage.get_bucket.return_value = {"public": False}
    client.storage.from_.return_value.create_signed_url.return_value = {"signedURL": url}
    with pytest.raises(StorageReadError) as error:
        SupabaseStorage(client=client).create_signed_url(f"pedidos/{uuid4()}/{uuid4()}.png")
    assert url not in str(error.value)

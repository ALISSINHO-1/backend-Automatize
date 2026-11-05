from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.infrastructure.storage.supabase_storage import SupabaseStorage, StorageReadError


def test_link_assinado_delega_expiracao_ao_storage():
    client = MagicMock()
    api = client.storage.from_.return_value
    api.create_signed_url.return_value = {"signedURL": "https://storage.example.com/object/sign/file?token=temporary"}
    caminho = f"pedidos/{uuid4()}/{uuid4()}.pdf"
    url = SupabaseStorage(client=client, bucket="evidencias-anexos").create_signed_url(caminho, expires_in=300)
    api.create_signed_url.assert_called_once_with(caminho, 300)
    assert url.startswith("https://")


@pytest.mark.parametrize("caminho", ["../arquivo.pdf", "pedidos/not-uuid/a.pdf", f"pedidos/{uuid4()}/../segredo.pdf"])
def test_caminho_invalido_nunca_e_assinado(caminho):
    client = MagicMock()
    with pytest.raises(StorageReadError):
        SupabaseStorage(client=client, bucket="evidencias-anexos").create_signed_url(caminho)
    client.storage.from_.assert_not_called()


@pytest.mark.parametrize("resposta", [{}, {"signedURL": "javascript:alert(1)"}, {"signedURL": "https://user:password@host/file"}])
def test_resposta_invalida_nao_vaza_detalhes(resposta):
    client = MagicMock()
    client.storage.from_.return_value.create_signed_url.return_value = resposta
    with pytest.raises(StorageReadError, match="Nao foi possivel"):
        SupabaseStorage(client=client, bucket="evidencias-anexos").create_signed_url(f"pedidos/{uuid4()}/{uuid4()}.pdf")

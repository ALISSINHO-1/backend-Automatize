from __future__ import annotations

import re
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from supabase import Client, create_client  # type: ignore

from app.core.config import settings
from app.infrastructure.storage.file_validation import (
    MIME_POR_EXTENSAO,
    validar_arquivo,
)


def create_supabase_client() -> Client:
    """Create a client only when Storage is requested."""
    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL não configurada.")
    if not settings.SUPABASE_KEY:
        raise RuntimeError("SUPABASE_KEY não configurada.")
    try:
        url = urlsplit(settings.SUPABASE_URL)
        local_http = url.scheme == "http" and url.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if (
            not url.hostname
            or (url.scheme != "https" and not local_http)
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError
    except ValueError:
        raise RuntimeError(
            "SUPABASE_URL deve usar HTTPS; HTTP permitido somente para ambiente local."
        ) from None
    try:
        return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    except Exception:
        raise RuntimeError("Falha ao configurar cliente Supabase.") from None


class StorageUploadError(Exception):
    def __init__(
        self, message: str, *, caminho_storage: str, compensacao_pendente: bool = False
    ) -> None:
        self.caminho_storage = caminho_storage
        self.compensacao_pendente = compensacao_pendente
        super().__init__(message)


class StorageReadError(Exception):
    pass


class StorageDeleteError(Exception):
    pass


class SupabaseStorage:
    def __init__(
        self,
        client: Client | None = None,
        bucket: str | None = None,
    ) -> None:
        if client is None:
            client = create_supabase_client()

        self.client = client
        self.bucket = bucket or settings.STORAGE_BUCKET_NAME
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", self.bucket):
            raise ValueError("Nome de bucket inválido.")

    def upload(
        self,
        *,
        pedido_id: UUID,
        nome_arquivo: str,
        conteudo: bytes,
        content_type: str,
    ) -> str:
        if not isinstance(pedido_id, UUID):
            raise ValueError("pedido_id deve ser UUID.")
        extensao, mime_detectado = validar_arquivo(nome_arquivo, conteudo, content_type)
        nome_storage = f"{uuid4()}{extensao}"
        caminho = f"pedidos/{pedido_id}/{nome_storage}"

        try:
            self.client.storage.from_(self.bucket).upload(
                path=caminho,
                file=conteudo,
                file_options={
                    "content-type": mime_detectado,
                    "upsert": "false",
                },
            )
        except Exception:
            # A timeout may happen after the object was received. Only this
            # upload's generated UUID path is eligible for compensation.
            pendente = False
            try:
                self.delete(caminho)
            except StorageDeleteError:
                pendente = True
            raise StorageUploadError(
                "Erro ao enviar arquivo para o Storage.",
                caminho_storage=caminho,
                compensacao_pendente=pendente,
            ) from None

        return caminho

    @staticmethod
    def _validar_caminho(caminho: str) -> None:
        parts = caminho.split("/")
        try:
            if len(parts) != 3 or parts[0] != "pedidos":
                raise ValueError
            if str(UUID(parts[1])) != parts[1]:
                raise ValueError
            stem, dot, extension = parts[2].rpartition(".")
            if (
                not dot
                or str(UUID(stem)) != stem
                or f".{extension}" not in MIME_POR_EXTENSAO
            ):
                raise ValueError
        except (ValueError, AttributeError):
            raise StorageDeleteError("Caminho de Storage inválido.") from None

    def signed_url(self, caminho: str, *, expires_in: int = 60) -> str:
        try:
            self._validar_caminho(caminho)
        except StorageDeleteError:
            raise StorageReadError("Caminho de arquivo inválido.") from None
        if not 1 <= expires_in <= 300:
            raise ValueError("Validade do link deve estar entre 1 e 300 segundos.")
        try:
            result = self.client.storage.from_(self.bucket).create_signed_url(
                caminho, expires_in
            )
            url = result["signedURL"]
            parsed = urlsplit(url)
            expected = urlsplit(str(self.client.supabase_url))
            if parsed.scheme != expected.scheme or parsed.netloc != expected.netloc:
                raise ValueError("Origem inválida no link assinado.")
            return url
        except Exception:
            raise StorageReadError(
                "Não foi possível gerar o acesso ao arquivo."
            ) from None

    def delete(self, caminho: str) -> None:
        self._validar_caminho(caminho)
        try:
            self.client.storage.from_(self.bucket).remove([caminho])
        except Exception:
            raise StorageDeleteError("Erro ao remover arquivo do Storage.") from None

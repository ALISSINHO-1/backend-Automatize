from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from supabase import Client, create_client # type: ignore

from app.core.config import settings


class StorageUploadError(Exception):
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
            if not settings.SUPABASE_URL:
                raise ValueError("SUPABASE_URL não configurada.")

            if not settings.SUPABASE_KEY:
                raise ValueError("SUPABASE_KEY não configurada.")

            client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_KEY,
            )

        self.client = client
        self.bucket = bucket or settings.STORAGE_BUCKET_NAME

    def upload(
        self,
        *,
        pedido_id: UUID,
        nome_arquivo: str,
        conteudo: bytes,
        content_type: str,
    ) -> str:
        extensao = Path(nome_arquivo).suffix.lower()
        nome_storage = f"{uuid4()}{extensao}"
        caminho = f"pedidos/{pedido_id}/{nome_storage}"

        try:
            self.client.storage.from_(self.bucket).upload(
                path=caminho,
                file=conteudo,
                file_options={
                    "content-type": content_type,
                    "upsert": "false",
                },
            )
        except Exception as exc:
            raise StorageUploadError(
                f"Erro ao enviar '{nome_arquivo}' para o Storage."
            ) from exc

        return caminho

    def delete(self, caminho: str) -> None:
        try:
            self.client.storage.from_(self.bucket).remove([caminho])
        except Exception as exc:
            raise StorageDeleteError(
                f"Erro ao remover '{caminho}' do Storage."
            ) from exc
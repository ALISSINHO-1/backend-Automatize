from __future__ import annotations

from pathlib import Path
from typing import Sequence
from uuid import UUID

from sqlalchemy.orm import Session # type: ignore

from app.domain.models.anexo import Anexo
from app.infrastructure.storage.supabase_storage import (
    StorageDeleteError,
    SupabaseStorage,
)
from app.repositories.anexo_repository import AnexoRepository


class AnexoNaoEncontradoError(Exception):
    pass


class ArquivoInvalidoError(Exception):
    pass


class AnexoService:
    EXTENSOES_PERMITIDAS = {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".doc",
        ".docx",
    }

    TAMANHO_MAXIMO_BYTES = 10 * 1024 * 1024  # 10 MB

    def __init__(
        self,
        db: Session,
        repository: AnexoRepository | None = None,
        storage: SupabaseStorage | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AnexoRepository(db)
        self.storage = storage or SupabaseStorage()

    def listar_por_pedido(
        self,
        pedido_id: UUID,
    ) -> Sequence[Anexo]:
        return self.repository.get_by_pedido(pedido_id)

    def buscar_por_id(
        self,
        anexo_id: UUID,
    ) -> Anexo:
        anexo = self.repository.get_by_id(anexo_id)

        if anexo is None:
            raise AnexoNaoEncontradoError(
                f"Anexo {anexo_id} não encontrado."
            )

        return anexo

    def criar(
        self,
        *,
        pedido_id: UUID,
        enviado_por_id: UUID,
        nome_arquivo: str,
        conteudo: bytes,
        content_type: str,
        ocorrencia_id: UUID | None = None,
    ) -> Anexo:
        extensao = Path(nome_arquivo).suffix.lower()

        if extensao not in self.EXTENSOES_PERMITIDAS:
            raise ArquivoInvalidoError(
                f"Extensão '{extensao}' não permitida."
            )

        if not conteudo:
            raise ArquivoInvalidoError(
                "O arquivo está vazio."
            )

        if len(conteudo) > self.TAMANHO_MAXIMO_BYTES:
            raise ArquivoInvalidoError(
                "O arquivo excede o limite de 10 MB."
            )

        caminho_storage = self.storage.upload(
            pedido_id=pedido_id,
            nome_arquivo=nome_arquivo,
            conteudo=conteudo,
            content_type=content_type,
        )

        try:
            anexo = self.repository.create(
                {
                    "pedido_id": pedido_id,
                    "ocorrencia_id": ocorrencia_id,
                    "enviado_por_id": enviado_por_id,
                    "nome_arquivo": nome_arquivo,
                    "caminho_storage": caminho_storage,
                    "extensao": extensao.lstrip("."),
                    "tamanho_bytes": len(conteudo),
                }
            )

            self.db.commit()

        except Exception:
            self.db.rollback()

            # Compensação: evita arquivo órfão caso o banco falhe.
            try:
                self.storage.delete(caminho_storage)
            except StorageDeleteError:
                pass

            raise

        # A refresh failure after commit cannot undo persisted metadata. Keep
        # its object in Storage so the committed record never points to a deletion.
        self.db.refresh(anexo)
        return anexo

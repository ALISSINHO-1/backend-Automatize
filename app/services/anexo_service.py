from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy.orm import Session # type: ignore
from sqlalchemy.exc import DBAPIError

from app.domain.models.anexo import Anexo
from app.infrastructure.storage.file_validation import (
    ArquivoInvalidoError,
    MIME_POR_EXTENSAO,
    TAMANHO_MAXIMO_BYTES,
    validar_arquivo,
)
from app.infrastructure.storage.supabase_storage import (
    StorageDeleteError,
    SupabaseStorage,
)
from app.repositories.anexo_repository import AnexoRepository


class AnexoNaoEncontradoError(Exception):
    pass


class AnexoCompensacaoError(RuntimeError):
    """A failed write also needs operational cleanup; do not hide that failure."""

    def __init__(self, caminho_storage: str) -> None:
        self.caminho_storage = caminho_storage
        super().__init__("Falha ao compensar anexo; reconciliação do Storage necessária.")


class AnexoCommitIncertoError(RuntimeError):
    def __init__(self, caminho_storage: str) -> None:
        self.caminho_storage = caminho_storage
        super().__init__("Confirmação de commit indisponível; reconciliação do anexo necessária.")


class AnexoService:
    EXTENSOES_PERMITIDAS = set(MIME_POR_EXTENSAO)
    TAMANHO_MAXIMO_BYTES = TAMANHO_MAXIMO_BYTES

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
        if not isinstance(pedido_id, UUID) or not isinstance(enviado_por_id, UUID):
            raise ValueError("pedido_id e enviado_por_id devem ser UUIDs.")
        extensao, mime_detectado = validar_arquivo(nome_arquivo, conteudo, content_type)

        caminho_storage: str | None = None
        commit_iniciado = False
        try:
            if ocorrencia_id is not None:
                self.repository.validar_ocorrencia_do_pedido(
                    pedido_id=pedido_id, ocorrencia_id=ocorrencia_id,
                )
            caminho_storage = self.storage.upload(
                pedido_id=pedido_id,
                nome_arquivo=nome_arquivo,
                conteudo=conteudo,
                content_type=mime_detectado,
            )
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

            commit_iniciado = True
            self.db.commit()

        except Exception as exc:
            commit_incerto = commit_iniciado and isinstance(exc, DBAPIError) and exc.connection_invalidated
            try:
                self.db.rollback()
            finally:
                # Cleanup must still run when rollback itself fails.
                if caminho_storage is not None:
                    # A lost connection while committing does not prove that
                    # metadata was rolled back. Preserve the object for review.
                    if commit_incerto:
                        raise AnexoCommitIncertoError(caminho_storage) from None
                    try:
                        self.storage.delete(caminho_storage)
                    except StorageDeleteError:
                        raise AnexoCompensacaoError(caminho_storage) from None
            raise

        # A refresh failure after commit cannot undo persisted metadata. Keep
        # its object in Storage so the committed record never points to a deletion.
        self.db.refresh(anexo)
        return anexo

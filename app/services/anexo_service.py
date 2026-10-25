from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy.orm import Session # type: ignore

from app.core.exceptions import ArquivoInvalidoException
from app.domain.models.anexo import Anexo
from app.domain.models.auditoria_log import AuditoriaLog
from app.domain.regras import arquivos
from app.infrastructure.storage.supabase_storage import (
    StorageDeleteError,
    SupabaseStorage,
)
from app.repositories.anexo_repository import AnexoRepository


class AnexoNaoEncontradoError(Exception):
    pass


# Mantido como alias: a validacao de conteudo e compartilhada com as evidencias.
ArquivoInvalidoError = ArquivoInvalidoException


class AnexoService:
    EXTENSOES_PERMITIDAS = arquivos.EXTENSOES_PERMITIDAS

    TAMANHO_MAXIMO_BYTES = arquivos.TAMANHO_MAXIMO_BYTES

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
        content_type: str | None = None,
        ocorrencia_id: UUID | None = None,
    ) -> Anexo:
        # O content_type informado pelo cliente nao e confiavel; o Storage recebe
        # o tipo detectado a partir do conteudo real.
        arquivo = arquivos.validar_arquivo(nome_arquivo, conteudo)

        caminho_storage = self.storage.upload(
            pedido_id=pedido_id,
            nome_arquivo=arquivo.nome_arquivo,
            conteudo=conteudo,
            content_type=arquivo.content_type,
        )

        try:
            anexo = self.repository.create(
                {
                    "pedido_id": pedido_id,
                    "ocorrencia_id": ocorrencia_id,
                    "enviado_por_id": enviado_por_id,
                    "nome_arquivo": arquivo.nome_arquivo,
                    "caminho_storage": caminho_storage,
                    "extensao": arquivo.extensao,
                    "tamanho_bytes": arquivo.tamanho_bytes,
                }
            )
            self.db.add(
                AuditoriaLog(
                    usuario_id=enviado_por_id,
                    pedido_id=pedido_id,
                    acao="ENVIO_EVIDENCIA",
                    detalhes={
                        "anexo_id": str(anexo.id),
                        "nome_arquivo": arquivo.nome_arquivo,
                        "tamanho_bytes": arquivo.tamanho_bytes,
                        "ocorrencia_id": str(ocorrencia_id) if ocorrencia_id else None,
                    },
                    created_at=datetime.now(timezone.utc),
                )
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

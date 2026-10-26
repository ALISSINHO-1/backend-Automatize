from __future__ import annotations

from typing import Any, Mapping, Sequence
from uuid import UUID

from sqlalchemy import select # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.anexo import Anexo
from app.domain.models.ocorrencia import Ocorrencia
from app.domain.models.pedido import Pedido
from app.repositories.base_repository import BaseRepository


class OcorrenciaNaoEncontradaError(ValueError):
    pass


class OcorrenciaDeOutroPedidoError(ValueError):
    pass


class AnexoRepository(BaseRepository[Anexo]):
    protected_fields = BaseRepository.protected_fields | frozenset({
        "pedido_id", "ocorrencia_id", "enviado_por_id", "caminho_storage",
    })

    def __init__(self, db: Session) -> None:
        super().__init__(Anexo, db)

    def validar_ocorrencia_do_pedido(self, *, pedido_id: UUID, ocorrencia_id: UUID) -> None:
        if not isinstance(pedido_id, UUID) or not isinstance(ocorrencia_id, UUID):
            raise ValueError("pedido_id e ocorrencia_id devem ser UUIDs.")
        # FOR UPDATE also prevents reassignment to a different pedido while
        # the service uploads and persists the attachment in this transaction.
        vinculo = self.db.scalar(
            select(Ocorrencia.pedido_id).where(Ocorrencia.id == ocorrencia_id).with_for_update()
        )
        if vinculo is None:
            raise OcorrenciaNaoEncontradaError("Ocorrência não encontrada.")
        if vinculo != pedido_id:
            raise OcorrenciaDeOutroPedidoError("Ocorrência não pertence ao pedido informado.")

    def create(self, data: Mapping[str, Any]) -> Anexo:
        if data.get("ocorrencia_id") is not None:
            self.validar_ocorrencia_do_pedido(
                pedido_id=data["pedido_id"], ocorrencia_id=data["ocorrencia_id"],
            )
        return super().create(data)

    def get_by_pedido_for_cliente(self, pedido_id: UUID, *, cliente_id: UUID) -> Sequence[Anexo]:
        if not isinstance(cliente_id, UUID):
            raise ValueError("cliente_id deve ser UUID.")
        return self.db.scalars(
            select(Anexo).join(Pedido, Anexo.pedido_id == Pedido.id)
            .where(Pedido.id == pedido_id, Pedido.cliente_id == cliente_id)
            .order_by(Anexo.created_at, Anexo.id)
        ).all()

    def get_by_pedido_for_responsavel(self, pedido_id: UUID, *, responsavel_id: UUID) -> Sequence[Anexo]:
        if not isinstance(responsavel_id, UUID):
            raise ValueError("responsavel_id deve ser UUID.")
        return self.db.scalars(
            select(Anexo).join(Pedido, Anexo.pedido_id == Pedido.id)
            .where(Pedido.id == pedido_id, Pedido.responsavel_id == responsavel_id)
            .order_by(Anexo.created_at, Anexo.id)
        ).all()

    def get_by_pedido(
        self,
        pedido_id: UUID,
    ) -> Sequence[Anexo]:
        stmt = (
            select(Anexo)
            .where(Anexo.pedido_id == pedido_id)
            .order_by(Anexo.created_at.desc())
        )

        return self.db.scalars(stmt).all()

    def get_by_ocorrencia(
        self,
        ocorrencia_id: UUID,
    ) -> Sequence[Anexo]:
        stmt = (
            select(Anexo)
            .where(Anexo.ocorrencia_id == ocorrencia_id)
            .order_by(Anexo.created_at.desc())
        )

        return self.db.scalars(stmt).all()

    def get_by_usuario(
        self,
        usuario_id: UUID,
    ) -> Sequence[Anexo]:
        stmt = (
            select(Anexo)
            .where(Anexo.enviado_por_id == usuario_id)
            .order_by(Anexo.created_at.desc())
        )

        return self.db.scalars(stmt).all()

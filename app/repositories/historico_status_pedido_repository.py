from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.historico_status_pedido import HistoricoStatusPedido
from app.repositories.base_repository import BaseRepository


class HistoricoStatusPedidoRepository(
    BaseRepository[HistoricoStatusPedido]
):
    def __init__(self, db: Session) -> None:
        super().__init__(HistoricoStatusPedido, db)

    def get_by_pedido(
        self,
        pedido_id: UUID,
    ) -> Sequence[HistoricoStatusPedido]:
        stmt = (
            select(HistoricoStatusPedido)
            .where(HistoricoStatusPedido.pedido_id == pedido_id)
            .order_by(HistoricoStatusPedido.created_at.asc())
        )

        return self.db.scalars(stmt).all()

    def get_by_usuario(
        self,
        usuario_id: UUID,
    ) -> Sequence[HistoricoStatusPedido]:
        stmt = (
            select(HistoricoStatusPedido)
            .where(HistoricoStatusPedido.usuario_id == usuario_id)
            .order_by(HistoricoStatusPedido.created_at.desc())
        )

        return self.db.scalars(stmt).all()
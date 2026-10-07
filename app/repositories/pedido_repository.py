from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.enums import StatusPedidoEnum
from app.domain.models.pedido import Pedido
from app.repositories.base_repository import BaseRepository


class PedidoRepository(BaseRepository[Pedido]):

    def __init__(self, db: Session) -> None:
        super().__init__(Pedido, db)

    def get_by_codigo(
        self,
        codigo: str,
    ) -> Pedido | None:
        stmt = select(Pedido).where(
            Pedido.codigo_identificador == codigo
        )

        return self.db.scalar(stmt)

    def get_by_cliente(
        self,
        cliente_id: UUID,
    ) -> Sequence[Pedido]:
        stmt = (
            select(Pedido)
            .where(Pedido.cliente_id == cliente_id)
            .order_by(Pedido.created_at.desc())
        )

        return self.db.scalars(stmt).all()

    def get_by_status(
        self,
        status: StatusPedidoEnum,
    ) -> Sequence[Pedido]:
        stmt = (
            select(Pedido)
            .where(Pedido.status == status)
            .order_by(Pedido.created_at.desc())
        )

        return self.db.scalars(stmt).all()

    def get_by_responsavel(
        self,
        responsavel_id: UUID,
    ) -> Sequence[Pedido]:
        stmt = (
            select(Pedido)
            .where(Pedido.responsavel_id == responsavel_id)
            .order_by(Pedido.created_at.desc())
        )

        return self.db.scalars(stmt).all()
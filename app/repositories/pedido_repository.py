from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models.enums import StatusPedidoEnum
from app.domain.models.pedido import Pedido
from app.repositories.base_repository import BaseRepository


class PedidoRepository(BaseRepository[Pedido]):
    """
    Repositório responsável pelas operações de persistência
    específicas da entidade Pedido.

    O controle de transação (commit/rollback) pertence
    à camada Service/Use Case.
    """

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

    def exists_by_codigo(
        self,
        codigo: str,
    ) -> bool:
        stmt = (
            select(Pedido.id)
            .where(
                Pedido.codigo_identificador == codigo
            )
            .limit(1)
        )

        return self.db.scalar(stmt) is not None

    def get_by_cliente(
        self,
        cliente_id: UUID,
    ) -> Sequence[Pedido]:
        stmt = (
            select(Pedido)
            .where(
                Pedido.cliente_id == cliente_id
            )
            .order_by(
                Pedido.created_at.desc()
            )
        )

        return self.db.scalars(stmt).all()

    def get_by_status(
        self,
        status: StatusPedidoEnum,
    ) -> Sequence[Pedido]:
        stmt = (
            select(Pedido)
            .where(
                Pedido.status == status
            )
            .order_by(
                Pedido.created_at.desc()
            )
        )

        return self.db.scalars(stmt).all()

    def get_by_responsavel(
        self,
        responsavel_id: UUID,
    ) -> Sequence[Pedido]:
        stmt = (
            select(Pedido)
            .where(
                Pedido.responsavel_id == responsavel_id
            )
            .order_by(
                Pedido.created_at.desc()
            )
        )

        return self.db.scalars(stmt).all()

    def list_for_access_scope(
        self,
        *,
        offset: int,
        limit: int,
        cliente_id: UUID | None = None,
        responsavel_id: UUID | None = None,
    ) -> Sequence[Pedido]:
        """List demands, applying any ownership filter before pagination."""
        stmt = select(Pedido)
        if cliente_id is not None:
            stmt = stmt.where(Pedido.cliente_id == cliente_id)
        if responsavel_id is not None:
            stmt = stmt.where(Pedido.responsavel_id == responsavel_id)

        stmt = (
            stmt.order_by(Pedido.created_at.asc(), Pedido.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def get_by_id_for_access_scope(
        self,
        pedido_id: UUID,
        *,
        cliente_id: UUID | None = None,
        responsavel_id: UUID | None = None,
    ) -> Pedido | None:
        """Fetch one demand inside its ownership scope, if one is supplied."""
        stmt = select(Pedido).where(Pedido.id == pedido_id)
        if cliente_id is not None:
            stmt = stmt.where(Pedido.cliente_id == cliente_id)
        if responsavel_id is not None:
            stmt = stmt.where(Pedido.responsavel_id == responsavel_id)
        return self.db.scalar(stmt)

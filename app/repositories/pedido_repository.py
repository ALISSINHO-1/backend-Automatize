from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select, func, or_
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

    protected_fields = BaseRepository.protected_fields | frozenset({"cliente_id"})

    def get_by_id_for_cliente(
        self, pedido_id: UUID, *, cliente_id: UUID
    ) -> Pedido | None:
        self._require_uuid(cliente_id)
        return self.get_by_id_for_access_scope(pedido_id, cliente_id=cliente_id)

    def get_by_id_for_responsavel(
        self, pedido_id: UUID, *, responsavel_id: UUID
    ) -> Pedido | None:
        self._require_uuid(responsavel_id)
        return self.get_by_id_for_access_scope(pedido_id, responsavel_id=responsavel_id)

    @staticmethod
    def _require_uuid(value: UUID) -> None:
        if not isinstance(value, UUID):
            raise ValueError("O identificador de escopo deve ser UUID.")

    def get_by_codigo(
        self,
        codigo: str,
    ) -> Pedido | None:
        stmt = select(Pedido).where(Pedido.codigo_identificador == codigo)

        return self.db.scalar(stmt)

    def exists_by_codigo(
        self,
        codigo: str,
    ) -> bool:
        stmt = select(Pedido.id).where(Pedido.codigo_identificador == codigo).limit(1)

        return self.db.scalar(stmt) is not None

    def get_by_cliente(
        self,
        cliente_id: UUID,
    ) -> Sequence[Pedido]:
        self._require_uuid(cliente_id)
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
        self._require_uuid(responsavel_id)
        stmt = (
            select(Pedido)
            .where(Pedido.responsavel_id == responsavel_id)
            .order_by(Pedido.created_at.desc())
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

    def consultar_filtrado(
        self, *, scope, filtros, offset: int, limit: int, incluir_totais: bool
    ):
        conditions = [getattr(Pedido, campo) == valor for campo, valor in scope.items()]
        for campo in ("cliente_id", "responsavel_id"):
            if campo in filtros:
                conditions.append(getattr(Pedido, campo) == filtros[campo])
        if "estado" in filtros:
            conditions.append(Pedido.status == filtros["estado"])
        if "inicio" in filtros:
            conditions.append(Pedido.created_at >= filtros["inicio"])
        if "fim" in filtros:
            conditions.append(Pedido.created_at <= filtros["fim"])
        if "busca" in filtros:
            termo = (
                filtros["busca"]
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions.append(
                or_(
                    Pedido.titulo.ilike(f"%{termo}%", escape="\\"),
                    Pedido.codigo_identificador.ilike(f"%{termo}%", escape="\\"),
                )
            )
        registros = self.db.scalars(
            select(Pedido)
            .where(*conditions)
            .order_by(Pedido.created_at, Pedido.id)
            .offset(offset)
            .limit(limit)
        ).all()
        contagens = None
        if incluir_totais:
            contagens = {estado.value: 0 for estado in StatusPedidoEnum}
            for estado, total in self.db.execute(
                select(Pedido.status, func.count())
                .where(*conditions)
                .group_by(Pedido.status)
            ):
                contagens[estado.value] = total
        return registros, contagens

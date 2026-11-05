from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.models.enums import StatusPedidoEnum
from app.domain.models.pedido import Pedido
from app.domain.schemas.demanda_filtros import DemandaFiltros
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

    def get_by_id_for_update(self, pedido_id: UUID) -> Pedido | None:
        self._require_uuid(pedido_id)
        return self.db.scalar(
            select(Pedido).where(Pedido.id == pedido_id).with_for_update()
            .execution_options(populate_existing=True)
        )

    def get_by_id_for_cliente(self, pedido_id: UUID, *, cliente_id: UUID) -> Pedido | None:
        self._require_uuid(cliente_id)
        return self.get_by_id_for_access_scope(pedido_id, cliente_id=cliente_id)

    def get_by_id_for_responsavel(self, pedido_id: UUID, *, responsavel_id: UUID) -> Pedido | None:
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
        self._require_uuid(cliente_id)
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
        self._require_uuid(responsavel_id)
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
        filtros: DemandaFiltros | None = None,
    ) -> Sequence[Pedido]:
        """List demands, applying any ownership filter before pagination."""
        stmt = self._consulta_filtrada(cliente_id=cliente_id, responsavel_id=responsavel_id, filtros=filtros)

        stmt = (
            stmt.order_by(Pedido.created_at.asc(), Pedido.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    @staticmethod
    def _consulta_filtrada(*, cliente_id=None, responsavel_id=None, filtros=None):
        stmt = select(Pedido)
        # O escopo do JWT e os filtros do usuario sao SEMPRE cumulativos.
        if cliente_id is not None:
            stmt = stmt.where(Pedido.cliente_id == cliente_id)
        if responsavel_id is not None:
            stmt = stmt.where(Pedido.responsavel_id == responsavel_id)
        if filtros is not None:
            for campo in ("cliente_id", "responsavel_id", "status"):
                valor = getattr(filtros, campo)
                if valor is not None:
                    stmt = stmt.where(getattr(Pedido, campo) == valor)
            if filtros.busca is not None:
                # Busca literal: % e _ nao viram curingas fornecidos pelo cliente.
                termo = filtros.busca.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                stmt = stmt.where(or_(Pedido.titulo.ilike(f"%{termo}%", escape="\\"),
                                      Pedido.codigo_identificador.ilike(f"%{termo}%", escape="\\")))
            if filtros.criado_de is not None:
                stmt = stmt.where(Pedido.created_at >= filtros.criado_de)
            if filtros.criado_ate is not None:
                stmt = stmt.where(Pedido.created_at <= filtros.criado_ate)
        return stmt

    def indicadores_for_access_scope(self, *, filtros=None, **scope):
        filtrados = self._consulta_filtrada(filtros=filtros, **scope).subquery()
        consulta = select(filtrados.c.status, func.count()).group_by(filtrados.c.status)
        contagens = {estado.value: 0 for estado in StatusPedidoEnum}
        for estado, quantidade in self.db.execute(consulta):
            contagens[estado.value] = quantidade
        return {"total": sum(contagens.values()), "por_status": contagens}

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

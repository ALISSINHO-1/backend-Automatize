from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.models.enums import PerfilEnum
from app.domain.models.pedido import Pedido
from app.domain.models.user import User
from app.repositories.pedido_repository import PedidoRepository


class DemandAccessDenied(Exception):
    """Raised when a persisted profile has no demand-read policy."""


class DemandaQueryService:
    """Authorize and coordinate read-only demand queries."""

    def __init__(self, db: Session) -> None:
        self.pedidos = PedidoRepository(db)

    @staticmethod
    def access_scope(user: User) -> dict[str, UUID]:
        if user.perfil == PerfilEnum.ADMIN:
            return {}
        if user.perfil == PerfilEnum.CLIENTE:
            return {"cliente_id": user.id}
        if user.perfil == PerfilEnum.TECNICO:
            return {"responsavel_id": user.id}
        raise DemandAccessDenied

    def list_demands(
        self,
        user: User,
        *,
        offset: int,
        limit: int,
    ) -> Sequence[Pedido]:
        scope = self.access_scope(user)
        return self.pedidos.list_for_access_scope(
            offset=offset,
            limit=limit,
            **scope,
        )

    def consultar_filtrado(
        self, user: User, *, filtros, offset: int, limit: int, incluir_totais: bool
    ):
        scope = self.access_scope(user)
        return self.pedidos.consultar_filtrado(
            scope=scope,
            filtros=filtros,
            offset=offset,
            limit=limit,
            incluir_totais=incluir_totais,
        )

    def get_demand(self, user: User, pedido_id: UUID) -> Pedido | None:
        scope = self.access_scope(user)
        return self.pedidos.get_by_id_for_access_scope(pedido_id, **scope)

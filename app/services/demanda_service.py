from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AcessoNegadoException
from app.domain.models.pedido import Pedido
from app.domain.models.user import User
from app.domain.regras import autorizacao
from app.repositories.pedido_repository import PedidoRepository


class DemandAccessDenied(Exception):
    """Raised when a persisted profile has no demand-read policy."""


class DemandaQueryService:
    """Authorize and coordinate read-only demand queries."""

    def __init__(self, db: Session) -> None:
        self.pedidos = PedidoRepository(db)

    @staticmethod
    def access_scope(user: User) -> dict[str, UUID]:
        # Mesma politica das rotas de escrita (regras.autorizacao, SCRUM-95).
        try:
            return autorizacao.escopo_leitura(user)
        except AcessoNegadoException:
            raise DemandAccessDenied from None

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

    def get_demand(self, user: User, pedido_id: UUID) -> Pedido | None:
        scope = self.access_scope(user)
        return self.pedidos.get_by_id_for_access_scope(pedido_id, **scope)

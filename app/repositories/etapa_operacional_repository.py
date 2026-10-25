from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.etapa_operacional import EtapaOperacional
from app.repositories.base_repository import BaseRepository


class EtapaOperacionalRepository(BaseRepository[EtapaOperacional]):
    def __init__(self, db: Session) -> None:
        super().__init__(EtapaOperacional, db)

    def get_by_pedido(
        self,
        pedido_id: UUID,
    ) -> Sequence[EtapaOperacional]:
        stmt = (
            select(EtapaOperacional)
            .where(EtapaOperacional.pedido_id == pedido_id)
            .order_by(EtapaOperacional.created_at.asc(), EtapaOperacional.id.asc())
        )

        return self.db.scalars(stmt).all()

    def get_by_id_and_pedido(
        self,
        etapa_id: UUID,
        pedido_id: UUID,
    ) -> EtapaOperacional | None:
        stmt = select(EtapaOperacional).where(
            EtapaOperacional.id == etapa_id,
            EtapaOperacional.pedido_id == pedido_id,
        )

        return self.db.scalar(stmt)

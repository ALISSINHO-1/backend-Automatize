from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.auditoria_log import AuditoriaLog
from app.repositories.base_repository import BaseRepository


class AuditoriaLogRepository(BaseRepository[AuditoriaLog]):
    def __init__(self, db: Session) -> None:
        super().__init__(AuditoriaLog, db)

    def get_by_pedido(
        self,
        pedido_id: UUID,
    ) -> Sequence[AuditoriaLog]:
        stmt = (
            select(AuditoriaLog)
            .where(AuditoriaLog.pedido_id == pedido_id)
            .order_by(AuditoriaLog.created_at.asc(), AuditoriaLog.id.asc())
        )

        return self.db.scalars(stmt).all()

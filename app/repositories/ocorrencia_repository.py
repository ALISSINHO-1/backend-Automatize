from uuid import UUID

from sqlalchemy import select

from app.domain.models.ocorrencia import Ocorrencia
from app.repositories.base_repository import BaseRepository


class OcorrenciaRepository(BaseRepository[Ocorrencia]):
    def __init__(self, db):
        super().__init__(Ocorrencia, db)

    def listar(self, pedido_id: UUID, *, offset: int, limit: int):
        return self.db.scalars(
            select(Ocorrencia)
            .where(Ocorrencia.pedido_id == pedido_id)
            .order_by(Ocorrencia.created_at, Ocorrencia.id)
            .offset(offset)
            .limit(limit)
        ).all()

    def obter(self, pedido_id: UUID, ocorrencia_id: UUID):
        return self.db.scalar(
            select(Ocorrencia).where(
                Ocorrencia.pedido_id == pedido_id,
                Ocorrencia.id == ocorrencia_id,
            )
        )

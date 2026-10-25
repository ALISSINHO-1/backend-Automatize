from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.anexo import Anexo
from app.repositories.base_repository import BaseRepository


class AnexoRepository(BaseRepository[Anexo]):
    def __init__(self, db: Session) -> None:
        super().__init__(Anexo, db)

    def get_by_pedido(
        self,
        pedido_id: UUID,
    ) -> Sequence[Anexo]:
        stmt = (
            select(Anexo)
            .where(Anexo.pedido_id == pedido_id)
            .order_by(Anexo.created_at.desc())
        )

        return self.db.scalars(stmt).all()

    def get_by_ocorrencia(
        self,
        ocorrencia_id: UUID,
    ) -> Sequence[Anexo]:
        stmt = (
            select(Anexo)
            .where(Anexo.ocorrencia_id == ocorrencia_id)
            .order_by(Anexo.created_at.desc())
        )

        return self.db.scalars(stmt).all()

    def get_by_usuario(
        self,
        usuario_id: UUID,
    ) -> Sequence[Anexo]:
        stmt = (
            select(Anexo)
            .where(Anexo.enviado_por_id == usuario_id)
            .order_by(Anexo.created_at.desc())
        )

        return self.db.scalars(stmt).all()
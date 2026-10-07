from __future__ import annotations

from typing import Any, Generic, Mapping, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import select # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.core.database import Base


ModelType = TypeVar("ModelType", bound=Base) # type: ignore


class BaseRepository(Generic[ModelType]):
    """
    Repositório base para operações comuns de persistência.

    Responsabilidade:
    - encapsular acesso ao SQLAlchemy;
    - fornecer CRUD básico;
    - não conter regras de negócio.
    """

    def __init__(
        self,
        model: type[ModelType],
        db: Session,
    ) -> None:
        self.model = model
        self.db = db

    def get_by_id(self, entity_id: UUID) -> ModelType | None:
        return self.db.get(self.model, entity_id)

    def get_all(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ModelType]:
        stmt = (
            select(self.model)
            .offset(offset)
            .limit(limit)
        )

        return self.db.scalars(stmt).all()

    def create(
        self,
        data: Mapping[str, Any],
    ) -> ModelType:
        entity = self.model(**data)

        self.db.add(entity)
        self.db.flush()
        self.db.refresh(entity)

        return entity

    def update(
        self,
        entity: ModelType,
        data: Mapping[str, Any],
    ) -> ModelType:
        for field, value in data.items():
            if hasattr(entity, field):
                setattr(entity, field, value)

        self.db.flush()
        self.db.refresh(entity)

        return entity

    def delete(
        self,
        entity: ModelType,
    ) -> None:
        self.db.delete(entity)
        self.db.flush()
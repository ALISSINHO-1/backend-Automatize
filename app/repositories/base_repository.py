from __future__ import annotations

from typing import Any, Generic, Mapping, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import select # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.core.database import Base


ModelType = TypeVar("ModelType", bound=Base) # type: ignore


class BaseRepository(Generic[ModelType]):
    """
    Repositório base para operações genéricas de persistência.

    Responsabilidades:
    - consultas básicas;
    - criação;
    - atualização;
    - exclusão;
    - sincronização da sessão com flush().

    O controle da transação (commit/rollback) pertence
    à camada Service/Use Case.
    """

    protected_fields: frozenset[str] = frozenset(
        {
            "id",
            "created_at",
            "updated_at",
        }
    )

    def __init__(
        self,
        model: type[ModelType],
        db: Session,
    ) -> None:
        self.model = model
        self.db = db

    def get_by_id(
        self,
        entity_id: UUID,
    ) -> ModelType | None:
        return self.db.get(
            self.model,
            entity_id,
        )

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

        # Impede alteração de campos internos/sensíveis.
        protected = (
            set(data.keys())
            & self.protected_fields
        )

        if protected:
            fields = ", ".join(
                sorted(protected)
            )

            raise ValueError(
                "Não é permitido alterar "
                f"campos protegidos: {fields}"
            )

        # Impede campos que não existem no model.
        for field, value in data.items():

            if not hasattr(entity, field):
                raise ValueError(
                    f"Campo '{field}' não existe "
                    f"em {self.model.__name__}."
                )

            setattr(
                entity,
                field,
                value,
            )

        self.db.flush()
        self.db.refresh(entity)

        return entity

    def delete(
        self,
        entity: ModelType,
    ) -> None:

        self.db.delete(entity)
        self.db.flush()
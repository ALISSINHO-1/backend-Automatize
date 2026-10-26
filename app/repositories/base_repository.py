from __future__ import annotations

from typing import Any, Generic, Mapping, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import Uuid, inspect, select # type: ignore
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
        if not isinstance(entity_id, UUID):
            raise ValueError("O identificador deve ser UUID.")
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
        self._validate_columns(data)
        # Services may supply an evidence UUID (e.g. formal acceptance). Keep
        # that contract, while rejecting server timestamps and non-column data.
        internal = set(data) & {"created_at", "updated_at"}
        if internal:
            raise ValueError("Não é permitido definir campos internos na criação.")
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

        # Validate the entire mapping before changing any in-memory state.
        self._validate_columns(data)
        for field, value in data.items():
            setattr(
                entity,
                field,
                value,
            )

        self.db.flush()
        self.db.refresh(entity)

        return entity

    def _validate_columns(self, data: Mapping[str, Any]) -> None:
        columns = inspect(self.model).columns
        if any(field not in columns.keys() for field in data):
            raise ValueError(f"Campo não existe nas colunas de {self.model.__name__}.")
        for field, value in data.items():
            if isinstance(columns[field].type, Uuid) and value is not None and not isinstance(value, UUID):
                raise ValueError("Identificadores de persistência devem ser UUIDs.")

    def delete(
        self,
        entity: ModelType,
    ) -> None:

        self.db.delete(entity)
        self.db.flush()

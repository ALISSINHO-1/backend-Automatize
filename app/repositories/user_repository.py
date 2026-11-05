from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Exists

from app.domain.models.user import User
from app.domain.models.enums import PerfilEnum
from app.domain.models.pedido import Pedido
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    protected_fields = BaseRepository.protected_fields | frozenset({"perfil", "ativo", "senha_hash"})

    def __init__(self, db: Session) -> None:
        super().__init__(User, db)

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return self.db.scalar(statement)

    def get_all(self, *, offset: int = 0, limit: int = 100) -> Sequence[User]:
        raise ValueError("Use uma consulta específica de usuários com escopo explícito.")

    @staticmethod
    def _validar_pagina(offset: int, limit: int) -> None:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Paginação inválida.")

    @staticmethod
    def _validar_uuid(value: UUID) -> None:
        if not isinstance(value, UUID):
            raise ValueError("O identificador de escopo deve ser UUID.")

    def list_tecnicos(self, *, offset: int = 0, limit: int = 100) -> Sequence[User]:
        self._validar_pagina(offset, limit)
        return self.db.scalars(
            select(User).where(User.perfil == PerfilEnum.TECNICO)
            .order_by(User.id).offset(offset).limit(limit)
        ).all()

    @staticmethod
    def _vinculo_por_pedido(responsavel_id: UUID) -> Exists:
        # This is responsibility for a pedido, not a permanent client-company
        # relationship. No independent association exists in the current schema.
        return select(Pedido.id).where(
            Pedido.cliente_id == User.id,
            Pedido.responsavel_id == responsavel_id,
        ).exists()

    def list_clientes_por_responsavel(
        self, *, responsavel_id: UUID, offset: int = 0, limit: int = 100,
    ) -> Sequence[User]:
        self._validar_uuid(responsavel_id)
        self._validar_pagina(offset, limit)
        return self.db.scalars(
            select(User).where(
                User.perfil == PerfilEnum.CLIENTE,
                self._vinculo_por_pedido(responsavel_id),
            ).order_by(User.id).offset(offset).limit(limit)
        ).all()

    def get_cliente_por_responsavel(self, cliente_id: UUID, *, responsavel_id: UUID) -> User | None:
        self._validar_uuid(cliente_id)
        self._validar_uuid(responsavel_id)
        return self.db.scalar(select(User).where(
            User.id == cliente_id,
            User.perfil == PerfilEnum.CLIENTE,
            self._vinculo_por_pedido(responsavel_id),
        ))

    def get_cliente_proprio(self, *, usuario_id: UUID) -> User | None:
        self._validar_uuid(usuario_id)
        return self.db.scalar(select(User).where(User.id == usuario_id, User.perfil == PerfilEnum.CLIENTE))

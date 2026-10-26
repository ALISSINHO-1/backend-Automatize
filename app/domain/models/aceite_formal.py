import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, event, text # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore

from app.core.database import Base
from app.core.exceptions import RegistroImutavelException


class AceiteFormal(Base):
    """Aceite formal do cliente. Imutavel apos gravado (SCRUM-72): o ORM recusa
    UPDATE/DELETE e o banco tem trigger com a mesma regra."""

    __tablename__ = "aceites_formais"

    __table_args__ = (
        UniqueConstraint("pedido_id", name="uq_aceites_formais_pedido_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    pedido_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pedidos.id"),
        nullable=False,
    )

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    data_hora_aceite: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    versao_entregavel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    declaracao_aceite: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    hash_validacao: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )


@event.listens_for(AceiteFormal, "before_update")
@event.listens_for(AceiteFormal, "before_delete")
def _bloquear_alteracao_aceite(mapper, connection, target) -> None:
    raise RegistroImutavelException("O aceite formal e imutavel e nao pode ser alterado nem excluido.")

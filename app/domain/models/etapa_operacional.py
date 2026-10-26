import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, text # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore

from app.core.database import Base


class EtapaOperacional(Base):
    """Etapa do checklist operacional; pendencias bloqueiam a HOMOLOGACAO (SCRUM-71)."""

    __tablename__ = "etapas_operacionais"

    __table_args__ = (
        CheckConstraint(
            "(concluida AND concluida_em IS NOT NULL AND concluida_por_id IS NOT NULL)"
            " OR (NOT concluida AND concluida_em IS NULL AND concluida_por_id IS NULL)",
            name="etapas_operacionais_conclusao_check",
        ),
        Index("ix_etapas_operacionais_pedido_id", "pedido_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    pedido_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pedidos.id", ondelete="CASCADE"),
        nullable=False,
    )

    descricao: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    concluida: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    concluida_por_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
    )

    criado_por_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ( # type: ignore
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore

from app.core.database import Base
from app.domain.models.enums import StatusPedidoEnum


class Pedido(Base):
    __tablename__ = "pedidos"

    __table_args__ = (
        CheckConstraint(
            "percentual_progresso >= 0 AND percentual_progresso <= 100",
            name="pedidos_percentual_progresso_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    codigo_identificador: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )

    titulo: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    descricao: Mapped[str | None] = mapped_column(Text)

    status: Mapped[StatusPedidoEnum] = mapped_column(
        Enum(StatusPedidoEnum, name="enum_status"),
        nullable=False,
        server_default=text("'PLANEAMENTO'::enum_status"),
    )

    percentual_progresso: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        server_default=text("0.00"),
    )

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
    )

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    updated_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True),
    server_default=text("CURRENT_TIMESTAMP"),
    onupdate=func.now(), # type: ignore
)
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, text # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore

from app.core.database import Base
from app.domain.models.enums import StatusPedidoEnum


class HistoricoStatusPedido(Base):
    __tablename__ = "historico_status_pedidos"

    __table_args__ = (
        Index(
            "ix_historico_status_pedidos_pedido_id",
            "pedido_id",
        ),
        Index(
            "ix_historico_status_pedidos_usuario_id",
            "usuario_id",
        ),
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

    status_anterior: Mapped[StatusPedidoEnum] = mapped_column(
        Enum(
            StatusPedidoEnum,
            name="enum_status",
            create_type=False,
        ),
        nullable=False,
    )

    status_novo: Mapped[StatusPedidoEnum] = mapped_column(
        Enum(
            StatusPedidoEnum,
            name="enum_status",
            create_type=False,
        ),
        nullable=False,
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
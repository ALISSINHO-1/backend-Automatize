import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, text # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore

from app.core.database import Base
from app.domain.models.enums import (
    StatusPedidoEnum,
    TipoOcorrenciaEnum,
)


class Ocorrencia(Base):
    __tablename__ = "ocorrencias"

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

    autor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    tipo: Mapped[TipoOcorrenciaEnum] = mapped_column(
        Enum(
            TipoOcorrenciaEnum,
            name="enum_tipo_ocorrencia",
        ),
        nullable=False,
    )

    descricao: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    motivo_regresso: Mapped[str | None] = mapped_column(Text)

    status_anterior: Mapped[StatusPedidoEnum | None] = mapped_column(
        Enum(StatusPedidoEnum, name="enum_status")
    )

    status_novo: Mapped[StatusPedidoEnum | None] = mapped_column(
        Enum(StatusPedidoEnum, name="enum_status")
    )

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
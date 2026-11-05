import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Text, UniqueConstraint, text # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore

from app.core.database import Base
from app.domain.models.enums import (
    StatusPedidoEnum,
    TipoOcorrenciaEnum,
)


class Ocorrencia(Base):
    __tablename__ = "ocorrencias"
    __table_args__ = (
        UniqueConstraint("id", "pedido_id", name="uq_ocorrencias_id_pedido_id"),
        CheckConstraint(
            "(resolvida_em IS NULL) = (resolvida_por_id IS NULL) "
            "AND (resolvida_em IS NULL) = (descricao_resolucao IS NULL)",
            name="ck_ocorrencias_resolucao_completa",
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

    # Resolucao da ocorrencia (SCRUM-98): os tres campos andam juntos
    # (ck_ocorrencias_resolucao_completa); nulos = ocorrencia em aberto.
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    resolvida_por_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
    )

    descricao_resolucao: Mapped[str | None] = mapped_column(Text)

    @property
    def resolvida(self) -> bool:
        return self.resolvida_em is not None

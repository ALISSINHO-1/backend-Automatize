import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ( # type: ignore
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    select,
)
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import Mapped, column_property, mapped_column # type: ignore

from app.core.database import Base
from app.domain.models.enums import StatusPedidoEnum
from app.domain.models.historico_status_pedido import HistoricoStatusPedido


class Pedido(Base):
    __tablename__ = "pedidos"

    __table_args__ = (
        UniqueConstraint("id", "cliente_id", name="uq_pedidos_id_cliente_id"),
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

    data_previsao: Mapped[date | None] = mapped_column(Date)
    data_inicio: Mapped[datetime | None] = column_property(
        select(func.min(HistoricoStatusPedido.created_at))
        .where(
            HistoricoStatusPedido.pedido_id == id,
            HistoricoStatusPedido.status_novo == StatusPedidoEnum.EXECUCAO,
        )
        .correlate_except(HistoricoStatusPedido)
        .scalar_subquery()
    )
    data_conclusao: Mapped[datetime | None] = column_property(
        select(func.max(HistoricoStatusPedido.created_at))
        .where(
            HistoricoStatusPedido.pedido_id == id,
            HistoricoStatusPedido.status_novo == StatusPedidoEnum.CONCLUIDO,
            status == StatusPedidoEnum.CONCLUIDO,
        )
        .correlate_except(HistoricoStatusPedido)
        .scalar_subquery()
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

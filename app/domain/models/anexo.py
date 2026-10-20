import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, text # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore

from app.core.database import Base


class Anexo(Base):
    __tablename__ = "anexos"

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

    ocorrencia_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ocorrencias.id", ondelete="SET NULL"),
    )

    enviado_por_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    nome_arquivo: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    caminho_storage: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    extensao: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    tamanho_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
    )
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, text # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore
from sqlalchemy import func # type: ignore

from app.core.database import Base
from app.domain.models.enums import PerfilEnum


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    senha_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    perfil: Mapped[PerfilEnum] = mapped_column(
        Enum(PerfilEnum, name="enum_perfil"),
        nullable=False,
        server_default=text("'CLIENTE'::enum_perfil"),
    )

    ativo: Mapped[bool | None] = mapped_column(
        Boolean,
        server_default=text("true"),
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
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Integer, text # type: ignore
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

    # Contas anteriores continuam LEGADO para evitar perda de acesso.
    origem_cadastro: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LEGADO",
        server_default=text("'LEGADO'")
    )

    # Todas as sessoes anteriores sao invalidadas ao redefinir a senha.
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    email_verificado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Cadastros publicos sao PENDENTE; contas legadas preservam ATIVO.
    situacao_cadastro: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ATIVO", server_default=text("'ATIVO'")
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
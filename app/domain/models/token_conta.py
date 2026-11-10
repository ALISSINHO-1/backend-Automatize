"""Single-use email confirmation and password reset; store only token digests."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TokenConta(Base):
    __tablename__ = "tokens_conta"
    __table_args__ = (
        CheckConstraint(
            "finalidade IN ('VERIFICAR_EMAIL', 'REDEFINIR_SENHA')",
            name="ck_tokens_conta_finalidade",
        ),
        Index("ix_tokens_conta_usuario_id", "usuario_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    usuario_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    finalidade: Mapped[str] = mapped_column(String(20), nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

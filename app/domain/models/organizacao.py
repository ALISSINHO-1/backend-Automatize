"""Organizacao contratante do SaaS (nao confundir com ADMIN global)."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Organizacao(Base):
    __tablename__ = "organizacoes"
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    criado_por_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

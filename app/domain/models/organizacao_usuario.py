"""Membro de organizacao: GESTOR e local, nao equivale a ADMIN global."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class OrganizacaoUsuario(Base):
    __tablename__ = "organizacao_usuarios"
    __table_args__ = (
        UniqueConstraint("organizacao_id", "usuario_id", name="uq_organizacao_usuario"),
        CheckConstraint("papel IN ('GESTOR', 'COLABORADOR')", name="ck_organizacao_usuarios_papel"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    organizacao_id: Mapped[UUID] = mapped_column(ForeignKey("organizacoes.id"), nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    papel: Mapped[str] = mapped_column(String(16), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

"""Contrato DEV de pessoa ou assinatura SAAS de organizacao."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Contratacao(Base):
    __tablename__ = "contratacoes"
    __table_args__ = (
        CheckConstraint("situacao IN ('PENDENTE', 'ATIVA', 'SUSPENSA')", name="ck_contratacoes_situacao"),
        CheckConstraint(
            "(tipo = 'DEV' AND usuario_cliente_id IS NOT NULL AND organizacao_id IS NULL)"
            " OR (tipo = 'SAAS' AND organizacao_id IS NOT NULL AND usuario_cliente_id IS NULL)",
            name="ck_contratacoes_tipo_titular",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    situacao: Mapped[str] = mapped_column(String(16), nullable=False)
    usuario_cliente_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    organizacao_id: Mapped[UUID | None] = mapped_column(ForeignKey("organizacoes.id"), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

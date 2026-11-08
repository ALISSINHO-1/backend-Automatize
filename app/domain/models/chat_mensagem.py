from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChatMensagem(Base):
    __tablename__ = "chat_mensagens"
    __table_args__ = (
        CheckConstraint("canal IN ('cliente', 'interno')", name="chat_mensagens_canal_check"),
        Index("ix_chat_mensagens_conversa", "pedido_id", "canal", "criado_em", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    pedido_id: Mapped[UUID] = mapped_column(ForeignKey("pedidos.id", ondelete="CASCADE"))
    autor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    canal: Mapped[str] = mapped_column(String(10))
    texto: Mapped[str] = mapped_column(String(2000))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

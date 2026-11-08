from uuid import UUID

from sqlalchemy import LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MovimentoQuadro(Base):
    __tablename__ = "movimentos_quadro"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    conteudo_cifrado: Mapped[bytes] = mapped_column(LargeBinary)

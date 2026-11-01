from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.models.enums import PerfilEnum


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    perfil: PerfilEnum
    ativo: bool | None

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.enums import TipoOcorrenciaEnum


class OcorrenciaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    tipo: TipoOcorrenciaEnum = Field(
        description="REGRESSO_ESTADO é reservado ao fluxo de rejeição."
    )
    descricao: str = Field(
        min_length=5,
        max_length=10000,
        examples=["O relatório não apresenta os totais esperados."],
    )


class OcorrenciaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    descricao: str = Field(min_length=5, max_length=10000)


class OcorrenciaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    pedido_id: UUID
    autor_id: UUID
    tipo: TipoOcorrenciaEnum
    descricao: str
    created_at: datetime | None

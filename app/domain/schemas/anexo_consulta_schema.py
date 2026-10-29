from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AnexoConsultaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    pedido_id: UUID
    ocorrencia_id: UUID | None
    enviado_por_id: UUID
    nome_arquivo: str
    extensao: str
    tamanho_bytes: int
    created_at: datetime | None

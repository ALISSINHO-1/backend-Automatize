from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict # type: ignore


class AnexoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pedido_id: UUID
    ocorrencia_id: UUID | None
    enviado_por_id: UUID

    nome_arquivo: str
    caminho_storage: str
    extensao: str
    tamanho_bytes: int

    created_at: datetime
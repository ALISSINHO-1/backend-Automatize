"""Public attachment metadata and short-lived private access (HML contract)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AnexoPublico(BaseModel):
    id: UUID
    pedido_id: UUID
    ocorrencia_id: UUID | None
    enviado_por_id: UUID
    nome_arquivo: str
    extensao: str
    tamanho_bytes: int
    created_at: datetime | None
    referencia_acesso: str


class AnexoAcesso(BaseModel):
    url: str
    expira_em: datetime
    validade_segundos: int

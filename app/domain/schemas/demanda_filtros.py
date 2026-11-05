from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.models.enums import StatusPedidoEnum


class DemandaFiltros(BaseModel):
    busca: str | None = Field(default=None, min_length=1, max_length=255)
    status: StatusPedidoEnum | None = None
    cliente_id: UUID | None = None
    responsavel_id: UUID | None = None
    criado_de: datetime | None = None
    criado_ate: datetime | None = None


class DemandaIndicadores(BaseModel):
    total: int
    por_status: dict[str, int]

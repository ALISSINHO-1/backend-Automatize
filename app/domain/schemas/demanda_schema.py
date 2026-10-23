from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models.enums import StatusPedidoEnum


class DemandaResponse(BaseModel):
    """Public read representation of a demand (Pedido)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="UUID da demanda, serializado como string.")
    codigo_identificador: str = Field(description="Código identificador da demanda.")
    titulo: str = Field(description="Título da demanda.")
    descricao: str | None = Field(description="Descrição, ou null se ausente.")
    status: StatusPedidoEnum = Field(description="Status persistido da demanda.")
    percentual_progresso: str | None = Field(
        description=(
            "Percentual decimal serializado como string, por exemplo \"37.50\", "
            "ou null se ausente."
        )
    )
    cliente_id: UUID = Field(description="UUID do cliente, serializado como string.")
    responsavel_id: UUID | None = Field(
        description="UUID do responsável ou null se não houver responsável."
    )
    created_at: datetime | None = Field(description="Data de criação ou null.")
    updated_at: datetime | None = Field(description="Data da última atualização ou null.")

    @field_validator("percentual_progresso", mode="before")
    @classmethod
    def decimal_as_string(cls, value: object) -> str | None:
        if value is None:
            return None
        return str(value)

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field # type: ignore

from app.domain.models.enums import StatusPedidoEnum


class PedidoBase(BaseModel):
    titulo: str = Field(
        min_length=3,
        max_length=255,
    )

    descricao: str | None = None


class PedidoCreate(PedidoBase):
    codigo_identificador: str = Field(
        min_length=1,
        max_length=50,
    )

    cliente_id: UUID
    responsavel_id: UUID | None = None


class PedidoUpdate(BaseModel):
    titulo: str | None = Field(
        default=None,
        min_length=3,
        max_length=255,
    )

    descricao: str | None = None

    status: StatusPedidoEnum | None = None

    percentual_progresso: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    responsavel_id: UUID | None = None


class PedidoResponse(PedidoBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    codigo_identificador: str
    status: StatusPedidoEnum
    percentual_progresso: Decimal

    cliente_id: UUID
    responsavel_id: UUID | None

    created_at: datetime
    updated_at: datetime
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.enums import StatusPedidoEnum


class _Requisicao(BaseModel):
    # Campos desconhecidos sao recusados: evita que um cliente_id/usuario_id
    # enviado no corpo pareca ter efeito.
    model_config = ConfigDict(extra="forbid")


class DemandaCreateRequest(_Requisicao):
    titulo: str = Field(max_length=255, examples=["Ajustar relatório de vendas"])
    descricao: str = Field(
        examples=["Incluir total mensal e filtros por período no relatório."]
    )
    cliente_id: UUID | None = Field(
        default=None,
        description="Usado apenas por ADMIN. Para CLIENTE, a demanda e sempre do usuario do token.",
    )


class DemandaUpdateRequest(_Requisicao):
    titulo: str = Field(max_length=255, examples=["Ajustar relatório de vendas"])
    descricao: str = Field(
        examples=["Incluir total mensal e filtros por período no relatório."]
    )


class StatusUpdateRequest(_Requisicao):
    status: StatusPedidoEnum


class RejeicaoRequest(_Requisicao):
    motivo: str = Field(
        description="Motivo da rejeição (mínimo 10 caracteres).",
        examples=["Os totais do relatório ainda divergem do combinado."],
    )


class ResponsavelRequest(_Requisicao):
    responsavel_id: UUID


class EtapaCreateRequest(_Requisicao):
    descricao: str = Field(max_length=255)


class EtapaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pedido_id: UUID
    descricao: str = Field(
        examples=["Incluir total mensal e filtros por período no relatório."]
    )
    concluida: bool
    concluida_em: datetime | None
    concluida_por_id: UUID | None
    criado_por_id: UUID
    created_at: datetime


class AuditoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    usuario_id: UUID | None
    acao: str
    detalhes: dict[str, Any] | None
    created_at: datetime | None

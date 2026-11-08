from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.models.enums import StatusPedidoEnum, TipoOcorrenciaEnum


class _Requisicao(BaseModel):
    # Campos desconhecidos sao recusados: evita que um cliente_id/usuario_id
    # enviado no corpo pareca ter efeito.
    model_config = ConfigDict(extra="forbid")


class DemandaDisponivelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    codigo_identificador: str
    titulo: str


class DemandaCreateRequest(_Requisicao):
    titulo: str = Field(max_length=255)
    descricao: str
    cliente_id: UUID | None = Field(
        default=None,
        description="Usado apenas por ADMIN. Para CLIENTE, a demanda e sempre do usuario do token.",
    )


class DemandaUpdateRequest(_Requisicao):
    titulo: str = Field(max_length=255)
    descricao: str


class StatusUpdateRequest(_Requisicao):
    status: StatusPedidoEnum


class RejeicaoRequest(_Requisicao):
    motivo: str = Field(description="Motivo da rejeicao (minimo 10 caracteres).")


class ResponsavelRequest(_Requisicao):
    responsavel_id: UUID
    motivo: str | None = Field(
        default=None,
        max_length=500,
        description="Obrigatorio (minimo 10 caracteres) ao trocar um tecnico ja atribuido.",
    )


class EtapaCreateRequest(_Requisicao):
    descricao: str = Field(max_length=255)
    ordem: int | None = Field(default=None, ge=1, strict=True, description="Posicao; omitida adiciona ao final.")


class EtapaUpdateRequest(_Requisicao):
    descricao: str | None = Field(default=None, min_length=3, max_length=255)
    ordem: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def exigir_alteracao(self):
        if self.descricao is None and self.ordem is None:
            raise ValueError("Informe descricao ou ordem.")
        return self


class EtapaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pedido_id: UUID
    descricao: str
    ordem: int
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


class OcorrenciaCreateRequest(_Requisicao):
    tipo: TipoOcorrenciaEnum = Field(description="ERRO ou SOLICITACAO_CORRECAO.")
    descricao: str = Field(max_length=2000, description="Minimo 10 caracteres.")


class ResolucaoOcorrenciaRequest(_Requisicao):
    descricao_resolucao: str = Field(max_length=2000, description="O que foi corrigido (minimo 10 caracteres).")


class OcorrenciaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pedido_id: UUID
    autor_id: UUID
    tipo: TipoOcorrenciaEnum
    descricao: str
    status_anterior: StatusPedidoEnum | None
    status_novo: StatusPedidoEnum | None
    created_at: datetime | None
    resolvida: bool
    resolvida_em: datetime | None
    resolvida_por_id: UUID | None
    descricao_resolucao: str | None

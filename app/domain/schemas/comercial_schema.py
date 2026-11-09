"""Contratos comerciais controlados somente pela equipe ADMIN."""
from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class NovaOrganizacao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=3, max_length=255)

class NovoMembro(BaseModel):
    model_config = ConfigDict(extra="forbid")
    usuario_id: UUID
    papel: Literal["GESTOR", "COLABORADOR"]

class ContratoDEV(BaseModel):
    model_config = ConfigDict(extra="forbid")
    usuario_id: UUID

class ContratoSAAS(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organizacao_id: UUID

class OrganizacaoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    ativa: bool

class VinculoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organizacao_id: UUID
    usuario_id: UUID
    papel: str
    ativo: bool

class ContratoResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tipo: str
    situacao: str
    usuario_cliente_id: UUID | None
    organizacao_id: UUID | None

class ContaPendenteResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    email: str
    created_at: datetime | None

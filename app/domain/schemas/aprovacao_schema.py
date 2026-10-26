from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AprovacaoSolicitacaoSchema(BaseModel):
    """Corpo do aceite formal. Nao ha cliente_id: o cliente e o usuario do token."""

    model_config = ConfigDict(extra="forbid")

    versao_entregavel: str = Field(max_length=50, description="Versao do entregavel aprovada.")
    declaracao_aceite: str = Field(description="Declaracao de aceite do cliente (minimo 10 caracteres).")


class AprovacaoRespostaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pedido_id: UUID
    cliente_id: UUID
    data_hora_aceite: datetime
    versao_entregavel: str
    declaracao_aceite: str
    hash_validacao: str

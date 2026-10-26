from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.domain.enums import StatusPedidoEnum

# Nomes e tipos seguem a tabela "pedidos" (ids UUID, created_at/updated_at),
# senao a leitura do model via from_attributes quebra em tempo de execucao.
class PedidoBaseSchema(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=255, description="Titulo do pedido ou servico")
    descricao: str = Field(..., min_length=5, description="Descricao detalhada da solicitacao")
    cliente_id: UUID = Field(..., description="Identificador do cliente solicitante")

class PedidoCriarSchema(PedidoBaseSchema):
    pass

class PedidoAtualizarStatusSchema(BaseModel):
    novo_status: StatusPedidoEnum
    motivo_regresso: Optional[str] = Field(None, description="Obrigatorio caso retorne para Execucao")

class PedidoRespostaSchema(PedidoBaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    codigo_identificador: str
    # Pedidos gravados antes podem ter descricao vazia (coluna aceita NULL).
    descricao: Optional[str] = None
    status: StatusPedidoEnum
    percentual_progresso: Optional[Decimal] = None
    responsavel_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

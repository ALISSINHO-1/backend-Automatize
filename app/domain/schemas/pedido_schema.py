from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.domain.enums import StatusPedidoEnum

class PedidoBaseSchema(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=150, description="Titulo do pedido ou servico")
    descricao: str = Field(..., min_length=5, description="Descricao detalhada da solicitacao")
    cliente_id: str = Field(..., description="Identificador do cliente solicitante")

class PedidoCriarSchema(PedidoBaseSchema):
    pass

class PedidoAtualizarStatusSchema(BaseModel):
    novo_status: StatusPedidoEnum
    motivo_regresso: Optional[str] = Field(None, description="Obrigatorio caso retorne para Execucao")

class PedidoRespostaSchema(PedidoBaseSchema):
    id: int
    status: StatusPedidoEnum
    percentual_progresso: float
    data_criacao: datetime
    data_conclusao: Optional[datetime] = None

    class Config:
        from_attributes = True

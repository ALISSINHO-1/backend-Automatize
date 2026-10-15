from datetime import datetime
from pydantic import BaseModel, Field

class AprovacaoSolicitacaoSchema(BaseModel):
    pedido_id: int = Field(..., description="ID da ordem de serviço a aprovar")
    cliente_id: str = Field(..., description="Identificador do cliente homologador")

class AprovacaoRespostaSchema(BaseModel):
    pedido_id: int
    status_final: str
    aprovado_por: str
    data_aceite: datetime
    percentual_progresso: float
    mensagem: str

from datetime import datetime
from typing import Optional, List, Dict, Any
from app.domain.enums import StatusDemandaEnum

class Demanda:

    def __init__(
        self,
        id: int,
        titulo: str,
        descricao: str,
        cliente_id: str,
        status: StatusDemandaEnum = StatusDemandaEnum.PLANEAMENTO,
        percentual_progresso: float = 15.0,
        criado_em: Optional[datetime] = None
    ):
        self.id = id
        self.titulo = titulo
        self.descricao = descricao
        self.cliente_id = cliente_id
        self.status = status
        self.percentual_progresso = percentual_progresso
        self.criado_em = criado_em or datetime.now()
        self.aprovado_por: Optional[str] = None
        self.data_aprovacao: Optional[datetime] = None
        self.historico_alteracoes: List[Dict[str, Any]] = []

    def adicionar_historico(self, acao: str, status_anterior: str, novo_status: str, motivo: Optional[str] = None):
        self.historico_alteracoes.append({
            "data_hora": datetime.now(),
            "acao": acao,
            "status_anterior": status_anterior,
            "novo_status": novo_status,
            "motivo": motivo
        })
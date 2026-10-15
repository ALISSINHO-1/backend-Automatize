from typing import Optional
from app.domain.enums import StatusPedidoEnum

class PedidoService:
    """Núcleo de regras do ciclo de vida e progresso (POO)."""

    @classmethod
    def calcular_progresso(cls, status: StatusPedidoEnum) -> float:
        # TODO: implementar calculo percentual automatico
        pass

    @classmethod
    def validar_e_transitar(
        cls,
        status_atual: StatusPedidoEnum,
        novo_status: StatusPedidoEnum,
        motivo_regresso: Optional[str] = None
    ) -> float:
        # TODO: implementar maquina de estados estrita
        pass

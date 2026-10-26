"""Regras puras do ciclo de vida da demanda (sem banco, sem sessao).

O DemandService aplica estas regras sobre o Pedido persistido; mante-las
aqui permite testa-las isoladamente e reutiliza-las no PedidoService.
"""
from decimal import Decimal

from app.core.exceptions import (
    AprovacaoNaoAutorizadaException,
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
)
from app.domain.models.enums import StatusPedidoEnum


PROGRESSO_POR_ESTADO: dict[StatusPedidoEnum, Decimal] = {
    StatusPedidoEnum.PLANEAMENTO: Decimal("15.00"),
    StatusPedidoEnum.EXECUCAO: Decimal("50.00"),
    StatusPedidoEnum.HOMOLOGACAO: Decimal("85.00"),
    StatusPedidoEnum.CONCLUIDO: Decimal("100.00"),
}

TRANSICOES_VALIDAS: dict[StatusPedidoEnum, tuple[StatusPedidoEnum, ...]] = {
    StatusPedidoEnum.PLANEAMENTO: (StatusPedidoEnum.EXECUCAO,),
    StatusPedidoEnum.EXECUCAO: (StatusPedidoEnum.HOMOLOGACAO,),
    StatusPedidoEnum.HOMOLOGACAO: (StatusPedidoEnum.CONCLUIDO, StatusPedidoEnum.EXECUCAO),
    StatusPedidoEnum.CONCLUIDO: (),
}

TAMANHO_MINIMO_MOTIVO_REGRESSO = 10


def calcular_progresso(
    status: StatusPedidoEnum,
    total_etapas: int = 0,
    etapas_concluidas: int = 0,
) -> Decimal:
    """Em EXECUCAO com etapas cadastradas, o progresso avanca de PLANEAMENTO ate
    HOMOLOGACAO proporcionalmente as etapas concluidas. Nos demais casos vale o
    percentual do estado."""
    if status != StatusPedidoEnum.EXECUCAO or total_etapas <= 0:
        return PROGRESSO_POR_ESTADO[status]

    inicio = PROGRESSO_POR_ESTADO[StatusPedidoEnum.PLANEAMENTO]
    fim = PROGRESSO_POR_ESTADO[StatusPedidoEnum.HOMOLOGACAO]
    progresso = inicio + (fim - inicio) * etapas_concluidas / total_etapas
    return progresso.quantize(Decimal("0.01"))


def validar_motivo_regresso(motivo: str | None) -> str:
    motivo = (motivo or "").strip()
    if len(motivo) < TAMANHO_MINIMO_MOTIVO_REGRESSO:
        raise TransicaoEstadoInvalidaException(
            "O regresso de HOMOLOGACAO para EXECUCAO exige a descricao do motivo "
            f"com no minimo {TAMANHO_MINIMO_MOTIVO_REGRESSO} caracteres."
        )
    return motivo


def validar_transicao(
    status_atual: StatusPedidoEnum,
    novo_status: StatusPedidoEnum,
    *,
    etapas_pendentes: tuple[str, ...] = (),
    motivo_regresso: str | None = None,
) -> None:
    """Valida a transicao pela maquina de estados.

    A conclusao nunca passa por aqui: ela so acontece com o aceite formal do
    cliente (AprovacaoService)."""
    if status_atual == StatusPedidoEnum.CONCLUIDO:
        raise TransicaoEstadoInvalidaException("Demandas no estado CONCLUIDO sao imutaveis.")

    if novo_status not in TRANSICOES_VALIDAS[status_atual]:
        raise TransicaoEstadoInvalidaException(
            f"Transicao ilegal: nao e permitido transitar de {status_atual.value} "
            f"para {novo_status.value}."
        )

    if novo_status == StatusPedidoEnum.CONCLUIDO:
        raise AprovacaoNaoAutorizadaException(
            "A conclusao exige aceite formal do cliente. Utilize a aprovacao da homologacao."
        )

    if status_atual == StatusPedidoEnum.HOMOLOGACAO:
        validar_motivo_regresso(motivo_regresso)

    if novo_status == StatusPedidoEnum.HOMOLOGACAO and etapas_pendentes:
        raise TransicaoEstadoInvalidaException(
            "Nao e permitido enviar para HOMOLOGACAO com etapas operacionais pendentes: "
            f"{', '.join(etapas_pendentes)}."
        )


def validar_texto(valor: str | None, campo: str, minimo: int, maximo: int | None = None) -> str:
    valor = (valor or "").strip()
    if len(valor) < minimo:
        raise RegraNegocioException(f"O campo {campo} deve ter no minimo {minimo} caracteres.")
    if maximo is not None and len(valor) > maximo:
        raise RegraNegocioException(f"O campo {campo} deve ter no maximo {maximo} caracteres.")
    return valor

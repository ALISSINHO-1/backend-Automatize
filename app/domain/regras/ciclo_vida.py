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
from app.domain.models.enums import StatusPedidoEnum, TipoOcorrenciaEnum


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
    total_etapas: int = 0,
    etapas_pendentes: tuple[str, ...] = (),
    motivo_regresso: str | None = None,
    ocorrencias_abertas: int = 0,
) -> None:
    """Valida a transicao pela maquina de estados.

    A conclusao nunca passa por aqui: ela so acontece com o aceite formal do
    cliente (AprovacaoService). HOMOLOGACAO exige ao menos uma etapa operacional
    cadastrada e todas concluidas (SCRUM-71 / PR #12): sem etapas nao ha registro
    do que foi executado para o cliente homologar."""
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

    if novo_status == StatusPedidoEnum.HOMOLOGACAO and total_etapas <= 0:
        raise TransicaoEstadoInvalidaException(
            "Nao e permitido enviar para HOMOLOGACAO sem etapas operacionais: "
            "cadastre e conclua ao menos uma etapa."
        )

    if novo_status == StatusPedidoEnum.HOMOLOGACAO and etapas_pendentes:
        raise TransicaoEstadoInvalidaException(
            "Nao e permitido enviar para HOMOLOGACAO com etapas operacionais pendentes: "
            f"{', '.join(etapas_pendentes)}."
        )

    # SCRUM-98: erro ou pedido de correcao em aberto significa entrega incompleta;
    # o cliente so homologa depois que a correcao foi registrada como resolvida.
    if novo_status == StatusPedidoEnum.HOMOLOGACAO and ocorrencias_abertas > 0:
        raise TransicaoEstadoInvalidaException(
            "Nao e permitido enviar para HOMOLOGACAO com ocorrencias em aberto: "
            f"resolva as {ocorrencias_abertas} ocorrencia(s) pendente(s)."
        )


def validar_tipo_ocorrencia_manual(tipo: TipoOcorrenciaEnum) -> None:
    """REGRESSO_ESTADO nasce apenas da rejeicao da homologacao; registra-lo a mao
    criaria um regresso sem mudanca de estado correspondente."""
    if tipo == TipoOcorrenciaEnum.REGRESSO_ESTADO:
        raise RegraNegocioException(
            "Ocorrencias de regresso sao geradas pela rejeicao da homologacao. "
            "Registre ERRO ou SOLICITACAO_CORRECAO."
        )


def validar_estado_para_ocorrencia(status: StatusPedidoEnum) -> None:
    """Ocorrencias novas so durante o trabalho. Em HOMOLOGACAO o caminho e a
    rejeicao (que ja gera o regresso); assim nunca ha ocorrencia aberta na
    homologacao e o aceite nao conclui uma demanda com pendencia."""
    if status not in (StatusPedidoEnum.PLANEAMENTO, StatusPedidoEnum.EXECUCAO):
        raise TransicaoEstadoInvalidaException(
            f"Ocorrencias so podem ser registradas em PLANEAMENTO ou EXECUCAO. Estado atual: {status.value}. "
            "Em HOMOLOGACAO, solicite a correcao rejeitando a homologacao."
        )


def validar_texto(valor: str | None, campo: str, minimo: int, maximo: int | None = None) -> str:
    valor = (valor or "").strip()
    if len(valor) < minimo:
        raise RegraNegocioException(f"O campo {campo} deve ter no minimo {minimo} caracteres.")
    if maximo is not None and len(valor) > maximo:
        raise RegraNegocioException(f"O campo {campo} deve ter no maximo {maximo} caracteres.")
    return valor

from decimal import Decimal

import pytest

from app.core.exceptions import (
    AprovacaoNaoAutorizadaException,
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
)
from app.domain.models.enums import StatusPedidoEnum as Status
from app.domain.regras import ciclo_vida
from app.services.pedido_service import PedidoService


@pytest.mark.parametrize("status, esperado", [
    (Status.PLANEAMENTO, "15.00"),
    (Status.EXECUCAO, "50.00"),
    (Status.HOMOLOGACAO, "85.00"),
    (Status.CONCLUIDO, "100.00"),
])
def test_progresso_padrao_por_estado(status, esperado):
    assert ciclo_vida.calcular_progresso(status) == Decimal(esperado)


@pytest.mark.parametrize("concluidas, esperado", [(0, "15.00"), (1, "32.50"), (2, "50.00"), (4, "85.00")])
def test_progresso_em_execucao_acompanha_etapas(concluidas, esperado):
    assert ciclo_vida.calcular_progresso(Status.EXECUCAO, 4, concluidas) == Decimal(esperado)


def test_etapas_so_influenciam_progresso_em_execucao():
    assert ciclo_vida.calcular_progresso(Status.PLANEAMENTO, 4, 4) == Decimal("15.00")
    assert ciclo_vida.calcular_progresso(Status.HOMOLOGACAO, 4, 0) == Decimal("85.00")


@pytest.mark.parametrize("atual, novo", [
    (Status.PLANEAMENTO, Status.EXECUCAO),
    (Status.EXECUCAO, Status.HOMOLOGACAO),
])
def test_transicoes_de_avanco_validas(atual, novo):
    ciclo_vida.validar_transicao(atual, novo)


@pytest.mark.parametrize("atual, novo", [
    (Status.PLANEAMENTO, Status.HOMOLOGACAO),
    (Status.PLANEAMENTO, Status.CONCLUIDO),
    (Status.EXECUCAO, Status.PLANEAMENTO),
    (Status.EXECUCAO, Status.CONCLUIDO),
    (Status.HOMOLOGACAO, Status.PLANEAMENTO),
])
def test_transicoes_ilegais(atual, novo):
    with pytest.raises(TransicaoEstadoInvalidaException, match="Transicao ilegal"):
        ciclo_vida.validar_transicao(atual, novo)


def test_concluido_e_imutavel():
    with pytest.raises(TransicaoEstadoInvalidaException, match="imutaveis"):
        ciclo_vida.validar_transicao(Status.CONCLUIDO, Status.EXECUCAO)


def test_conclusao_exige_aceite_formal():
    with pytest.raises(AprovacaoNaoAutorizadaException, match="aceite formal"):
        ciclo_vida.validar_transicao(Status.HOMOLOGACAO, Status.CONCLUIDO)


@pytest.mark.parametrize("motivo", [None, "", "curto", "         a"])
def test_regresso_exige_motivo_com_10_caracteres(motivo):
    with pytest.raises(TransicaoEstadoInvalidaException, match="10 caracteres"):
        ciclo_vida.validar_transicao(Status.HOMOLOGACAO, Status.EXECUCAO, motivo_regresso=motivo)


def test_regresso_com_motivo_valido():
    ciclo_vida.validar_transicao(Status.HOMOLOGACAO, Status.EXECUCAO, motivo_regresso="Layout divergente")


def test_homologacao_bloqueada_por_etapas_pendentes():
    with pytest.raises(TransicaoEstadoInvalidaException, match="Testar temperatura"):
        ciclo_vida.validar_transicao(
            Status.EXECUCAO, Status.HOMOLOGACAO, etapas_pendentes=("Testar temperatura",)
        )


def test_validar_texto_normaliza_e_limita():
    assert ciclo_vida.validar_texto("  Ajuste  ", "titulo", 3, 10) == "Ajuste"
    with pytest.raises(RegraNegocioException, match="minimo 3"):
        ciclo_vida.validar_texto(" A ", "titulo", 3)
    with pytest.raises(RegraNegocioException, match="maximo 5"):
        ciclo_vida.validar_texto("abcdef", "titulo", 1, 5)


def test_pedido_service_usa_as_mesmas_regras():
    assert PedidoService.calcular_progresso(Status.EXECUCAO) == 50.0
    assert PedidoService.validar_e_transitar(Status.PLANEAMENTO, Status.EXECUCAO) == 50.0
    with pytest.raises(AprovacaoNaoAutorizadaException):
        PedidoService.validar_e_transitar(Status.HOMOLOGACAO, Status.CONCLUIDO)

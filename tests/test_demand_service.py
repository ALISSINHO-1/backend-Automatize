import pytest
from app.domain.enums import StatusDemandaEnum
from app.core.exceptions import (
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
    AprovacaoNaoAutorizadaException
)
from app.services.demand_service import DemandService

@pytest.fixture(autouse=True)
def reset_service():
    DemandService._demandas.clear()
    DemandService._contador_id = 1

def test_criar_demanda_valida():
    demanda = DemandService.create("Formatacao", "Limpeza e formatacao de PC", "cli_1")
    assert demanda.id == 1
    assert demanda.status == StatusDemandaEnum.PLANEAMENTO
    assert demanda.percentual_progresso == 15.0
    assert len(demanda.historico_alteracoes) == 1

def test_criar_demanda_invalida_falha():
    with pytest.raises(RegraNegocioException):
        DemandService.create("A", "Desc", "cli_1")

def test_transicao_valida_fluxo():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    d1 = DemandService.change_status(demanda.id, StatusDemandaEnum.EXECUCAO)
    assert d1.status == StatusDemandaEnum.EXECUCAO
    assert d1.percentual_progresso == 50.0

    d2 = DemandService.change_status(demanda.id, StatusDemandaEnum.HOMOLOGACAO)
    assert d2.status == StatusDemandaEnum.HOMOLOGACAO
    assert d2.percentual_progresso == 85.0

def test_bloqueio_salto_de_estado():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    with pytest.raises(TransicaoEstadoInvalidaException):
        DemandService.change_status(demanda.id, StatusDemandaEnum.CONCLUIDO)

def test_aprovacao_homologacao_com_sucesso():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    DemandService.change_status(demanda.id, StatusDemandaEnum.EXECUCAO)
    DemandService.change_status(demanda.id, StatusDemandaEnum.HOMOLOGACAO)

    demanda_concluida = DemandService.aprovar_homologacao(demanda.id, "cliente_valente")
    assert demanda_concluida.status == StatusDemandaEnum.CONCLUIDO
    assert demanda_concluida.percentual_progresso == 100.0
    assert demanda_concluida.aprovado_por == "cliente_valente"
    assert demanda_concluida.data_aprovacao is not None

def test_bloqueio_aprovacao_fora_de_homologacao():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    with pytest.raises(AprovacaoNaoAutorizadaException):
        DemandService.aprovar_homologacao(demanda.id, "cliente_valente")

def test_rejeicao_homologacao_com_retorno_para_execucao():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    DemandService.change_status(demanda.id, StatusDemandaEnum.EXECUCAO)
    DemandService.change_status(demanda.id, StatusDemandaEnum.HOMOLOGACAO)

    demanda_retornada = DemandService.rejeitar_homologacao(
        demanda.id,
        motivo_rejeicao="Corrigir tela de login quebrada no mobile."
    )
    assert demanda_retornada.status == StatusDemandaEnum.EXECUCAO
    assert demanda_retornada.percentual_progresso == 50.0

def test_rejeicao_homologacao_sem_motivo_falha():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    DemandService.change_status(demanda.id, StatusDemandaEnum.EXECUCAO)
    DemandService.change_status(demanda.id, StatusDemandaEnum.HOMOLOGACAO)

    with pytest.raises(TransicaoEstadoInvalidaException):
        DemandService.rejeitar_homologacao(demanda.id, motivo_rejeicao="Curto")
from dataclasses import FrozenInstanceError, replace

import pytest
from app.domain.enums import StatusDemandaEnum
from app.core.exceptions import (
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
    AprovacaoNaoAutorizadaException,
    RegistroImutavelException
)
from app.domain.models.demanda import RegistroAceite
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

def _demanda_em_homologacao():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    DemandService.change_status(demanda.id, StatusDemandaEnum.EXECUCAO)
    DemandService.change_status(demanda.id, StatusDemandaEnum.HOMOLOGACAO)
    return demanda

def test_conclusao_sem_aceite_formal_bloqueada():
    demanda = _demanda_em_homologacao()
    with pytest.raises(AprovacaoNaoAutorizadaException):
        DemandService.change_status(demanda.id, StatusDemandaEnum.CONCLUIDO)
    assert demanda.status == StatusDemandaEnum.HOMOLOGACAO
    assert demanda.aceite is None

def test_aceite_registra_cliente_data_hora_e_hash():
    demanda = _demanda_em_homologacao()
    DemandService.aprovar_homologacao(demanda.id, "cliente_valente")

    aceite = demanda.aceite
    assert aceite.cliente_id == "cliente_valente"
    assert aceite.data_hora.tzinfo is not None
    assert aceite.is_integro()

def test_aceite_concluido_nao_pode_ser_alterado():
    demanda = _demanda_em_homologacao()
    DemandService.aprovar_homologacao(demanda.id, "cliente_valente")

    with pytest.raises(FrozenInstanceError):
        demanda.aceite.cliente_id = "outro_cliente"
    with pytest.raises(AttributeError):
        demanda.aprovado_por = "outro_cliente"
    with pytest.raises(AttributeError):
        demanda.data_aprovacao = None
    with pytest.raises(RegistroImutavelException):
        demanda.registrar_aceite(RegistroAceite.criar(demanda.id, "outro_cliente"))
    assert demanda.aprovado_por == "cliente_valente"

def test_aceite_nao_pode_ser_repetido_nem_rejeitado_apos_conclusao():
    demanda = _demanda_em_homologacao()
    DemandService.aprovar_homologacao(demanda.id, "cliente_valente")

    with pytest.raises(AprovacaoNaoAutorizadaException):
        DemandService.aprovar_homologacao(demanda.id, "outro_cliente")
    with pytest.raises(TransicaoEstadoInvalidaException):
        DemandService.rejeitar_homologacao(demanda.id, "Motivo longo o suficiente.")
    assert demanda.aprovado_por == "cliente_valente"
    assert demanda.status == StatusDemandaEnum.CONCLUIDO

def test_historico_nao_pode_ser_editado_externamente():
    demanda = _demanda_em_homologacao()
    DemandService.aprovar_homologacao(demanda.id, "cliente_valente")

    historico = demanda.historico_alteracoes
    with pytest.raises(AttributeError):
        historico.clear()
    with pytest.raises(TypeError):
        historico[-1]["motivo"] = "adulterado"
    assert historico[-1]["acao"] == "ACEITE_FORMAL_HOMOLOGACAO"

def test_hash_detecta_adulteracao_do_aceite():
    demanda = _demanda_em_homologacao()
    DemandService.aprovar_homologacao(demanda.id, "cliente_valente")

    adulterado = replace(demanda.aceite, cliente_id="outro_cliente")
    assert not adulterado.is_integro()

def test_exclusao_de_demanda_concluida_bloqueada():
    demanda = _demanda_em_homologacao()
    DemandService.aprovar_homologacao(demanda.id, "cliente_valente")

    with pytest.raises(RegistroImutavelException):
        DemandService.delete(demanda.id)
    assert DemandService.get_by_id(demanda.id) is demanda

def test_exclusao_de_demanda_nao_concluida():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    DemandService.delete(demanda.id)
    assert DemandService.get_by_id(demanda.id) is None

import pytest
from app.domain.enums import StatusDemandaEnum
from app.core.exceptions import (
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
    RegistroImutavelException
)
from app.services.demand_service import DemandService

@pytest.fixture(autouse=True)
def reset_service():
    DemandService._demandas.clear()
    DemandService._contador_id = 1

def _demanda_em_execucao():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    DemandService.change_status(demanda.id, StatusDemandaEnum.EXECUCAO, autor_id="tec_1")
    return demanda

def _demanda_concluida():
    demanda = _demanda_em_execucao()
    DemandService.change_status(demanda.id, StatusDemandaEnum.HOMOLOGACAO)
    DemandService.aprovar_homologacao(demanda.id, "cli_1")
    return demanda


# SCRUM-71: bloqueio de homologacao com etapas pendentes

def test_homologacao_bloqueada_com_etapa_pendente():
    demanda = _demanda_em_execucao()
    DemandService.adicionar_etapa(demanda.id, "Trocar pasta termica")
    DemandService.adicionar_etapa(demanda.id, "Testar temperatura")
    DemandService.concluir_etapa(demanda.id, 1)

    with pytest.raises(TransicaoEstadoInvalidaException, match="Testar temperatura"):
        DemandService.change_status(demanda.id, StatusDemandaEnum.HOMOLOGACAO)
    assert demanda.status == StatusDemandaEnum.EXECUCAO

def test_homologacao_liberada_com_todas_etapas_concluidas():
    demanda = _demanda_em_execucao()
    DemandService.adicionar_etapa(demanda.id, "Trocar pasta termica")
    DemandService.concluir_etapa(demanda.id, 1)

    DemandService.change_status(demanda.id, StatusDemandaEnum.HOMOLOGACAO)
    assert demanda.status == StatusDemandaEnum.HOMOLOGACAO

def test_progresso_em_execucao_acompanha_etapas_concluidas():
    demanda = _demanda_em_execucao()
    for descricao in ("Etapa A", "Etapa B", "Etapa C", "Etapa D"):
        DemandService.adicionar_etapa(demanda.id, descricao)
    assert demanda.percentual_progresso == 15.0

    DemandService.concluir_etapa(demanda.id, 1)
    DemandService.concluir_etapa(demanda.id, 2)
    assert demanda.percentual_progresso == 50.0

    DemandService.concluir_etapa(demanda.id, 3)
    DemandService.concluir_etapa(demanda.id, 4)
    assert demanda.percentual_progresso == 85.0

def test_etapa_so_pode_ser_concluida_em_execucao():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    DemandService.adicionar_etapa(demanda.id, "Etapa planejada")

    with pytest.raises(TransicaoEstadoInvalidaException):
        DemandService.concluir_etapa(demanda.id, 1)

def test_etapa_nao_pode_ser_concluida_duas_vezes():
    demanda = _demanda_em_execucao()
    DemandService.adicionar_etapa(demanda.id, "Etapa A")
    DemandService.concluir_etapa(demanda.id, 1)

    with pytest.raises(RegraNegocioException):
        DemandService.concluir_etapa(demanda.id, 1)

def test_etapa_nao_pode_ser_adicionada_em_homologacao():
    demanda = _demanda_em_execucao()
    DemandService.change_status(demanda.id, StatusDemandaEnum.HOMOLOGACAO)

    with pytest.raises(TransicaoEstadoInvalidaException):
        DemandService.adicionar_etapa(demanda.id, "Etapa tardia")


# SCRUM-75: auditoria de atribuicao e envio de evidencias

def test_transicao_registra_autor_no_historico():
    demanda = _demanda_em_execucao()
    entrada = demanda.historico_alteracoes[-1]
    assert entrada["acao"] == "ALTERACAO_ESTADO"
    assert entrada["autor_id"] == "tec_1"
    assert entrada["data_hora"].tzinfo is not None

def test_atribuicao_de_responsavel_e_auditada():
    demanda = _demanda_em_execucao()
    DemandService.atribuir_responsavel(demanda.id, "tec_1", autor_id="admin")
    DemandService.atribuir_responsavel(demanda.id, "tec_2", autor_id="admin")

    entrada = demanda.historico_alteracoes[-1]
    assert demanda.responsavel_id == "tec_2"
    assert entrada["acao"] == "ATRIBUICAO_RESPONSAVEL"
    assert entrada["autor_id"] == "admin"
    assert entrada["detalhes"]["responsavel_anterior"] == "tec_1"
    assert entrada["detalhes"]["responsavel_novo"] == "tec_2"

def test_envio_de_evidencia_e_auditado():
    demanda = _demanda_em_execucao()
    evidencia = DemandService.registrar_evidencia(demanda.id, "tela_erro.PNG", 2048, autor_id="cli_1")

    assert demanda.evidencias == (evidencia,)
    assert evidencia.extensao == "png"
    entrada = demanda.historico_alteracoes[-1]
    assert entrada["acao"] == "ENVIO_EVIDENCIA"
    assert entrada["autor_id"] == "cli_1"
    assert entrada["detalhes"]["nome_arquivo"] == "tela_erro.PNG"

@pytest.mark.parametrize("nome, tamanho", [
    ("script.exe", 1024),
    ("sem_extensao", 1024),
    ("foto.png", 0),
    ("foto.png", 10 * 1024 * 1024 + 1),
])
def test_evidencia_invalida_rejeitada_sem_auditoria(nome, tamanho):
    demanda = _demanda_em_execucao()
    total_historico = len(demanda.historico_alteracoes)

    with pytest.raises(RegraNegocioException):
        DemandService.registrar_evidencia(demanda.id, nome, tamanho, autor_id="cli_1")
    assert demanda.evidencias == ()
    assert len(demanda.historico_alteracoes) == total_historico

def test_evidencia_exige_autor():
    demanda = _demanda_em_execucao()
    with pytest.raises(RegraNegocioException):
        DemandService.registrar_evidencia(demanda.id, "foto.png", 1024, autor_id=" ")

def test_atribuicao_e_evidencia_bloqueadas_apos_conclusao():
    demanda = _demanda_concluida()
    with pytest.raises(RegistroImutavelException):
        DemandService.atribuir_responsavel(demanda.id, "tec_2")
    with pytest.raises(RegistroImutavelException):
        DemandService.registrar_evidencia(demanda.id, "foto.png", 1024, autor_id="cli_1")


# SCRUM-20: edicao de demanda

def test_edicao_atualiza_dados_e_audita():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    DemandService.update(demanda.id, " Ajuste urgente ", "Ajuste na base de producao", autor_id="admin")

    assert demanda.titulo == "Ajuste urgente"
    entrada = demanda.historico_alteracoes[-1]
    assert entrada["acao"] == "EDICAO_DEMANDA"
    assert entrada["detalhes"]["anterior"]["titulo"] == "Ajuste"

def test_edicao_invalida_falha():
    demanda = DemandService.create("Ajuste", "Ajuste na base de dados", "cli_1")
    with pytest.raises(RegraNegocioException):
        DemandService.update(demanda.id, "A", "Ajuste na base de dados")
    assert demanda.titulo == "Ajuste"

def test_edicao_bloqueada_apos_conclusao():
    demanda = _demanda_concluida()
    with pytest.raises(RegistroImutavelException):
        DemandService.update(demanda.id, "Novo titulo", "Nova descricao")

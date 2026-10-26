from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text # type: ignore
from sqlalchemy.exc import DBAPIError, IntegrityError # type: ignore

from app.core.exceptions import (
    AcessoNegadoException,
    AprovacaoNaoAutorizadaException,
    ArquivoInvalidoException,
    RecursoNaoEncontradoException,
    RegistroImutavelException,
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
)
from app.domain.models import (
    AceiteFormal,
    Anexo,
    AuditoriaLog,
    EtapaOperacional,
    HistoricoStatusPedido,
    Ocorrencia,
    Pedido,
)
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum as Status, TipoOcorrenciaEnum
from app.schemas.pedido import PedidoUpdate
from app.services.anexo_service import AnexoService
from app.services.demand_service import DemandService
from app.services.pedido_service import PedidoService
from tests import amostras


@pytest.fixture
def service(db, storage):
    return DemandService(db, anexo_service=AnexoService(db, storage=storage))


@pytest.fixture
def atores(criar_usuario):
    return {
        "admin": criar_usuario(PerfilEnum.ADMIN),
        "cliente": criar_usuario(PerfilEnum.CLIENTE),
        "outro_cliente": criar_usuario(PerfilEnum.CLIENTE),
        "tecnico": criar_usuario(PerfilEnum.TECNICO),
        "outro_tecnico": criar_usuario(PerfilEnum.TECNICO),
    }


@pytest.fixture
def demanda(service, atores):
    pedido = service.criar(atores["cliente"], titulo="Manutencao notebook", descricao="Troca de pasta termica")
    service.atribuir_responsavel(atores["admin"], pedido.id, responsavel_id=atores["tecnico"].id)
    return pedido


def _em_homologacao(service, atores, pedido):
    service.alterar_status(atores["tecnico"], pedido.id, Status.EXECUCAO)
    etapa = service.adicionar_etapa(atores["tecnico"], pedido.id, descricao="Executar servico")
    service.concluir_etapa(atores["tecnico"], pedido.id, etapa.id)
    service.alterar_status(atores["tecnico"], pedido.id, Status.HOMOLOGACAO)
    return pedido


def _concluida(service, atores, pedido):
    _em_homologacao(service, atores, pedido)
    service.aprovar_homologacao(atores["cliente"], pedido.id, versao_entregavel="v1.0",
                                declaracao_aceite="Aprovo a entrega conforme combinado.")
    return pedido


def _recarregar(db, pedido):
    db.expire_all()
    return db.get(Pedido, pedido.id)


def _acoes(db, pedido):
    return [log.acao for log in db.scalars(
        select(AuditoriaLog).where(AuditoriaLog.pedido_id == pedido.id).order_by(AuditoriaLog.created_at)
    )]


def _contar(db, modelo, **filtros):
    stmt = select(func.count()).select_from(modelo)
    for campo, valor in filtros.items():
        stmt = stmt.where(getattr(modelo, campo) == valor)
    return db.scalar(stmt)


# ----------------------------------------------------------------------
# Cadastro, edicao e exclusao persistidos
# ----------------------------------------------------------------------

def test_cliente_cria_demanda_persistida_para_si(db, service, atores):
    pedido = service.criar(atores["cliente"], titulo="  Ajuste  ", descricao="Ajuste na base de dados")

    salvo = _recarregar(db, pedido)
    assert salvo.cliente_id == atores["cliente"].id
    assert salvo.titulo == "Ajuste"
    assert salvo.status == Status.PLANEAMENTO
    assert salvo.percentual_progresso == Decimal("15.00")
    assert salvo.codigo_identificador.startswith("DEM-")
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.pedido_id == pedido.id))
    assert (log.acao, log.usuario_id) == ("CRIACAO_DEMANDA", atores["cliente"].id)


def test_cliente_nao_cria_demanda_para_outro_cliente(service, atores):
    with pytest.raises(AcessoNegadoException):
        service.criar(atores["cliente"], titulo="Ajuste", descricao="Ajuste na base",
                      cliente_id=atores["outro_cliente"].id)


def test_tecnico_nao_cria_demanda(service, atores):
    with pytest.raises(AcessoNegadoException):
        service.criar(atores["tecnico"], titulo="Ajuste", descricao="Ajuste na base")


def test_admin_cria_demanda_somente_para_cliente_ativo(service, atores, criar_usuario):
    pedido = service.criar(atores["admin"], titulo="Ajuste", descricao="Ajuste na base",
                           cliente_id=atores["cliente"].id)
    assert pedido.cliente_id == atores["cliente"].id

    with pytest.raises(AcessoNegadoException):
        service.criar(atores["admin"], titulo="Ajuste", descricao="Ajuste na base")
    with pytest.raises(RecursoNaoEncontradoException):
        service.criar(atores["admin"], titulo="Ajuste", descricao="Ajuste na base",
                      cliente_id=atores["tecnico"].id)
    inativo = criar_usuario(PerfilEnum.CLIENTE, ativo=False)
    with pytest.raises(RecursoNaoEncontradoException):
        service.criar(atores["admin"], titulo="Ajuste", descricao="Ajuste na base", cliente_id=inativo.id)


@pytest.mark.parametrize("usuario", [None, "inativo"])
def test_operacoes_exigem_usuario_autenticado_ativo(service, demanda, criar_usuario, usuario):
    if usuario == "inativo":
        usuario = criar_usuario(PerfilEnum.ADMIN, ativo=False)
    with pytest.raises(AcessoNegadoException):
        service.editar(usuario, demanda.id, titulo="Novo titulo", descricao="Nova descricao")
    with pytest.raises(AcessoNegadoException):
        service.alterar_status(usuario, demanda.id, Status.EXECUCAO)


def test_edicao_persiste_e_audita_valores_anteriores(db, service, atores, demanda):
    service.editar(atores["cliente"], demanda.id, titulo="Ajuste urgente", descricao="Ajuste na base de producao")

    salvo = _recarregar(db, demanda)
    assert salvo.titulo == "Ajuste urgente"
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "EDICAO_DEMANDA",
                                               AuditoriaLog.pedido_id == demanda.id))
    assert log.usuario_id == atores["cliente"].id
    assert log.detalhes["anterior"]["titulo"] == "Manutencao notebook"


def test_edicao_invalida_nao_altera_banco(db, service, atores, demanda):
    with pytest.raises(RegraNegocioException):
        service.editar(atores["cliente"], demanda.id, titulo="A", descricao="Descricao valida")
    assert _recarregar(db, demanda).titulo == "Manutencao notebook"


def test_tecnico_nao_edita_e_cliente_de_outra_demanda_nao_enxerga(service, atores, demanda):
    with pytest.raises(AcessoNegadoException):
        service.editar(atores["tecnico"], demanda.id, titulo="Novo titulo", descricao="Nova descricao")
    with pytest.raises(RecursoNaoEncontradoException):
        service.editar(atores["outro_cliente"], demanda.id, titulo="Novo titulo", descricao="Nova descricao")


def test_somente_admin_exclui_e_auditoria_sobrevive(db, service, atores, demanda):
    with pytest.raises(AcessoNegadoException):
        service.excluir(atores["cliente"], demanda.id)

    pedido_id = demanda.id
    service.excluir(atores["admin"], pedido_id)

    db.expire_all()
    assert db.get(Pedido, pedido_id) is None
    log = db.scalar(select(AuditoriaLog).where(
        AuditoriaLog.acao == "EXCLUSAO_DEMANDA",
        AuditoriaLog.detalhes["pedido_id"].astext == str(pedido_id),
    ))
    assert log.usuario_id == atores["admin"].id
    assert log.pedido_id is None
    assert log.detalhes["pedido_id"] == str(pedido_id)


# ----------------------------------------------------------------------
# Maquina de estados e etapas (SCRUM-71)
# ----------------------------------------------------------------------

def test_somente_equipe_operacional_avanca_estado(service, atores, demanda):
    with pytest.raises(AcessoNegadoException):
        service.alterar_status(atores["cliente"], demanda.id, Status.EXECUCAO)
    with pytest.raises(RecursoNaoEncontradoException):
        service.alterar_status(atores["outro_tecnico"], demanda.id, Status.EXECUCAO)

    pedido = service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)
    assert pedido.status == Status.EXECUCAO


def test_transicao_grava_historico_e_auditoria_com_autor(db, service, atores, demanda):
    service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)

    historico = db.scalar(select(HistoricoStatusPedido).where(HistoricoStatusPedido.pedido_id == demanda.id))
    assert (historico.status_anterior, historico.status_novo) == (Status.PLANEAMENTO, Status.EXECUCAO)
    assert historico.usuario_id == atores["tecnico"].id
    assert _acoes(db, demanda)[-1] == "ALTERACAO_ESTADO"


def test_conclusao_nao_pode_ser_feita_por_alteracao_de_status(service, atores, demanda):
    _em_homologacao(service, atores, demanda)
    with pytest.raises(AprovacaoNaoAutorizadaException, match="aceite formal"):
        service.alterar_status(atores["admin"], demanda.id, Status.CONCLUIDO)
    with pytest.raises(TransicaoEstadoInvalidaException, match="rejeicao do cliente"):
        service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)


def test_homologacao_bloqueada_por_etapa_pendente_sem_gravar_nada(db, service, atores, demanda):
    service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)
    etapa = service.adicionar_etapa(atores["tecnico"], demanda.id, descricao="Trocar pasta termica")
    service.adicionar_etapa(atores["tecnico"], demanda.id, descricao="Testar temperatura")
    service.concluir_etapa(atores["tecnico"], demanda.id, etapa.id)
    historicos = _contar(db, HistoricoStatusPedido, pedido_id=demanda.id)

    with pytest.raises(TransicaoEstadoInvalidaException, match="Testar temperatura"):
        service.alterar_status(atores["tecnico"], demanda.id, Status.HOMOLOGACAO)

    assert _recarregar(db, demanda).status == Status.EXECUCAO
    assert _contar(db, HistoricoStatusPedido, pedido_id=demanda.id) == historicos


def test_progresso_persistido_acompanha_etapas(db, service, atores, demanda):
    service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)
    etapas = [service.adicionar_etapa(atores["tecnico"], demanda.id, descricao=f"Etapa {n}") for n in range(4)]
    assert _recarregar(db, demanda).percentual_progresso == Decimal("15.00")

    service.concluir_etapa(atores["tecnico"], demanda.id, etapas[0].id)
    service.concluir_etapa(atores["admin"], demanda.id, etapas[1].id)
    assert _recarregar(db, demanda).percentual_progresso == Decimal("50.00")

    for etapa in etapas[2:]:
        service.concluir_etapa(atores["tecnico"], demanda.id, etapa.id)
    assert _recarregar(db, demanda).percentual_progresso == Decimal("85.00")

    salva = db.get(EtapaOperacional, etapas[1].id)
    assert salva.concluida and salva.concluida_em is not None
    assert salva.concluida_por_id == atores["admin"].id

    service.alterar_status(atores["tecnico"], demanda.id, Status.HOMOLOGACAO)
    assert [e.descricao for e in service.listar_etapas(atores["cliente"], demanda.id)] == [
        "Etapa 0", "Etapa 1", "Etapa 2", "Etapa 3",
    ]


def test_regras_de_conclusao_de_etapa(service, atores, demanda, criar_usuario):
    etapa = service.adicionar_etapa(atores["tecnico"], demanda.id, descricao="Etapa planejada")
    with pytest.raises(TransicaoEstadoInvalidaException, match="EXECUCAO"):
        service.concluir_etapa(atores["tecnico"], demanda.id, etapa.id)

    service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)
    with pytest.raises(AcessoNegadoException):
        service.concluir_etapa(atores["cliente"], demanda.id, etapa.id)
    with pytest.raises(RecursoNaoEncontradoException):
        service.concluir_etapa(atores["tecnico"], demanda.id, uuid4())

    service.concluir_etapa(atores["tecnico"], demanda.id, etapa.id)
    with pytest.raises(TransicaoEstadoInvalidaException, match="ja esta concluida"):
        service.concluir_etapa(atores["tecnico"], demanda.id, etapa.id)

    service.alterar_status(atores["tecnico"], demanda.id, Status.HOMOLOGACAO)
    with pytest.raises(TransicaoEstadoInvalidaException):
        service.adicionar_etapa(atores["tecnico"], demanda.id, descricao="Etapa tardia")


def test_etapa_de_outra_demanda_nao_pode_ser_concluida(service, atores, demanda):
    outra = service.criar(atores["cliente"], titulo="Outra demanda", descricao="Outra descricao")
    service.atribuir_responsavel(atores["admin"], outra.id, responsavel_id=atores["tecnico"].id)
    etapa_outra = service.adicionar_etapa(atores["tecnico"], outra.id, descricao="Etapa alheia")
    service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)

    with pytest.raises(RecursoNaoEncontradoException):
        service.concluir_etapa(atores["tecnico"], demanda.id, etapa_outra.id)


def test_homologacao_sem_etapas_bloqueada_no_service_e_no_pedido_service(db, service, atores, demanda):
    service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)
    with pytest.raises(TransicaoEstadoInvalidaException, match="sem etapas operacionais"):
        service.alterar_status(atores["tecnico"], demanda.id, Status.HOMOLOGACAO)
    with pytest.raises(TransicaoEstadoInvalidaException, match="sem etapas operacionais"):
        PedidoService(db).atualizar(demanda.id, PedidoUpdate(status=Status.HOMOLOGACAO),
                                    usuario_id=atores["admin"].id)
    assert _recarregar(db, demanda).status == Status.EXECUCAO
    assert _contar(db, HistoricoStatusPedido, pedido_id=demanda.id) == 1


def test_pedido_service_segue_a_mesma_maquina_de_estados(db, service, atores, demanda):
    pedidos = PedidoService(db)
    with pytest.raises(TransicaoEstadoInvalidaException, match="Transicao ilegal"):
        pedidos.atualizar(demanda.id, PedidoUpdate(status=Status.HOMOLOGACAO), usuario_id=atores["admin"].id)

    pedidos.atualizar(demanda.id, PedidoUpdate(status=Status.EXECUCAO), usuario_id=atores["admin"].id)
    etapa = service.adicionar_etapa(atores["tecnico"], demanda.id, descricao="Executar servico")
    service.concluir_etapa(atores["tecnico"], demanda.id, etapa.id)
    salvo = pedidos.atualizar(demanda.id, PedidoUpdate(status=Status.HOMOLOGACAO), usuario_id=atores["admin"].id)
    assert (salvo.status, salvo.percentual_progresso) == (Status.HOMOLOGACAO, Decimal("85.00"))

    with pytest.raises(TransicaoEstadoInvalidaException, match="rejeicao do cliente"):
        pedidos.atualizar(demanda.id, PedidoUpdate(status=Status.EXECUCAO), usuario_id=atores["admin"].id)
    with pytest.raises(AprovacaoNaoAutorizadaException, match="aceite formal"):
        pedidos.atualizar(demanda.id, PedidoUpdate(status=Status.CONCLUIDO), usuario_id=atores["admin"].id)
    assert _recarregar(db, demanda).status == Status.HOMOLOGACAO


def test_linha_do_tempo_de_estados_com_autores(service, atores, demanda):
    service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)
    etapa = service.adicionar_etapa(atores["tecnico"], demanda.id, descricao="Executar servico")
    service.concluir_etapa(atores["tecnico"], demanda.id, etapa.id)
    service.alterar_status(atores["admin"], demanda.id, Status.HOMOLOGACAO)
    service.rejeitar_homologacao(atores["cliente"], demanda.id, motivo="Layout divergente do aprovado")

    eventos = service.listar_estados(atores["cliente"], demanda.id)
    assert [(e["estado_anterior"], e["novo_estado"], e["usuario_responsavel"]) for e in eventos] == [
        (None, Status.PLANEAMENTO, atores["cliente"].nome),
        (Status.PLANEAMENTO, Status.EXECUCAO, atores["tecnico"].nome),
        (Status.EXECUCAO, Status.HOMOLOGACAO, atores["admin"].nome),
        (Status.HOMOLOGACAO, Status.EXECUCAO, atores["cliente"].nome),
    ]
    with pytest.raises(RecursoNaoEncontradoException):
        service.listar_estados(atores["outro_cliente"], demanda.id)


# ----------------------------------------------------------------------
# Aceite formal (SCRUM-72)
# ----------------------------------------------------------------------

def test_aceite_do_cliente_dono_conclui_e_persiste(db, service, atores, demanda):
    _em_homologacao(service, atores, demanda)

    aceite = service.aprovar_homologacao(atores["cliente"], demanda.id, versao_entregavel="v1.0",
                                         declaracao_aceite="Aprovo a entrega conforme combinado.")

    salvo = _recarregar(db, demanda)
    assert salvo.status == Status.CONCLUIDO
    assert salvo.percentual_progresso == Decimal("100.00")
    persistido = db.scalar(select(AceiteFormal).where(AceiteFormal.pedido_id == demanda.id))
    assert persistido.id == aceite.id
    assert persistido.cliente_id == atores["cliente"].id
    assert len(persistido.hash_validacao) == 64
    assert "ACEITE_FORMAL" in _acoes(db, demanda)


@pytest.mark.parametrize("ator, erro", [
    ("outro_cliente", RecursoNaoEncontradoException),
    ("admin", AprovacaoNaoAutorizadaException),
    ("tecnico", AprovacaoNaoAutorizadaException),
])
def test_somente_cliente_dono_aprova(db, service, atores, demanda, ator, erro):
    _em_homologacao(service, atores, demanda)
    with pytest.raises(erro):
        service.aprovar_homologacao(atores[ator], demanda.id, versao_entregavel="v1.0",
                                    declaracao_aceite="Aprovo a entrega conforme combinado.")
    assert _recarregar(db, demanda).status == Status.HOMOLOGACAO
    assert _contar(db, AceiteFormal, pedido_id=demanda.id) == 0


def test_aceite_fora_de_homologacao_e_dados_invalidos(service, atores, demanda):
    with pytest.raises(TransicaoEstadoInvalidaException, match="HOMOLOGACAO"):
        service.aprovar_homologacao(atores["cliente"], demanda.id, versao_entregavel="v1.0",
                                    declaracao_aceite="Aprovo a entrega conforme combinado.")
    _em_homologacao(service, atores, demanda)
    with pytest.raises(RegraNegocioException, match="declaracao"):
        service.aprovar_homologacao(atores["cliente"], demanda.id, versao_entregavel="v1.0",
                                    declaracao_aceite="ok")


def test_segundo_aceite_e_recusado(db, service, atores, demanda):
    _concluida(service, atores, demanda)
    with pytest.raises(RegistroImutavelException):
        service.aprovar_homologacao(atores["cliente"], demanda.id, versao_entregavel="v2.0",
                                    declaracao_aceite="Aprovo novamente a entrega.")
    assert _contar(db, AceiteFormal, pedido_id=demanda.id) == 1


def test_demanda_concluida_e_imutavel_pelo_service(db, service, atores, demanda):
    _concluida(service, atores, demanda)

    with pytest.raises(RegistroImutavelException):
        service.editar(atores["cliente"], demanda.id, titulo="Novo titulo", descricao="Nova descricao")
    with pytest.raises(RegistroImutavelException):
        service.excluir(atores["admin"], demanda.id)
    with pytest.raises(RegistroImutavelException):
        service.atribuir_responsavel(atores["admin"], demanda.id, responsavel_id=atores["outro_tecnico"].id)
    with pytest.raises(RegistroImutavelException):
        service.registrar_evidencia(atores["cliente"], demanda.id, nome_arquivo="foto.png",
                                    conteudo=amostras.png())
    with pytest.raises(TransicaoEstadoInvalidaException):
        service.adicionar_etapa(atores["tecnico"], demanda.id, descricao="Etapa tardia")
    with pytest.raises(TransicaoEstadoInvalidaException):
        service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)
    with pytest.raises(TransicaoEstadoInvalidaException):
        service.rejeitar_homologacao(atores["cliente"], demanda.id, motivo="Quero reabrir a demanda")

    salvo = _recarregar(db, demanda)
    assert (salvo.status, salvo.titulo, salvo.responsavel_id) == (
        Status.CONCLUIDO, "Manutencao notebook", atores["tecnico"].id,
    )


def test_orm_recusa_alterar_ou_excluir_aceite(db, service, atores, demanda):
    _concluida(service, atores, demanda)
    aceite = db.scalar(select(AceiteFormal).where(AceiteFormal.pedido_id == demanda.id))

    aceite.versao_entregavel = "adulterada"
    with pytest.raises(RegistroImutavelException):
        db.flush()
    db.rollback()

    db.delete(db.scalar(select(AceiteFormal).where(AceiteFormal.pedido_id == demanda.id)))
    with pytest.raises(RegistroImutavelException):
        db.flush()
    db.rollback()


@pytest.mark.parametrize("sql", [
    "UPDATE aceites_formais SET versao_entregavel = 'adulterada' WHERE pedido_id = :id",
    "DELETE FROM aceites_formais WHERE pedido_id = :id",
    "UPDATE pedidos SET titulo = 'adulterado' WHERE id = :id",
    "UPDATE pedidos SET status = 'EXECUCAO' WHERE id = :id",
    "DELETE FROM pedidos WHERE id = :id",
])
def test_banco_recusa_alteracao_direta_de_demanda_concluida(db, service, atores, demanda, sql):
    _concluida(service, atores, demanda)

    with pytest.raises(DBAPIError, match="imutave"):
        with db.begin_nested():
            db.execute(text(sql), {"id": demanda.id})


def test_banco_recusa_concluir_sem_aceite_mesmo_fora_do_service(db, service, atores, demanda):
    _em_homologacao(service, atores, demanda)

    # Escrita direta pelo ORM, sem passar por nenhum service: a trigger impede o atalho.
    with pytest.raises(DBAPIError, match="aceite formal"):
        with db.begin_nested():
            demanda.status = Status.CONCLUIDO
            db.flush()
    assert _recarregar(db, demanda).status == Status.HOMOLOGACAO


def test_pedido_service_recusa_concluir_sem_aceite(db, service, atores, demanda):
    _em_homologacao(service, atores, demanda)

    with pytest.raises(AprovacaoNaoAutorizadaException):
        PedidoService(db).atualizar(demanda.id, PedidoUpdate(status=Status.CONCLUIDO),
                                    usuario_id=atores["admin"].id)
    assert _recarregar(db, demanda).status == Status.HOMOLOGACAO


def test_banco_recusa_inserir_demanda_ja_concluida(db, atores):
    with pytest.raises(DBAPIError, match="aceite formal"):
        with db.begin_nested():
            db.execute(text(
                "INSERT INTO pedidos (codigo_identificador, titulo, status, cliente_id) "
                "VALUES ('DEM-FAKE', 'Falsa', 'CONCLUIDO', :cliente)"
            ), {"cliente": atores["cliente"].id})


def test_banco_permite_um_unico_aceite_por_demanda(db, service, atores, demanda):
    _concluida(service, atores, demanda)
    with pytest.raises(IntegrityError, match="uq_aceites_formais_pedido_id"):
        with db.begin_nested():
            db.execute(text(
                "INSERT INTO aceites_formais (pedido_id, cliente_id, versao_entregavel, "
                "declaracao_aceite, hash_validacao) VALUES (:id, :cliente, 'v2', 'outra', 'x')"
            ), {"id": demanda.id, "cliente": atores["cliente"].id})


# ----------------------------------------------------------------------
# Rejeicao da homologacao
# ----------------------------------------------------------------------

def test_rejeicao_volta_para_execucao_com_ocorrencia(db, service, atores, demanda):
    _em_homologacao(service, atores, demanda)

    service.rejeitar_homologacao(atores["cliente"], demanda.id, motivo="  Layout divergente do aprovado  ")

    salvo = _recarregar(db, demanda)
    assert salvo.status == Status.EXECUCAO
    ocorrencia = db.scalar(select(Ocorrencia).where(Ocorrencia.pedido_id == demanda.id))
    assert ocorrencia.tipo == TipoOcorrenciaEnum.REGRESSO_ESTADO
    assert ocorrencia.autor_id == atores["cliente"].id
    assert ocorrencia.motivo_regresso == "Layout divergente do aprovado"
    assert (ocorrencia.status_anterior, ocorrencia.status_novo) == (Status.HOMOLOGACAO, Status.EXECUCAO)
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "REJEICAO_HOMOLOGACAO",
                                               AuditoriaLog.pedido_id == demanda.id))
    assert log.usuario_id == atores["cliente"].id
    assert log.detalhes["ocorrencia_id"] == str(ocorrencia.id)


def test_rejeicao_exige_motivo_e_cliente_dono(db, service, atores, demanda):
    _em_homologacao(service, atores, demanda)
    with pytest.raises(TransicaoEstadoInvalidaException, match="10 caracteres"):
        service.rejeitar_homologacao(atores["cliente"], demanda.id, motivo="Curto")
    with pytest.raises(AprovacaoNaoAutorizadaException):
        service.rejeitar_homologacao(atores["tecnico"], demanda.id, motivo="Motivo suficientemente longo")
    assert _recarregar(db, demanda).status == Status.HOMOLOGACAO
    assert _contar(db, Ocorrencia, pedido_id=demanda.id) == 0


# ----------------------------------------------------------------------
# Atribuicao e evidencias (SCRUM-75)
# ----------------------------------------------------------------------

def test_atribuicao_somente_admin_e_somente_tecnico_ativo(db, service, atores, demanda):
    with pytest.raises(AcessoNegadoException):
        service.atribuir_responsavel(atores["cliente"], demanda.id, responsavel_id=atores["tecnico"].id)
    with pytest.raises(RecursoNaoEncontradoException):
        service.atribuir_responsavel(atores["admin"], demanda.id, responsavel_id=atores["cliente"].id)

    service.atribuir_responsavel(atores["admin"], demanda.id, responsavel_id=atores["outro_tecnico"].id)

    assert _recarregar(db, demanda).responsavel_id == atores["outro_tecnico"].id
    log = db.scalars(select(AuditoriaLog).where(AuditoriaLog.acao == "ATRIBUICAO_RESPONSAVEL",
                                                AuditoriaLog.pedido_id == demanda.id)
                     .order_by(AuditoriaLog.created_at)).all()[-1]
    assert log.usuario_id == atores["admin"].id
    assert log.detalhes == {
        "responsavel_anterior": str(atores["tecnico"].id),
        "responsavel_novo": str(atores["outro_tecnico"].id),
    }


@pytest.mark.parametrize("ator", ["cliente", "tecnico", "admin"])
def test_evidencia_valida_e_persistida_e_auditada(db, service, storage, atores, demanda, ator):
    anexo = service.registrar_evidencia(atores[ator], demanda.id, nome_arquivo="Tela_Erro.PNG",
                                        conteudo=amostras.png())

    salvo = db.get(Anexo, anexo.id)
    assert (salvo.extensao, salvo.enviado_por_id) == ("png", atores[ator].id)
    assert storage.arquivos[salvo.caminho_storage][1] == "image/png"
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "ENVIO_EVIDENCIA",
                                               AuditoriaLog.pedido_id == demanda.id))
    assert log.usuario_id == atores[ator].id
    assert log.detalhes["anexo_id"] == str(anexo.id)


def test_evidencia_vinculada_a_ocorrencia_da_propria_demanda(db, service, atores, demanda):
    _em_homologacao(service, atores, demanda)
    service.rejeitar_homologacao(atores["cliente"], demanda.id, motivo="Layout divergente do aprovado")
    ocorrencia = db.scalar(select(Ocorrencia).where(Ocorrencia.pedido_id == demanda.id))

    anexo = service.registrar_evidencia(atores["cliente"], demanda.id, nome_arquivo="print.jpg",
                                        conteudo=amostras.jpeg(), ocorrencia_id=ocorrencia.id)
    assert anexo.ocorrencia_id == ocorrencia.id

    with pytest.raises(RecursoNaoEncontradoException):
        service.registrar_evidencia(atores["cliente"], demanda.id, nome_arquivo="print.jpg",
                                    conteudo=amostras.jpeg(), ocorrencia_id=uuid4())


def test_evidencia_invalida_nao_grava_nem_envia(db, service, storage, atores, demanda):
    with pytest.raises(ArquivoInvalidoException):
        service.registrar_evidencia(atores["cliente"], demanda.id, nome_arquivo="foto.png",
                                    conteudo=b"MZ\x90\x00 executavel")

    assert storage.arquivos == {}
    assert _contar(db, Anexo, pedido_id=demanda.id) == 0
    assert "ENVIO_EVIDENCIA" not in _acoes(db, demanda)
    # A sessao continua utilizavel e o bloqueio do pedido foi liberado.
    service.editar(atores["cliente"], demanda.id, titulo="Titulo novo", descricao="Descricao nova")


def test_evidencia_de_quem_nao_participa_da_demanda(service, atores, demanda):
    for ator in ("outro_cliente", "outro_tecnico"):
        with pytest.raises(RecursoNaoEncontradoException):
            service.registrar_evidencia(atores[ator], demanda.id, nome_arquivo="foto.png",
                                        conteudo=amostras.png())


def test_fluxo_completo_audita_todos_os_autores(db, service, atores, demanda):
    service.alterar_status(atores["tecnico"], demanda.id, Status.EXECUCAO)
    etapa = service.adicionar_etapa(atores["tecnico"], demanda.id, descricao="Executar ajuste")
    service.concluir_etapa(atores["tecnico"], demanda.id, etapa.id)
    service.registrar_evidencia(atores["tecnico"], demanda.id, nome_arquivo="laudo.pdf", conteudo=amostras.pdf())
    service.alterar_status(atores["tecnico"], demanda.id, Status.HOMOLOGACAO)
    service.aprovar_homologacao(atores["cliente"], demanda.id, versao_entregavel="v1.0",
                                declaracao_aceite="Aprovo a entrega conforme combinado.")

    logs = service.listar_auditoria(atores["cliente"], demanda.id)
    assert {log.acao for log in logs} == {
        "CRIACAO_DEMANDA", "ATRIBUICAO_RESPONSAVEL", "ALTERACAO_ESTADO", "CADASTRO_ETAPA",
        "CONCLUSAO_ETAPA", "ENVIO_EVIDENCIA", "ACEITE_FORMAL",
    }
    assert all(log.usuario_id is not None for log in logs)
    historico = db.scalars(select(HistoricoStatusPedido).where(HistoricoStatusPedido.pedido_id == demanda.id)).all()
    assert all(item.usuario_id is not None for item in historico)
    assert len(historico) == 3

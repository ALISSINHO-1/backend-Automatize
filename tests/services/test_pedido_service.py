from unittest.mock import MagicMock
from uuid import uuid4

from app.domain.models.enums import StatusPedidoEnum
from app.repositories.historico_status_pedido_repository import (
    HistoricoStatusPedidoRepository,
)

import pytest # type: ignore
from sqlalchemy.exc import IntegrityError # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.pedido import Pedido
from app.repositories.pedido_repository import PedidoRepository
from app.schemas.pedido import PedidoCreate, PedidoUpdate
from app.services.pedido_service import (
    CodigoPedidoDuplicadoError,
    PedidoNaoEncontradoError,
    PedidoService,
)


@pytest.fixture
def db_session() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def repository() -> MagicMock:
    return MagicMock(spec=PedidoRepository)

@pytest.fixture
def historico_repository() -> MagicMock:
    return MagicMock(spec=HistoricoStatusPedidoRepository)


@pytest.fixture
def service(
    db_session: MagicMock,
    repository: MagicMock,
    historico_repository: MagicMock,
) -> PedidoService:
    return PedidoService(
        db=db_session,
        repository=repository,
        historico_repository=historico_repository,
    )


def criar_pedido() -> Pedido:
    return Pedido(
        id=uuid4(),
        codigo_identificador="PED-001",
        titulo="Pedido de teste",
        cliente_id=uuid4(),
    )


def test_listar(
    service: PedidoService,
    repository: MagicMock,
) -> None:
    pedidos = [
        criar_pedido(),
        criar_pedido(),
    ]

    repository.get_all.return_value = pedidos

    resultado = service.listar(
        offset=0,
        limit=10,
    )

    assert resultado == pedidos

    repository.get_all.assert_called_once_with(
        offset=0,
        limit=10,
    )


def test_buscar_por_id(
    service: PedidoService,
    repository: MagicMock,
) -> None:
    pedido = criar_pedido()

    repository.get_by_id.return_value = pedido

    resultado = service.buscar_por_id(pedido.id)

    assert resultado is pedido

    repository.get_by_id.assert_called_once_with(
        pedido.id
    )


def test_buscar_por_id_inexistente(
    service: PedidoService,
    repository: MagicMock,
) -> None:
    pedido_id = uuid4()

    repository.get_by_id.return_value = None

    with pytest.raises(
        PedidoNaoEncontradoError,
        match="não encontrado",
    ):
        service.buscar_por_id(pedido_id)


def test_buscar_por_codigo(
    service: PedidoService,
    repository: MagicMock,
) -> None:
    pedido = criar_pedido()

    repository.get_by_codigo.return_value = pedido

    resultado = service.buscar_por_codigo(
        "PED-001"
    )

    assert resultado is pedido

    repository.get_by_codigo.assert_called_once_with(
        "PED-001"
    )


def test_buscar_por_codigo_inexistente(
    service: PedidoService,
    repository: MagicMock,
) -> None:
    repository.get_by_codigo.return_value = None

    with pytest.raises(
        PedidoNaoEncontradoError,
        match="não encontrado",
    ):
        service.buscar_por_codigo(
            "INEXISTENTE"
        )


def test_criar_faz_commit(
    service: PedidoService,
    repository: MagicMock,
    db_session: MagicMock,
) -> None:
    cliente_id = uuid4()

    dados = PedidoCreate(
        codigo_identificador="PED-002",
        titulo="Novo pedido",
        descricao="Pedido criado no teste",
        cliente_id=cliente_id,
    )

    pedido = Pedido(
        id=uuid4(),
        codigo_identificador=dados.codigo_identificador,
        titulo=dados.titulo,
        descricao=dados.descricao,
        cliente_id=cliente_id,
    )

    repository.get_by_codigo.return_value = None
    repository.create.return_value = pedido

    resultado = service.criar(dados)

    assert resultado is pedido

    repository.get_by_codigo.assert_called_once_with(
        "PED-002"
    )

    repository.create.assert_called_once()

    db_session.commit.assert_called_once()
    db_session.refresh.assert_called_once_with(pedido)
    db_session.rollback.assert_not_called()


def test_criar_rejeita_codigo_duplicado(
    service: PedidoService,
    repository: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido_existente = criar_pedido()

    repository.get_by_codigo.return_value = (
        pedido_existente
    )

    dados = PedidoCreate(
        codigo_identificador="PED-001",
        titulo="Pedido duplicado",
        cliente_id=uuid4(),
    )

    with pytest.raises(
        CodigoPedidoDuplicadoError,
        match="Já existe",
    ):
        service.criar(dados)

    repository.create.assert_not_called()
    db_session.commit.assert_not_called()


def test_criar_faz_rollback_em_erro(
    service: PedidoService,
    repository: MagicMock,
    db_session: MagicMock,
) -> None:
    dados = PedidoCreate(
        codigo_identificador="PED-003",
        titulo="Pedido com erro",
        cliente_id=uuid4(),
    )

    repository.get_by_codigo.return_value = None

    repository.create.side_effect = RuntimeError(
        "Erro de persistência"
    )

    with pytest.raises(
        RuntimeError,
        match="Erro de persistência",
    ):
        service.criar(dados)

    db_session.commit.assert_not_called()
    db_session.rollback.assert_called_once()


def test_criar_faz_rollback_em_integrity_error(
    service: PedidoService,
    repository: MagicMock,
    db_session: MagicMock,
) -> None:
    dados = PedidoCreate(
        codigo_identificador="PED-004",
        titulo="Pedido integrity error",
        cliente_id=uuid4(),
    )

    repository.get_by_codigo.return_value = None

    repository.create.side_effect = IntegrityError(
        statement="INSERT",
        params={},
        orig=Exception("constraint violation"),
    )

    with pytest.raises(IntegrityError):
        service.criar(dados)

    db_session.commit.assert_not_called()
    db_session.rollback.assert_called_once()


def test_atualizar_faz_commit(
    service: PedidoService,
    repository: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido = criar_pedido()

    repository.get_by_id.return_value = pedido
    repository.update.return_value = pedido

    dados = PedidoUpdate(
        titulo="Título atualizado"
    )

    resultado = service.atualizar(
        pedido.id,
        dados,
    )

    assert resultado is pedido

    repository.update.assert_called_once()

    db_session.commit.assert_called_once()
    db_session.refresh.assert_called_once_with(pedido)
    db_session.rollback.assert_not_called()


def test_atualizar_faz_rollback_em_erro(
    service: PedidoService,
    repository: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido = criar_pedido()

    repository.get_by_id.return_value = pedido

    repository.update.side_effect = RuntimeError(
        "Erro ao atualizar"
    )

    dados = PedidoUpdate(
        titulo="Novo título"
    )

    with pytest.raises(
        RuntimeError,
        match="Erro ao atualizar",
    ):
        service.atualizar(
            pedido.id,
            dados,
        )

    db_session.commit.assert_not_called()
    db_session.rollback.assert_called_once()
    
    
def test_atualizar_status_cria_historico(
    service: PedidoService,
    repository: MagicMock,
    historico_repository: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido = criar_pedido()
    pedido.status = StatusPedidoEnum.PLANEAMENTO

    usuario_id = uuid4()

    repository.get_by_id.return_value = pedido

    def atualizar_pedido(
        entidade: Pedido,
        dados: dict,
    ) -> Pedido:
        entidade.status = dados["status"]
        return entidade

    repository.update.side_effect = atualizar_pedido

    dados = PedidoUpdate(
        status=StatusPedidoEnum.EXECUCAO
    )

    resultado = service.atualizar(
        pedido.id,
        dados,
        usuario_id=usuario_id,
    )

    assert resultado.status == StatusPedidoEnum.EXECUCAO

    historico_repository.create.assert_called_once_with(
        {
            "pedido_id": pedido.id,
            "status_anterior": StatusPedidoEnum.PLANEAMENTO,
            "status_novo": StatusPedidoEnum.EXECUCAO,
            "usuario_id": usuario_id,
        }
    )

    db_session.commit.assert_called_once()
    db_session.rollback.assert_not_called()


def test_atualizar_sem_mudar_status_nao_cria_historico(
    service: PedidoService,
    repository: MagicMock,
    historico_repository: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido = criar_pedido()
    pedido.status = StatusPedidoEnum.PLANEAMENTO

    repository.get_by_id.return_value = pedido
    repository.update.return_value = pedido

    dados = PedidoUpdate(
        titulo="Novo título"
    )

    resultado = service.atualizar(
        pedido.id,
        dados,
    )

    assert resultado is pedido

    historico_repository.create.assert_not_called()

    db_session.commit.assert_called_once()
    db_session.rollback.assert_not_called()


def test_atualizar_status_sem_usuario_faz_rollback(
    service: PedidoService,
    repository: MagicMock,
    historico_repository: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido = criar_pedido()
    pedido.status = StatusPedidoEnum.PLANEAMENTO

    repository.get_by_id.return_value = pedido

    def atualizar_pedido(
        entidade: Pedido,
        dados: dict,
    ) -> Pedido:
        entidade.status = dados["status"]
        return entidade

    repository.update.side_effect = atualizar_pedido

    dados = PedidoUpdate(
        status=StatusPedidoEnum.EXECUCAO
    )

    with pytest.raises(
        ValueError,
        match="usuario_id é obrigatório",
    ):
        service.atualizar(
            pedido.id,
            dados,
        )

    historico_repository.create.assert_not_called()

    db_session.commit.assert_not_called()
    db_session.rollback.assert_called_once()


def test_atualizar_status_rollback_se_historico_falhar(
    service: PedidoService,
    repository: MagicMock,
    historico_repository: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido = criar_pedido()
    pedido.status = StatusPedidoEnum.PLANEAMENTO

    usuario_id = uuid4()

    repository.get_by_id.return_value = pedido

    def atualizar_pedido(
        entidade: Pedido,
        dados: dict,
    ) -> Pedido:
        entidade.status = dados["status"]
        return entidade

    repository.update.side_effect = atualizar_pedido

    historico_repository.create.side_effect = RuntimeError(
        "Erro ao registrar histórico"
    )

    dados = PedidoUpdate(
        status=StatusPedidoEnum.EXECUCAO
    )

    with pytest.raises(
        RuntimeError,
        match="Erro ao registrar histórico",
    ):
        service.atualizar(
            pedido.id,
            dados,
            usuario_id=usuario_id,
        )

    db_session.commit.assert_not_called()
    db_session.rollback.assert_called_once()


def test_excluir_faz_commit(
    service: PedidoService,
    repository: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido = criar_pedido()

    repository.get_by_id.return_value = pedido

    service.excluir(pedido.id)

    repository.delete.assert_called_once_with(
        pedido
    )

    db_session.commit.assert_called_once()
    db_session.rollback.assert_not_called()


def test_excluir_faz_rollback_em_erro(
    service: PedidoService,
    repository: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido = criar_pedido()

    repository.get_by_id.return_value = pedido

    repository.delete.side_effect = RuntimeError(
        "Erro ao excluir"
    )

    with pytest.raises(
        RuntimeError,
        match="Erro ao excluir",
    ):
        service.excluir(pedido.id)

    db_session.commit.assert_not_called()
    db_session.rollback.assert_called_once()
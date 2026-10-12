from unittest.mock import MagicMock
from uuid import uuid4

import pytest # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.enums import StatusPedidoEnum
from app.domain.models.pedido import Pedido
from app.repositories.pedido_repository import PedidoRepository


@pytest.fixture
def db_session() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def repository(
    db_session: MagicMock,
) -> PedidoRepository:
    return PedidoRepository(db_session)


def test_get_by_codigo(
    repository: PedidoRepository,
    db_session: MagicMock,
) -> None:
    pedido = Pedido(
        id=uuid4(),
        codigo_identificador="PED-001",
        titulo="Pedido teste",
        cliente_id=uuid4(),
    )

    db_session.scalar.return_value = pedido

    resultado = repository.get_by_codigo("PED-001")

    assert resultado is pedido
    assert resultado.codigo_identificador == "PED-001"

    db_session.scalar.assert_called_once()


def test_get_by_codigo_retorna_none(
    repository: PedidoRepository,
    db_session: MagicMock,
) -> None:
    db_session.scalar.return_value = None

    resultado = repository.get_by_codigo("INEXISTENTE")

    assert resultado is None

    db_session.scalar.assert_called_once()


def test_exists_by_codigo_true(
    repository: PedidoRepository,
    db_session: MagicMock,
) -> None:
    db_session.scalar.return_value = uuid4()

    resultado = repository.exists_by_codigo("PED-001")

    assert resultado is True

    db_session.scalar.assert_called_once()


def test_exists_by_codigo_false(
    repository: PedidoRepository,
    db_session: MagicMock,
) -> None:
    db_session.scalar.return_value = None

    resultado = repository.exists_by_codigo("INEXISTENTE")

    assert resultado is False

    db_session.scalar.assert_called_once()


def test_get_by_cliente(
    repository: PedidoRepository,
    db_session: MagicMock,
) -> None:
    cliente_id = uuid4()

    pedidos = [
        Pedido(
            id=uuid4(),
            codigo_identificador="PED-001",
            titulo="Pedido 1",
            cliente_id=cliente_id,
        ),
        Pedido(
            id=uuid4(),
            codigo_identificador="PED-002",
            titulo="Pedido 2",
            cliente_id=cliente_id,
        ),
    ]

    scalar_result = MagicMock()
    scalar_result.all.return_value = pedidos

    db_session.scalars.return_value = scalar_result

    resultado = repository.get_by_cliente(cliente_id)

    assert resultado == pedidos
    assert len(resultado) == 2

    db_session.scalars.assert_called_once()


def test_get_by_status(
    repository: PedidoRepository,
    db_session: MagicMock,
) -> None:
    pedidos = [
        Pedido(
            id=uuid4(),
            codigo_identificador="PED-003",
            titulo="Pedido em execução",
            cliente_id=uuid4(),
            status=StatusPedidoEnum.EXECUCAO,
        )
    ]

    scalar_result = MagicMock()
    scalar_result.all.return_value = pedidos

    db_session.scalars.return_value = scalar_result

    resultado = repository.get_by_status(
        StatusPedidoEnum.EXECUCAO
    )

    assert resultado == pedidos
    assert len(resultado) == 1
    assert resultado[0].status == StatusPedidoEnum.EXECUCAO

    db_session.scalars.assert_called_once()


def test_get_by_responsavel(
    repository: PedidoRepository,
    db_session: MagicMock,
) -> None:
    responsavel_id = uuid4()

    pedidos = [
        Pedido(
            id=uuid4(),
            codigo_identificador="PED-004",
            titulo="Pedido atribuído",
            cliente_id=uuid4(),
            responsavel_id=responsavel_id,
        )
    ]

    scalar_result = MagicMock()
    scalar_result.all.return_value = pedidos

    db_session.scalars.return_value = scalar_result

    resultado = repository.get_by_responsavel(
        responsavel_id
    )

    assert resultado == pedidos
    assert resultado[0].responsavel_id == responsavel_id

    db_session.scalars.assert_called_once()
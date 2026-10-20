from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.pedido import Pedido
from app.repositories.base_repository import BaseRepository


@pytest.fixture
def db_session() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def repository(
    db_session: MagicMock,
) -> BaseRepository[Pedido]:
    return BaseRepository(
        Pedido,
        db_session,
    )


def test_get_by_id(
    repository: BaseRepository[Pedido],
    db_session: MagicMock,
) -> None:
    pedido_id = uuid4()

    pedido = Pedido(
        id=pedido_id,
        codigo_identificador="TEST-001",
        titulo="Pedido de teste",
        cliente_id=uuid4(),
    )

    db_session.get.return_value = pedido

    resultado = repository.get_by_id(pedido_id)

    assert resultado is pedido

    db_session.get.assert_called_once_with(
        Pedido,
        pedido_id,
    )


def test_create(
    repository: BaseRepository[Pedido],
    db_session: MagicMock,
) -> None:
    cliente_id = uuid4()

    dados = {
        "codigo_identificador": "TEST-002",
        "titulo": "Novo pedido",
        "cliente_id": cliente_id,
    }

    resultado = repository.create(dados)

    assert isinstance(resultado, Pedido)
    assert resultado.codigo_identificador == "TEST-002"
    assert resultado.titulo == "Novo pedido"
    assert resultado.cliente_id == cliente_id

    db_session.add.assert_called_once_with(resultado)
    db_session.flush.assert_called_once()
    db_session.refresh.assert_called_once_with(resultado)


def test_update(
    repository: BaseRepository[Pedido],
    db_session: MagicMock,
) -> None:
    pedido = Pedido(
        id=uuid4(),
        codigo_identificador="TEST-003",
        titulo="Título antigo",
        cliente_id=uuid4(),
    )

    resultado = repository.update(
        pedido,
        {
            "titulo": "Título atualizado",
        },
    )

    assert resultado.titulo == "Título atualizado"

    db_session.flush.assert_called_once()
    db_session.refresh.assert_called_once_with(pedido)


@pytest.mark.parametrize(
    "campo",
    [
        "id",
        "created_at",
        "updated_at",
    ],
)
def test_update_rejeita_campos_protegidos(
    repository: BaseRepository[Pedido],
    campo: str,
) -> None:
    pedido = Pedido(
        id=uuid4(),
        codigo_identificador="TEST-004",
        titulo="Pedido",
        cliente_id=uuid4(),
    )

    with pytest.raises(
        ValueError,
        match="campos protegidos",
    ):
        repository.update(
            pedido,
            {
                campo: datetime.now(),
            },
        )


def test_update_rejeita_campo_inexistente(
    repository: BaseRepository[Pedido],
) -> None:
    pedido = Pedido(
        id=uuid4(),
        codigo_identificador="TEST-005",
        titulo="Pedido",
        cliente_id=uuid4(),
    )

    with pytest.raises(
        ValueError,
        match="não existe",
    ):
        repository.update(
            pedido,
            {
                "campo_inexistente": "valor",
            },
        )


def test_delete(
    repository: BaseRepository[Pedido],
    db_session: MagicMock,
) -> None:
    pedido = Pedido(
        id=uuid4(),
        codigo_identificador="TEST-006",
        titulo="Pedido",
        cliente_id=uuid4(),
    )

    repository.delete(pedido)

    db_session.delete.assert_called_once_with(pedido)
    db_session.flush.assert_called_once()
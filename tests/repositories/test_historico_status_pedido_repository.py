from unittest.mock import MagicMock
from uuid import uuid4

from app.domain.models.historico_status_pedido import HistoricoStatusPedido
from app.repositories.historico_status_pedido_repository import (
    HistoricoStatusPedidoRepository,
)


def test_get_by_pedido():
    db = MagicMock()
    repository = HistoricoStatusPedidoRepository(db)

    pedido_id = uuid4()

    historicos = [
        MagicMock(spec=HistoricoStatusPedido),
        MagicMock(spec=HistoricoStatusPedido),
    ]

    db.scalars.return_value.all.return_value = historicos

    resultado = repository.get_by_pedido(pedido_id)

    assert resultado == historicos
    db.scalars.assert_called_once()


def test_get_by_usuario():
    db = MagicMock()
    repository = HistoricoStatusPedidoRepository(db)

    usuario_id = uuid4()

    historicos = [
        MagicMock(spec=HistoricoStatusPedido),
    ]

    db.scalars.return_value.all.return_value = historicos

    resultado = repository.get_by_usuario(usuario_id)

    assert resultado == historicos
    db.scalars.assert_called_once()


def test_create_historico():
    db = MagicMock()
    repository = HistoricoStatusPedidoRepository(db)

    pedido_id = uuid4()
    usuario_id = uuid4()

    dados = {
        "pedido_id": pedido_id,
        "status_anterior": "PLANEAMENTO",
        "status_novo": "EXECUCAO",
        "usuario_id": usuario_id,
    }

    historico = repository.create(dados)

    assert historico.pedido_id == pedido_id
    assert historico.status_anterior == "PLANEAMENTO"
    assert historico.status_novo == "EXECUCAO"
    assert historico.usuario_id == usuario_id

    db.add.assert_called_once_with(historico)
    db.flush.assert_called_once()
    db.refresh.assert_called_once_with(historico)
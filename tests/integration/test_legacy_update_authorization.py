import pytest

from app.core.exceptions import AcessoNegadoException, RecursoNaoEncontradoException
from app.schemas.pedido import PedidoUpdate
from app.services.pedido_service import PedidoService
from tests.integration.test_demand_service_db import atores, demanda, service  # noqa: F401


@pytest.mark.parametrize("actor,fields,error", [
    ("cliente", {"status": "EXECUCAO"}, AcessoNegadoException),
    ("outro_cliente", {"titulo": "Tentativa horizontal"}, RecursoNaoEncontradoException),
    ("outro_tecnico", {"status": "EXECUCAO"}, RecursoNaoEncontradoException),
    ("tecnico", {"titulo": "Edicao nao autorizada"}, AcessoNegadoException),
    ("cliente", {"percentual_progresso": 100}, ValueError),
    ("admin", {"status": None}, ValueError),
])
def test_legacy_update_cannot_bypass_actor_scope(db, atores, demanda, actor, fields, error):
    with pytest.raises(error):
        PedidoService(db).atualizar(demanda.id, PedidoUpdate(**fields), usuario_id=atores[actor].id)


def test_legacy_assignment_requires_admin_and_does_not_change_before_validation(db, atores, demanda):
    with pytest.raises(AcessoNegadoException):
        PedidoService(db).atualizar(demanda.id, PedidoUpdate(responsavel_id=atores["outro_tecnico"].id),
                                    usuario_id=atores["tecnico"].id)


def test_legacy_update_requires_an_authenticated_actor(db, demanda):
    with pytest.raises(ValueError, match="usuario_id"):
        PedidoService(db).atualizar(demanda.id, PedidoUpdate(titulo="Sem autor"))

"""SCRUM-71 scenarios against real PostgreSQL, both services and JWT routes."""
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.exceptions import TransicaoEstadoInvalidaException
from app.domain.models import AuditoriaLog, HistoricoStatusPedido, Pedido
from app.domain.models.enums import StatusPedidoEnum as Status
from app.schemas.pedido import PedidoUpdate
from app.services.demand_service import DemandService
from app.services.pedido_service import PedidoService
from tests.integration.test_demandas_acoes_api import (  # noqa: F401
    atores, auth, client, demanda_id, settings,
)


SCENARIOS = [
    pytest.param(Status.PLANEAMENTO, 0, 0, False, id="A-zero-planeamento"),
    pytest.param(Status.EXECUCAO, 0, 0, False, id="A-zero-execucao"),
    pytest.param(Status.EXECUCAO, 1, 0, False, id="B-one-pending"),
    pytest.param(Status.EXECUCAO, 3, 2, False, id="C-many-one-pending"),
    pytest.param(Status.EXECUCAO, 1, 1, True, id="D-one-completed"),
    pytest.param(Status.EXECUCAO, 3, 3, True, id="D-all-completed"),
]


def persisted_state(db, order_id):
    db.expire_all()
    order = db.get(Pedido, order_id)
    counts = tuple(db.scalar(select(func.count()).select_from(model).where(
        model.pedido_id == order_id,
    )) for model in (HistoricoStatusPedido, AuditoriaLog))
    return order.status, order.percentual_progresso, *counts


@pytest.mark.parametrize("entrypoint", ["DemandService", "PedidoService"])
@pytest.mark.parametrize("initial,total,completed,allowed", SCENARIOS)
def test_scrum71_services_and_rejected_transaction(
    db, atores, entrypoint, initial, total, completed, allowed,
):
    service = DemandService(db)
    actor = atores["tecnico"]
    order = service.criar(atores["cliente"], titulo="SCRUM-71 checklist", descricao="Official homologation rule")
    order_id = order.id
    service.atribuir_responsavel(atores["admin"], order_id, responsavel_id=actor.id)
    stage_ids = [service.adicionar_etapa(actor, order_id, descricao=f"Stage {i}").id for i in range(total)]
    if initial == Status.EXECUCAO:
        service.alterar_status(actor, order_id, Status.EXECUCAO)
    for stage_id in stage_ids[:completed]:
        service.concluir_etapa(actor, order_id, stage_id)
    before = persisted_state(db, order_id)

    def transition():
        if entrypoint == "DemandService":
            return service.alterar_status(actor, order_id, Status.HOMOLOGACAO)
        return PedidoService(db).atualizar(
            order_id, PedidoUpdate(status=Status.HOMOLOGACAO), usuario_id=actor.id,
        )

    if allowed:
        transition()
        after = persisted_state(db, order_id)
        assert after[:2] == (Status.HOMOLOGACAO, Decimal("85.00"))
        assert after[2:] == (before[2] + 1, before[3] + 1)
    else:
        with pytest.raises(TransicaoEstadoInvalidaException):
            transition()
        assert db.is_active
        assert persisted_state(db, order_id) == before
        assert len(service.listar_etapas(actor, order_id)) == total


@pytest.mark.parametrize("initial,total,completed,allowed", SCENARIOS)
def test_scrum71_jwt_api_and_persisted_rollback(
    client, auth, db, demanda_id, initial, total, completed, allowed,
):
    stage_ids = []
    for i in range(total):
        response = client.post(f"/demandas/{demanda_id}/etapas", headers=auth["tecnico"],
                               json={"descricao": f"Stage {i}"})
        assert response.status_code == 201, response.text
        stage_ids.append(response.json()["id"])
    if initial == Status.EXECUCAO:
        response = client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"],
                               json={"status": "EXECUCAO"})
        assert response.status_code == 200, response.text
    for stage_id in stage_ids[:completed]:
        response = client.post(f"/demandas/{demanda_id}/etapas/{stage_id}/conclusao", headers=auth["tecnico"])
        assert response.status_code == 200, response.text
    order_id = UUID(demanda_id)
    before = persisted_state(db, order_id)
    response = client.post(f"/demandas/{demanda_id}/status", headers=auth["tecnico"],
                           json={"status": "HOMOLOGACAO"})
    assert response.status_code == (200 if allowed else 409), response.text
    if allowed:
        assert persisted_state(db, order_id)[:2] == (Status.HOMOLOGACAO, Decimal("85.00"))
    else:
        assert persisted_state(db, order_id) == before
        assert db.is_active

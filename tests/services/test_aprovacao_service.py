from decimal import Decimal
from hashlib import sha256
import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.orm import Session

from app.domain.models import AceiteFormal, AuditoriaLog, HistoricoStatusPedido, Pedido, User
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum
from app.services.aprovacao_service import AprovacaoService
from app.services.pedido_service import PedidoNaoEncontradoError


@pytest.fixture
def approval():
    client = User(id=uuid4(), nome="Cliente", email="cliente@example.com",
                  senha_hash="unused", ativo=True, perfil=PerfilEnum.CLIENTE)
    pedido = Pedido(id=uuid4(), codigo_identificador="PED-001", titulo="Entrega",
                    cliente_id=client.id, status=StatusPedidoEnum.HOMOLOGACAO)
    db = MagicMock(spec=Session)
    db.scalar.return_value = pedido
    db.get.return_value = client
    return db, pedido, client


def register(approval, **overrides):
    db, pedido, client = approval
    values = {"pedido_id": pedido.id, "cliente_id": client.id,
              "versao_entregavel": "v1.0", "declaracao_aceite": "Aprovo a entrega."}
    return AprovacaoService(db).registrar_aceite(**(values | overrides))


def test_approval_persists_evidence_history_and_audit_atomically(approval):
    db, pedido, client = approval
    aceite = register(approval)
    persisted = [call.args[0] for call in db.add.call_args_list]
    assert [type(item) for item in persisted] == [AceiteFormal, HistoricoStatusPedido, AuditoriaLog]
    assert persisted[0] is aceite
    assert aceite.pedido_id == pedido.id and aceite.cliente_id == client.id
    assert aceite.data_hora_aceite.tzinfo is not None
    evidence = {
        "id": str(aceite.id), "pedido_id": str(pedido.id), "cliente_id": str(client.id),
        "data_hora_aceite": aceite.data_hora_aceite.isoformat(),
        "versao_entregavel": "v1.0", "declaracao_aceite": "Aprovo a entrega.",
    }
    expected_hash = sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()
    assert aceite.hash_validacao == expected_hash
    assert persisted[1].status_anterior == StatusPedidoEnum.HOMOLOGACAO
    assert persisted[1].status_novo == StatusPedidoEnum.CONCLUIDO
    assert persisted[1].usuario_id == client.id
    assert persisted[2].detalhes["aceite_id"] == str(aceite.id)
    assert pedido.status == StatusPedidoEnum.CONCLUIDO
    assert pedido.percentual_progresso == Decimal("100.00")
    assert "FOR UPDATE" in str(db.scalar.call_args.args[0].compile(dialect=dialect()))
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


@pytest.mark.parametrize("status", [StatusPedidoEnum.PLANEAMENTO, StatusPedidoEnum.EXECUCAO,
                                    StatusPedidoEnum.CONCLUIDO])
def test_approval_rejects_wrong_status_without_writes(approval, status):
    db, pedido, _ = approval
    pedido.status = status
    with pytest.raises(ValueError, match="HOMOLOGACAO"):
        register(approval)
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.parametrize("reason", ["other-client", "inactive", "wrong-profile", "missing"])
def test_approval_requires_active_owning_client(approval, reason):
    db, pedido, client = approval
    if reason == "other-client":
        pedido.cliente_id = uuid4()
    elif reason == "inactive":
        client.ativo = False
    elif reason == "wrong-profile":
        client.perfil = PerfilEnum.ADMIN
    else:
        db.get.return_value = None
    with pytest.raises(PermissionError):
        register(approval)
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_approval_missing_order(approval):
    db, _, _ = approval
    db.scalar.return_value = None
    with pytest.raises(PedidoNaoEncontradoError):
        register(approval)
    db.add.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.parametrize("stage", ["evidence", "history", "audit", "commit"])
def test_approval_rolls_back_any_persistence_failure(approval, stage):
    db, _, _ = approval
    if stage == "commit":
        db.commit.side_effect = RuntimeError("write failed")
    else:
        failure_at = {"evidence": 0, "history": 1, "audit": 2}[stage]
        db.flush.side_effect = [None] * failure_at + [RuntimeError("write failed")]
    with pytest.raises(RuntimeError, match="write failed"):
        register(approval)
    db.rollback.assert_called_once()
    if stage != "commit":
        db.commit.assert_not_called()


@pytest.mark.parametrize("values", [{"versao_entregavel": " "}, {"versao_entregavel": "x" * 51},
                                    {"declaracao_aceite": " "}])
def test_approval_requires_version_and_declaration(approval, values):
    db, _, _ = approval
    with pytest.raises(ValueError):
        register(approval, **values)
    db.scalar.assert_not_called()
    db.add.assert_not_called()


def test_hml_entry_point_checks_persisted_status_and_returns_contract(approval):
    db, pedido, client = approval
    response = AprovacaoService.homologar_entrega(
        pedido.id, StatusPedidoEnum.HOMOLOGACAO, str(client.id), db=db,
        versao_entregavel="v1", declaracao_aceite="Aceito.",
    )
    assert response["pedido_id"] == pedido.id
    assert response["status_final"] == "CONCLUIDO"
    assert response["percentual_progresso"] == 100.0


def test_approval_rejects_stale_status(approval):
    db, _, _ = approval
    with pytest.raises(ValueError, match="diverge"):
        register(approval, status_esperado=StatusPedidoEnum.EXECUCAO)
    db.add.assert_not_called()
    db.rollback.assert_called_once()


def test_repeated_approval_does_not_create_a_second_acceptance(approval):
    db, _, _ = approval
    register(approval)
    db.reset_mock()
    with pytest.raises(ValueError, match="HOMOLOGACAO"):
        register(approval)
    db.add.assert_not_called()
    db.commit.assert_not_called()

"""Real independent PostgreSQL transactions; never run against shared data."""
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.orm import Session
from sqlalchemy import func, select, text

from app.core.exceptions import TransicaoEstadoInvalidaException
from app.domain.models import Pedido, User, AuditoriaLog, AceiteFormal
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum as Status
from app.schemas.pedido import PedidoUpdate
from app.services.demand_service import DemandService
from app.services.pedido_service import PedidoService


@pytest.fixture
def committed_order(engine):
    # This suite needs commits visible to independent connections. Its database
    # is disposable; records intentionally remain until container destruction.
    with Session(engine, expire_on_commit=False) as db:
        admin = User(id=uuid4(), nome="Audit Admin", email=f"{uuid4()}@test.invalid",
                     senha_hash="unused", perfil=PerfilEnum.ADMIN, ativo=True)
        client = User(id=uuid4(), nome="Audit Client", email=f"{uuid4()}@test.invalid",
                      senha_hash="unused", perfil=PerfilEnum.CLIENTE, ativo=True)
        db.add_all([admin, client])
        db.commit()
        order = DemandService(db).criar(client, titulo="Concurrency audit", descricao="Isolated transactions")
        return admin.id, client.id, order.id


def test_legacy_update_revalidates_state_loaded_before_another_commit(engine, committed_order):
    admin_id, _, order_id = committed_order
    with Session(engine, expire_on_commit=False) as stale, Session(engine) as other:
        legacy = PedidoService(stale)
        cached = legacy.buscar_por_id(order_id)
        admin = other.get(User, admin_id)
        prepare_homologation(other, admin, order_id)
        assert cached.status == Status.PLANEAMENTO
        # Previously the stale identity map allowed HOMOLOGACAO -> EXECUCAO,
        # skipping the client's rejection and its mandatory reason.
        with pytest.raises(TransicaoEstadoInvalidaException):
            legacy.atualizar(order_id, PedidoUpdate(status=Status.EXECUCAO), usuario_id=admin_id)
    with Session(engine) as check:
        assert check.get(Pedido, order_id).status == Status.HOMOLOGACAO


def prepare_homologation(db, user, order_id):
    service = DemandService(db)
    stage = service.adicionar_etapa(user, order_id, descricao="Concurrent delivery checklist")
    stage_id = stage.id
    service.alterar_status(user, order_id, Status.EXECUCAO)
    service.concluir_etapa(user, order_id, stage_id)
    service.alterar_status(user, order_id, Status.HOMOLOGACAO)


def run_simultaneously(engine, user_id, operations):
    barrier = Barrier(len(operations))

    def worker(operation):
        with Session(engine) as db:
            # Service commits return connections to the pool. Keep deadlines
            # transaction-local so later migration/CREATE DATABASE tests do not
            # inherit a worker's short timeout.
            db.execute(text("SET LOCAL lock_timeout='5s'"))
            db.execute(text("SET LOCAL statement_timeout='10s'"))
            user = db.get(User, user_id)
            service = DemandService(db)
            barrier.wait(timeout=10)
            try:
                operation(service, user)
                return "ok"
            except Exception as exc:
                db.rollback()
                return type(exc).__name__

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        return list(pool.map(worker, operations))


def test_two_simultaneous_status_changes_commit_once(engine, committed_order):
    admin_id, _, order_id = committed_order
    def advance(service, user):
        service.alterar_status(user, order_id, Status.EXECUCAO)
    result = run_simultaneously(engine, admin_id, [advance, advance])
    assert sorted(result) == ["TransicaoEstadoInvalidaException", "ok"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditoriaLog).where(
            AuditoriaLog.pedido_id == order_id, AuditoriaLog.acao == "ALTERACAO_ESTADO",
        )) == 1


def test_two_simultaneous_stage_completions_commit_once(engine, committed_order):
    admin_id, _, order_id = committed_order
    with Session(engine) as db:
        user = db.get(User, admin_id)
        service = DemandService(db)
        stage = service.adicionar_etapa(user, order_id, descricao="Concurrent stage")
        stage_id = stage.id
        service.alterar_status(user, order_id, Status.EXECUCAO)
    def complete(service, user):
        service.concluir_etapa(user, order_id, stage_id)
    assert sorted(run_simultaneously(engine, admin_id, [complete, complete])) == [
        "TransicaoEstadoInvalidaException", "ok",
    ]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditoriaLog).where(
            AuditoriaLog.pedido_id == order_id, AuditoriaLog.acao == "CONCLUSAO_ETAPA",
        )) == 1


def test_simultaneous_acceptances_persist_one_evidence(engine, committed_order):
    admin_id, client_id, order_id = committed_order
    with Session(engine) as db:
        user = db.get(User, admin_id)
        prepare_homologation(db, user, order_id)
    def accept(service, user):
        service.aprovar_homologacao(user, order_id, versao_entregavel="v1",
                                   declaracao_aceite="Aceito a entrega verificada.")
    result = run_simultaneously(engine, client_id, [accept, accept])
    assert result.count("ok") == 1
    assert set(result) <= {"ok", "RegistroImutavelException", "TransicaoEstadoInvalidaException"}
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AceiteFormal).where(AceiteFormal.pedido_id == order_id)) == 1
        assert db.get(Pedido, order_id).status == Status.CONCLUIDO


def test_concurrent_assignment_retains_both_audited_changes(engine, committed_order):
    admin_id, _, order_id = committed_order
    with Session(engine) as db:
        techs = [User(id=uuid4(), nome="Technical audit", email=f"{uuid4()}@test.invalid",
                      senha_hash="unused", perfil=PerfilEnum.TECNICO, ativo=True) for _ in range(2)]
        db.add_all(techs)
        db.commit()
        ids = [t.id for t in techs]
    # Whichever runs second is a reassignment, which requires a reason (SCRUM-97).
    operations = [lambda service, user, target=target: service.atribuir_responsavel(
        user, order_id, responsavel_id=target, motivo="Redistribuicao da carga da equipe",
    ) for target in ids]
    assert run_simultaneously(engine, admin_id, operations) == ["ok", "ok"]
    with Session(engine) as db:
        logs = list(db.scalars(select(AuditoriaLog).where(
            AuditoriaLog.pedido_id == order_id, AuditoriaLog.acao == "ATRIBUICAO_RESPONSAVEL",
        )))
        assert len(logs) == 2
        first = next(log for log in logs if log.detalhes["responsavel_anterior"] is None)
        second = next(log for log in logs if log is not first)
        assert second.detalhes["responsavel_anterior"] == first.detalhes["responsavel_novo"]
        assert str(db.get(Pedido, order_id).responsavel_id) == second.detalhes["responsavel_novo"]


def test_two_techs_can_claim_a_demand_only_once(engine, committed_order):
    admin_id, _, order_id = committed_order
    ids = [uuid4(), uuid4()]
    with Session(engine) as db:
        db.add_all([
            User(id=tech_id, nome="Queue technician", email=f"{tech_id}@test.invalid",
                 senha_hash="unused", perfil=PerfilEnum.TECNICO, ativo=True)
            for tech_id in ids
        ])
        db.commit()

    operations = [
        lambda service, _, tech_id=tech_id: service.assumir_demanda(
            service.db.get(User, tech_id), order_id
        )
        for tech_id in ids
    ]
    assert sorted(run_simultaneously(engine, admin_id, operations)) == [
        "OperacaoConflitanteException", "ok",
    ]
    with Session(engine) as db:
        registro = db.execute(select(AuditoriaLog).where(
            AuditoriaLog.pedido_id == order_id, AuditoriaLog.acao == "ATRIBUICAO_RESPONSAVEL",
        )).scalar_one()
        assert db.get(Pedido, order_id).responsavel_id in ids
        assert registro.usuario_id == db.get(Pedido, order_id).responsavel_id


def test_rollback_releases_order_and_discards_stage(engine, committed_order, monkeypatch):
    admin_id, _, order_id = committed_order
    with Session(engine) as db:
        service = DemandService(db)
        user = db.get(User, admin_id)
        def fail(*args, **kwargs):
            raise RuntimeError("isolated failure")
        monkeypatch.setattr(service, "_auditar", fail)
        with pytest.raises(RuntimeError):
            service.adicionar_etapa(user, order_id, descricao="Rolled back stage")
    with Session(engine) as db:
        service = DemandService(db)
        user = db.get(User, admin_id)
        assert not service.listar_etapas(user, order_id)
        service.alterar_status(user, order_id, Status.EXECUCAO)

"""Local disposable HML dataset. Default dry-run, credentials from environment."""
import argparse
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import create_database_engine
from app.domain.models import AceiteFormal, Pedido, User
from app.domain.models.enums import PerfilEnum, StatusPedidoEnum as Status
from app.repositories.pedido_repository import PedidoRepository
from app.services.demand_service import DemandService
from scripts.isolated_database import require_isolated_database
from scripts.seed_demo_environment import DemoEnvironmentSettings, DemoSeedConflictError, seed_demo_environment

ACCEPTED_CODE = "HML-SEED-ACEITE"
PENDING_STAGE = "[HML] Validar entrega pendente"
ACCEPTED_STAGE = "[HML] Validar entrega aprovada"


def build_dataset(db, demo):
    result = seed_demo_environment(db, demo)
    client = db.get(User, result.user_ids[PerfilEnum.CLIENTE])
    admin = db.get(User, result.user_ids[PerfilEnum.ADMIN])
    technician = db.get(User, result.user_ids[PerfilEnum.TECNICO])
    service = DemandService(db)
    pending = db.get(Pedido, result.pedido_id)
    stages = service.listar_etapas(admin, pending.id)
    if not any(stage.descricao == PENDING_STAGE for stage in stages):
        service.adicionar_etapa(admin, pending.id, descricao=PENDING_STAGE)
    accepted = PedidoRepository(db).get_by_codigo(ACCEPTED_CODE)
    if accepted is not None:
        acceptance = db.scalar(select(AceiteFormal).where(AceiteFormal.pedido_id == accepted.id))
        if (accepted.cliente_id != client.id or accepted.responsavel_id != technician.id
                or accepted.status != Status.CONCLUIDO or acceptance is None):
            raise DemoSeedConflictError("Pedido HML existente incompativel; dados preservados.")
        return result
    accepted = PedidoRepository(db).create({
        "codigo_identificador": ACCEPTED_CODE, "titulo": "[HML] Entrega aprovada",
        "descricao": "Massa sintetica para validar aceite e restauracao.",
        "cliente_id": client.id, "status": Status.PLANEAMENTO,
    })
    service._auditar(admin, accepted, "HML_SEED_CRIACAO", {"synthetic": True})
    db.commit()
    service.atribuir_responsavel(admin, accepted.id, responsavel_id=technician.id)
    stage = service.adicionar_etapa(technician, accepted.id, descricao=ACCEPTED_STAGE)
    stage_id = stage.id
    service.alterar_status(technician, accepted.id, Status.EXECUCAO)
    service.concluir_etapa(technician, accepted.id, stage_id)
    service.alterar_status(technician, accepted.id, Status.HOMOLOGACAO)
    service.aprovar_homologacao(client, accepted.id, versao_entregavel="hml-v1",
                              declaracao_aceite="Aceito a entrega sintetica de homologacao.")
    return result


def seed_isolated(engine, demo, *, apply=False):
    require_isolated_database(engine.url.render_as_string(hide_password=False))
    # Every service commit releases only a savepoint. Any later failure, or
    # default dry-run, rolls back users, orders, stages and acceptance together.
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                result = build_dataset(db, demo)
            if apply:
                transaction.commit()
            else:
                transaction.rollback()
            return result
        except Exception:
            transaction.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    engine = None
    try:
        target = require_isolated_database(os.environ.get("HML_DATABASE_URL", ""))
        demo = DemoEnvironmentSettings(_env_file=None)
        engine = create_database_engine(Settings(_env_file=None, DATABASE_URL=target))
        seed_isolated(engine, demo, apply=args.apply)
        print("Massa HML validada; " + ("persistida." if args.apply else "dry-run desfeito integralmente."))
        return 0
    except Exception:
        print("Massa HML nao concluida. Revise ambiente isolado, credenciais e conflitos.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

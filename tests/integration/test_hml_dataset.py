import secrets

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import AceiteFormal, AuditoriaLog, EtapaOperacional, Ocorrencia, Pedido, User
from scripts.seed_demo_environment import DemoEnvironmentSettings
from scripts.seed_hml_environment import seed_isolated
from app.services.demand_service import DemandService
from tests.integration.test_migration_upgrade import fresh_database, upgrade


def counts(engine):
    with Session(engine) as db:
        return tuple(db.scalar(select(func.count()).select_from(model)) for model in (
            User, Pedido, Ocorrencia, EtapaOperacional, AceiteFormal, AuditoriaLog,
        ))


def test_hml_dataset_has_atomic_dry_run_and_idempotent_apply(engine, monkeypatch):
    scratch = fresh_database(engine)
    try:
        upgrade(scratch, monkeypatch)
        demo = DemoEnvironmentSettings(_env_file=None, **{
            f"DEMO_{profile}_PASSWORD": SecretStr(secrets.token_urlsafe(18))
            for profile in ("ADMIN", "TECNICO", "CLIENTE")
        })
        empty = counts(scratch)
        seed_isolated(scratch, demo)
        assert counts(scratch) == empty
        first = seed_isolated(scratch, demo, apply=True)
        populated = counts(scratch)
        assert populated[:5] == (3, 2, 1, 2, 1)
        again = seed_isolated(scratch, demo, apply=True)
        assert first.user_ids == again.user_ids and first.pedido_id == again.pedido_id
        assert counts(scratch) == populated
    finally:
        scratch.dispose()


def test_hml_failure_rolls_back_even_after_service_commits(engine, monkeypatch):
    scratch = fresh_database(engine)
    try:
        upgrade(scratch, monkeypatch)
        demo = DemoEnvironmentSettings(_env_file=None, **{
            f"DEMO_{profile}_PASSWORD": SecretStr(secrets.token_urlsafe(18))
            for profile in ("ADMIN", "TECNICO", "CLIENTE")
        })
        def fail(*args, **kwargs):
            raise RuntimeError("synthetic late failure")
        monkeypatch.setattr(DemandService, "aprovar_homologacao", fail)
        with pytest.raises(RuntimeError):
            seed_isolated(scratch, demo, apply=True)
        assert counts(scratch) == (0, 0, 0, 0, 0, 0)
    finally:
        scratch.dispose()

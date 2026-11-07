"""Real PostgreSQL commits and the actual upload adapter over a simulated SDK."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.storage.reconciliation import ObjectEvidence, classify_objects
from app.infrastructure.storage.supabase_storage import SupabaseStorage, StorageUploadError
from app.domain.models import User
from app.domain.models.enums import PerfilEnum
from app.services.anexo_service import AnexoService
from app.services.demand_service import DemandService
from tests import amostras
from tests.integration.test_migration_upgrade import fresh_database, upgrade


@pytest.fixture
def upload_case(engine, monkeypatch):
    # Independent commits must not contaminate tests that count all attachments.
    database = fresh_database(engine)
    upgrade(database, monkeypatch)
    try:
        with Session(database) as db:
            user = User(id=uuid4(), nome="Synthetic", email=f"{uuid4()}@test.invalid",
                        senha_hash="unused", perfil=PerfilEnum.CLIENTE, ativo=True)
            db.add(user)
            db.commit()
            order = DemandService(db).criar(user, titulo="Isolated upload", descricao="Synthetic concurrent upload")
            yield database, user.id, order.id
    finally:
        database.dispose()


class PausedBucket:
    def __init__(self, failure):
        self.failure = failure
        self.uploaded, self.resume = Event(), Event()
        self.obj = None
        self.removes = 0

    def upload(self, *, path, file, file_options):
        assert file_options["upsert"] == "false"
        now = datetime.now(timezone.utc)
        self.obj = ObjectEvidence(path, now, now, uuid4())
        self.uploaded.set()
        assert self.resume.wait(10)
        if self.failure:
            raise TimeoutError("synthetic uncertain upload acknowledgement")

    def remove(self, paths):
        self.removes += 1
        assert paths == [self.obj.path]
        if self.failure == "timeout-and-compensation-failure":
            raise ConnectionError("synthetic compensation outage")
        self.obj = None


class SimulatedClient:
    def __init__(self, bucket):
        self.storage = self
        self.bucket = bucket

    def from_(self, name):
        assert name == "synthetic-private"
        return self.bucket


@pytest.mark.parametrize("failure", [None, "upload-timeout", "timeout-and-compensation-failure"],
                         ids=["successful-concurrent-commit", "acknowledgement-lost", "compensation-unavailable"])
def test_inflight_upload_and_uncertain_outcomes_never_authorize_cleanup(upload_case, failure):
    engine, user_id, order_id = upload_case
    bucket = PausedBucket(failure)
    adapter = SupabaseStorage(client=SimulatedClient(bucket), bucket="synthetic-private")

    def writer():
        with Session(engine) as db:
            attachment = AnexoService(db, storage=adapter).criar(
                pedido_id=order_id, enviado_por_id=user_id, nome_arquivo="synthetic.png",
                conteudo=amostras.png(), content_type="image/png")
            return attachment.caminho_storage

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer)
        try:
            assert bucket.uploaded.wait(10)
            obj = bucket.obj
            with engine.connect() as c:
                c.exec_driver_sql("SET TRANSACTION READ ONLY")
                assert c.execute(text("SELECT count(*) FROM public.anexos WHERE caminho_storage=:path"),
                                 {"path":obj.path}).scalar_one() == 0
            finding = classify_objects([obj], set(), {order_id}, complete=True)[0]
            assert finding["reason"] == "recent_or_inflight" and finding["delete"] is False
        finally:
            bucket.resume.set()
        if failure:
            with pytest.raises(StorageUploadError) as exc:
                future.result(timeout=10)
            assert exc.value.compensacao_pendente is (failure == "timeout-and-compensation-failure")
        else:
            assert future.result(timeout=10) == obj.path

    with engine.connect() as c:
        refs = set(c.execute(text("SELECT caminho_storage FROM public.anexos WHERE caminho_storage=:path"),
                             {"path":obj.path}).scalars())
    if failure is None:
        assert refs == {obj.path} and bucket.removes == 0
        # Reusing this path for a different object cannot override a DB reference.
        replacement = replace(obj, storage_id=uuid4(), updated_at=datetime.now(timezone.utc))
        finding = classify_objects([replacement], refs, {order_id}, complete=True)[0]
        assert finding["reason"] == "referenced" and finding["delete"] is False
    else:
        assert not refs and bucket.removes == 1
        if failure == "timeout-and-compensation-failure":
            assert bucket.obj is not None
            old = datetime.now(timezone.utc)-timedelta(days=3)
            finding = classify_objects([replace(obj, created_at=old, updated_at=old)], set(), {order_id}, complete=True)[0]
            assert finding["reason"] == "existing_order_requires_review" and finding["delete"] is False
        else:
            assert bucket.obj is None

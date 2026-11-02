"""PostgreSQL FK/commit behavior with an isolated in-memory Storage provider."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from unittest.mock import Mock

from app.domain.models import Anexo, AuditoriaLog
from app.services.anexo_service import AnexoService
from tests import amostras
from tests.integration.test_demand_service_db import atores, demanda, service  # noqa: F401


@pytest.mark.parametrize("missing", ["pedido_id", "enviado_por_id"])
def test_postgres_fk_failure_compensates_successful_storage_upload(db, storage, atores, demanda, monkeypatch, missing):
    upload = Mock(wraps=storage.upload)
    delete = Mock(wraps=storage.delete)
    monkeypatch.setattr(storage, "upload", upload)
    monkeypatch.setattr(storage, "delete", delete)
    references = {"pedido_id": demanda.id, "enviado_por_id": atores["cliente"].id}
    references[missing] = uuid4()
    with pytest.raises(IntegrityError) as error:
        AnexoService(db, storage=storage).criar(
            **references, nome_arquivo="evidence.png", conteudo=amostras.png(), content_type="image/png",
        )
    assert error.value.orig.pgcode == "23503"
    assert upload.call_count == 1 and delete.call_count == 1
    assert not storage.arquivos
    assert db.scalar(select(func.count()).select_from(Anexo)) == 0
    assert db.is_active


def test_post_commit_refresh_failure_keeps_postgres_metadata_and_storage_object(db, storage, atores, demanda, monkeypatch):
    original_refresh = db.refresh
    attachment_refreshes = 0

    def refresh(instance, *args, **kwargs):
        nonlocal attachment_refreshes
        if isinstance(instance, Anexo):
            attachment_refreshes += 1
            if attachment_refreshes == 2:
                raise RuntimeError("synthetic refresh failure after commit")
        return original_refresh(instance, *args, **kwargs)

    monkeypatch.setattr(db, "refresh", refresh)
    with pytest.raises(RuntimeError, match="after commit"):
        AnexoService(db, storage=storage).criar(
            pedido_id=demanda.id, enviado_por_id=atores["cliente"].id,
            nome_arquivo="evidence.png", conteudo=amostras.png(), content_type="image/png",
        )
    attachments = list(db.scalars(select(Anexo)))
    assert len(attachments) == 1
    assert attachments[0].caminho_storage in storage.arquivos
    assert db.scalar(select(func.count()).select_from(AuditoriaLog).where(
        AuditoriaLog.acao == "ENVIO_EVIDENCIA",
    )) == 1
    assert db.is_active


def test_storage_failure_does_not_leave_postgres_metadata(db, storage, atores, demanda, monkeypatch):
    monkeypatch.setattr(storage, "upload", Mock(side_effect=RuntimeError("synthetic provider failure")))
    with pytest.raises(RuntimeError, match="provider failure"):
        AnexoService(db, storage=storage).criar(
            pedido_id=demanda.id, enviado_por_id=atores["cliente"].id,
            nome_arquivo="evidence.png", conteudo=amostras.png(), content_type="image/png",
        )
    assert db.scalar(select(func.count()).select_from(Anexo)) == 0
    assert not storage.arquivos
    assert db.is_active

"""SCRUM-87 constraints and compensation against the guarded disposable DB."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.models import Anexo, AuditoriaLog, Ocorrencia, Pedido
from app.domain.models.enums import TipoOcorrenciaEnum
from app.infrastructure.storage.supabase_storage import StorageDeleteError
from app.services.anexo_service import AnexoCompensacaoError, AnexoService
from tests import amostras
from tests.integration.test_concurrency_postgres import committed_order  # noqa: F401
from tests.integration.test_demand_service_db import atores, demanda, service  # noqa: F401


def occurrence(db, atores, demanda):
    row = Ocorrencia(id=uuid4(), pedido_id=demanda.id, autor_id=atores["cliente"].id,
                     tipo=TipoOcorrenciaEnum.ERRO, descricao="Synthetic occurrence")
    db.add(row)
    db.flush()
    return row


def attachment(db, atores, demanda, row):
    item = Anexo(id=uuid4(), pedido_id=demanda.id, ocorrencia_id=row.id,
                 enviado_por_id=atores["cliente"].id, nome_arquivo="synthetic.pdf",
                 caminho_storage=f"pedidos/{demanda.id}/{uuid4()}.pdf", extensao="pdf", tamanho_bytes=1)
    db.add(item)
    db.flush()
    return item


@pytest.mark.parametrize("operation", ["insert", "attachment-update", "occurrence-update"])
def test_database_rejects_cross_order_occurrence_pairs(db, atores, demanda, service, operation):
    row = occurrence(db, atores, demanda)
    item = attachment(db, atores, demanda, row)
    other = service.criar(atores["cliente"], titulo="Other order", descricao="Synthetic second order")
    with pytest.raises(IntegrityError) as error:
        with db.begin_nested():
            if operation == "insert":
                attachment(db, atores, other, row)
            elif operation == "attachment-update":
                db.execute(text("UPDATE public.anexos SET pedido_id=:other WHERE id=:id"),
                           {"other": other.id, "id": item.id})
            else:
                db.execute(text("UPDATE public.ocorrencias SET pedido_id=:other WHERE id=:id"),
                           {"other": other.id, "id": row.id})
            db.execute(text("SET CONSTRAINTS public.fk_anexos_ocorrencia_pedido IMMEDIATE"))
    assert error.value.orig.pgcode == "23503"
    assert db.is_active


def test_occurrence_delete_preserves_order_and_detaches_attachment(db, atores, demanda):
    row = occurrence(db, atores, demanda)
    item = attachment(db, atores, demanda, row)
    db.execute(text("DELETE FROM public.ocorrencias WHERE id=:id"), {"id": row.id})
    db.execute(text("SET CONSTRAINTS public.fk_anexos_ocorrencia_pedido IMMEDIATE"))
    db.expire(item)
    assert item.ocorrencia_id is None and item.pedido_id == demanda.id


def test_order_delete_cascades_metadata_without_touching_storage(db, atores, demanda):
    row = occurrence(db, atores, demanda)
    item = attachment(db, atores, demanda, row)
    item_id, occurrence_id = item.id, row.id
    db.execute(text("DELETE FROM public.pedidos WHERE id=:id"), {"id": demanda.id})
    db.execute(text("SET CONSTRAINTS public.fk_anexos_ocorrencia_pedido IMMEDIATE"))
    assert db.scalar(select(func.count()).select_from(Anexo).where(Anexo.id == item_id)) == 0
    assert db.scalar(select(func.count()).select_from(Ocorrencia).where(Ocorrencia.id == occurrence_id)) == 0


def test_bad_pair_cannot_commit_even_if_both_individual_foreign_keys_exist(engine, committed_order):
    _, client_id, order_id = committed_order
    other, occurrence_id, attachment_id = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO public.pedidos(id,codigo_identificador,titulo,cliente_id) "
                                "VALUES (:id,:code,'Second order',:client)"),
                           {"id": other, "code": f"FK-{uuid4().hex}", "client": client_id})
        connection.execute(text("INSERT INTO public.ocorrencias(id,pedido_id,autor_id,tipo,descricao) "
                                "VALUES (:id,:order,:client,'ERRO','Synthetic')"),
                           {"id": occurrence_id, "order": order_id, "client": client_id})
    with pytest.raises(IntegrityError) as error:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO public.anexos(id,pedido_id,ocorrencia_id,enviado_por_id,"
                                    "nome_arquivo,caminho_storage,extensao,tamanho_bytes) "
                                    "VALUES (:id,:order,:occurrence,:client,'test.pdf','synthetic','pdf',1)"),
                               {"id": attachment_id, "order": other, "occurrence": occurrence_id, "client": client_id})
    assert error.value.orig.pgcode == "23503"
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM public.anexos WHERE id=:id"),
                                  {"id": attachment_id}).scalar_one() == 0


def test_audit_failure_rolls_back_attachment_and_compensates_upload(db, atores, demanda, storage, monkeypatch):
    original_add = db.add
    def add(entity, *args, **kwargs):
        if isinstance(entity, AuditoriaLog):
            raise RuntimeError("synthetic audit failure")
        return original_add(entity, *args, **kwargs)
    monkeypatch.setattr(db, "add", add)
    with pytest.raises(RuntimeError, match="audit failure"):
        AnexoService(db, storage=storage).criar(
            pedido_id=demanda.id, enviado_por_id=atores["cliente"].id,
            nome_arquivo="test.png", conteudo=amostras.png(), content_type="image/png")
    assert not storage.arquivos
    assert db.scalar(select(func.count()).select_from(Anexo)) == 0
    assert db.is_active


def test_failed_compensation_is_explicit_with_real_database_rollback(db, atores, demanda, storage, monkeypatch):
    def fail(_path):
        raise StorageDeleteError("synthetic provider failure")
    monkeypatch.setattr(storage, "delete", fail)
    with pytest.raises(AnexoCompensacaoError) as error:
        AnexoService(db, storage=storage).criar(
            pedido_id=demanda.id, enviado_por_id=uuid4(), nome_arquivo="test.png",
            conteudo=amostras.png(), content_type="image/png")
    assert error.value.caminho_storage in storage.arquivos
    assert db.scalar(select(func.count()).select_from(Anexo)) == 0
    assert db.is_active

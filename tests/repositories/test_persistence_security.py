from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.exc import IntegrityError

from app.domain.models.anexo import Anexo
from app.domain.models.historico_status_pedido import HistoricoStatusPedido
from app.domain.models.ocorrencia import Ocorrencia
from app.domain.models.pedido import Pedido
from app.repositories.anexo_repository import (
    AnexoRepository, OcorrenciaDeOutroPedidoError, OcorrenciaNaoEncontradaError,
)
from app.repositories.base_repository import BaseRepository
from app.repositories.historico_status_pedido_repository import HistoricoStatusPedidoRepository
from app.repositories.pedido_repository import PedidoRepository
from app.repositories.user_repository import UserRepository
from app.services.anexo_service import AnexoService
from tests.attachment_samples import pdf


def test_clients_are_scoped_before_pagination_without_duplicates(persistence_db, ownership):
    repo = UserRepository(persistence_db)
    assert list(repo.list_clientes_por_responsavel(responsavel_id=ownership.t1.id)) == [ownership.c1]
    assert set(repo.list_clientes_por_responsavel(responsavel_id=ownership.t2.id)) == {ownership.c1, ownership.c2}
    assert repo.get_cliente_por_responsavel(ownership.c2.id, responsavel_id=ownership.t1.id) is None
    assert repo.get_cliente_por_responsavel(ownership.c1.id, responsavel_id=ownership.t1.id) is ownership.c1
    assert repo.get_cliente_por_responsavel(ownership.c3.id, responsavel_id=ownership.t1.id) is None
    assert repo.get_cliente_por_responsavel(uuid4(), responsavel_id=ownership.t1.id) is None
    assert len(repo.list_clientes_por_responsavel(responsavel_id=ownership.t2.id, limit=1, offset=1)) == 1
    assert repo.list_clientes_por_responsavel(responsavel_id=ownership.admin.id) == []


def test_technician_listing_contains_no_clients_and_general_listing_is_disabled(persistence_db, ownership):
    repo = UserRepository(persistence_db)
    assert set(repo.list_tecnicos()) == {ownership.t1, ownership.t2}
    with pytest.raises(ValueError, match="específica"):
        repo.get_all()
    assert repo.get_cliente_proprio(usuario_id=ownership.c1.id) is ownership.c1
    assert repo.get_cliente_proprio(usuario_id=ownership.t1.id) is None


def test_pedidos_use_order_responsibility_even_for_shared_client(persistence_db, ownership):
    repo = PedidoRepository(persistence_db)
    p1, _, p2, shared, _ = ownership.pedidos
    assert repo.get_by_id_for_responsavel(p1.id, responsavel_id=ownership.t1.id) is p1
    assert repo.get_by_id_for_responsavel(p2.id, responsavel_id=ownership.t1.id) is None
    assert repo.get_by_id_for_responsavel(shared.id, responsavel_id=ownership.t1.id) is None
    assert repo.get_by_id_for_cliente(p1.id, cliente_id=ownership.c2.id) is None
    assert repo.get_by_id_for_cliente(p1.id, cliente_id=ownership.c1.id) is p1
    assert set(repo.get_by_cliente(ownership.c1.id)) == {ownership.pedidos[i] for i in (0, 1, 3)}
    assert set(repo.get_by_responsavel(ownership.t1.id)) == {ownership.pedidos[i] for i in (0, 1)}


@pytest.mark.parametrize("method,kwargs", [
    ("list_clientes_por_responsavel", {"responsavel_id": None}),
    ("list_clientes_por_responsavel", {"responsavel_id": "' OR 1=1 --"}),
    ("get_cliente_proprio", {"usuario_id": None}),
    ("list_tecnicos", {"limit": 0}),
    ("list_tecnicos", {"offset": -1}),
    ("list_tecnicos", {"limit": 101}),
])
def test_invalid_scope_never_reaches_database(method, kwargs):
    db = MagicMock()
    with pytest.raises(ValueError):
        getattr(UserRepository(db), method)(**kwargs)
    db.scalar.assert_not_called()
    db.scalars.assert_not_called()


@pytest.mark.parametrize("field", ["metadata", "registry", "__dict__", "_sa_instance_state", "missing"])
def test_mass_assignment_rejected_before_any_change(field):
    db = MagicMock()
    repo = BaseRepository(Pedido, db)
    pedido = Pedido(titulo="Original")
    with pytest.raises(ValueError):
        repo.update(pedido, {"titulo": "Changed", field: {}})
    assert pedido.titulo == "Original"
    with pytest.raises(ValueError):
        repo.create({field: {}})
    db.flush.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.parametrize("field", ["created_at", "updated_at"])
def test_server_managed_fields_cannot_be_mass_assigned_on_creation(field):
    with pytest.raises(ValueError):
        BaseRepository(Pedido, MagicMock()).create({field: uuid4()})


def test_service_generated_uuid_is_preserved_on_creation():
    identifier = uuid4()
    assert BaseRepository(Pedido, MagicMock()).create({"id": identifier}).id == identifier


def test_sensitive_user_fields_and_order_client_cannot_be_mass_assigned(ownership, persistence_db):
    for field in ("perfil", "ativo", "senha_hash"):
        with pytest.raises(ValueError):
            UserRepository(persistence_db).update(ownership.c1, {field: "new"})
    with pytest.raises(ValueError):
        PedidoRepository(persistence_db).update(ownership.pedidos[0], {"cliente_id": ownership.c2.id})


def test_query_values_are_bound_parameters():
    db = MagicMock()
    attack = "' OR 1=1 --"
    PedidoRepository(db).get_by_codigo(attack)
    compiled = db.scalar.call_args.args[0].compile(dialect=dialect())
    assert attack not in str(compiled)
    assert attack in compiled.params.values()


def test_occurrence_validation_locks_row_and_binds_ids():
    db = MagicMock()
    pedido_id, ocorrencia_id = uuid4(), uuid4()
    db.scalar.return_value = pedido_id
    AnexoRepository(db).validar_ocorrencia_do_pedido(pedido_id=pedido_id, ocorrencia_id=ocorrencia_id)
    compiled = db.scalar.call_args.args[0].compile(dialect=dialect())
    assert "FOR UPDATE" in str(compiled)
    assert ocorrencia_id in compiled.params.values()
    assert str(ocorrencia_id) not in str(compiled)
    db.commit.assert_not_called()


@pytest.mark.parametrize("relation", ["same", "other", "missing"])
def test_occurrence_checked_before_upload_with_real_repository(persistence_db, ownership, relation):
    pedido = ownership.pedidos[0]
    occurrence = Ocorrencia(id=uuid4(), pedido_id=(pedido.id if relation == "same" else ownership.pedidos[2].id),
                           autor_id=ownership.c1.id, tipo="ERRO", descricao="Evidência")
    if relation != "missing":
        persistence_db.add(occurrence)
        persistence_db.commit()
    storage = MagicMock()
    storage.upload.return_value = f"pedidos/{pedido.id}/{uuid4()}.pdf"
    service = AnexoService(persistence_db, storage=storage)
    kwargs = dict(pedido_id=pedido.id, enviado_por_id=ownership.c1.id, ocorrencia_id=occurrence.id,
                  nome_arquivo="evidence.pdf", conteudo=pdf(), content_type="application/octet-stream")
    if relation == "same":
        anexo = service.criar(**kwargs)
        assert anexo.ocorrencia_id == occurrence.id
        assert anexo.pedido_id == pedido.id
        assert storage.upload.call_args.kwargs["content_type"] == "application/pdf"
    else:
        error = OcorrenciaDeOutroPedidoError if relation == "other" else OcorrenciaNaoEncontradaError
        with pytest.raises(error):
            service.criar(**kwargs)
        storage.upload.assert_not_called()
        assert persistence_db.scalars(select(Anexo)).all() == []
    storage.delete.assert_not_called()


def test_fk_failure_rolls_back_metadata_and_compensates_upload(persistence_db, ownership):
    storage = MagicMock()
    storage.upload.return_value = f"pedidos/{ownership.pedidos[0].id}/{uuid4()}.pdf"
    with pytest.raises(IntegrityError):
        AnexoService(persistence_db, storage=storage).criar(
            pedido_id=ownership.pedidos[0].id, enviado_por_id=uuid4(),
            nome_arquivo="evidence.pdf", conteudo=pdf(), content_type="application/pdf",
        )
    assert persistence_db.scalars(select(Anexo)).all() == []
    storage.delete.assert_called_once_with(storage.upload.return_value)
    assert persistence_db.is_active


def test_history_fk_rollback_and_scoped_reads(persistence_db, ownership):
    repo = HistoricoStatusPedidoRepository(persistence_db)
    data = dict(pedido_id=ownership.pedidos[0].id, usuario_id=ownership.t1.id,
                status_anterior="PLANEAMENTO", status_novo="EXECUCAO")
    history = repo.create(data)
    assert repo.get_by_pedido_for_cliente(data["pedido_id"], cliente_id=ownership.c1.id) == [history]
    assert repo.get_by_pedido_for_cliente(data["pedido_id"], cliente_id=ownership.c2.id) == []
    assert repo.get_by_pedido_for_responsavel(data["pedido_id"], responsavel_id=ownership.t2.id) == []
    persistence_db.rollback()
    assert persistence_db.scalars(select(HistoricoStatusPedido)).all() == []
    data["usuario_id"] = uuid4()
    with pytest.raises(IntegrityError):
        repo.create(data)
    persistence_db.rollback()
    assert persistence_db.is_active


def test_anexo_scoped_reads_and_immutable_links(persistence_db, ownership):
    repo = AnexoRepository(persistence_db)
    anexo = repo.create(dict(pedido_id=ownership.pedidos[0].id, enviado_por_id=ownership.c1.id,
                            nome_arquivo="e.pdf", caminho_storage="internal", extensao="pdf", tamanho_bytes=1))
    pid = ownership.pedidos[0].id
    assert repo.get_by_pedido_for_cliente(pid, cliente_id=ownership.c1.id) == [anexo]
    assert repo.get_by_pedido_for_cliente(pid, cliente_id=ownership.c2.id) == []
    assert repo.get_by_pedido_for_responsavel(pid, responsavel_id=ownership.t1.id) == [anexo]
    assert repo.get_by_pedido_for_responsavel(pid, responsavel_id=ownership.t2.id) == []
    for field in ("pedido_id", "ocorrencia_id", "enviado_por_id", "caminho_storage"):
        with pytest.raises(ValueError):
            repo.update(anexo, {field: uuid4()})


@pytest.mark.parametrize("table,field", [
    ("pedido", "cliente_id"), ("pedido", "responsavel_id"),
    ("ocorrencia", "pedido_id"), ("ocorrencia", "autor_id"),
    ("anexo", "pedido_id"), ("anexo", "enviado_por_id"), ("anexo", "ocorrencia_id"),
    ("historico", "pedido_id"), ("historico", "usuario_id"),
])
def test_foreign_keys_reject_missing_references(persistence_db, ownership, table, field):
    models = {
        "pedido": Pedido,
        "ocorrencia": Ocorrencia,
        "anexo": Anexo,
        "historico": HistoricoStatusPedido,
    }
    values = {
        "pedido": dict(codigo_identificador="new", titulo="Pedido", cliente_id=ownership.c1.id),
        "ocorrencia": dict(pedido_id=ownership.pedidos[0].id, autor_id=ownership.c1.id,
                           tipo="ERRO", descricao="Detalhe"),
        "anexo": dict(pedido_id=ownership.pedidos[0].id, enviado_por_id=ownership.c1.id,
                      nome_arquivo="e.pdf", caminho_storage="internal", extensao="pdf", tamanho_bytes=1),
        "historico": dict(pedido_id=ownership.pedidos[0].id, usuario_id=ownership.t1.id,
                          status_anterior="PLANEAMENTO", status_novo="EXECUCAO"),
    }[table]
    values[field] = uuid4()
    persistence_db.add(models[table](**values))
    with pytest.raises(IntegrityError):
        persistence_db.flush()
    persistence_db.rollback()
    assert persistence_db.is_active


def test_cascades_and_set_null_preserve_attachment_metadata(persistence_db, ownership):
    pid, uid = ownership.pedidos[0].id, ownership.c1.id
    occurrence = Ocorrencia(id=uuid4(), pedido_id=pid, autor_id=uid, tipo="ERRO", descricao="Detalhe")
    persistence_db.add(occurrence)
    persistence_db.flush()
    anexo = AnexoRepository(persistence_db).create(dict(
        pedido_id=pid, ocorrencia_id=occurrence.id, enviado_por_id=uid,
        nome_arquivo="e.pdf", caminho_storage="internal", extensao="pdf", tamanho_bytes=1,
    ))
    history = HistoricoStatusPedidoRepository(persistence_db).create(dict(
        pedido_id=pid, usuario_id=uid, status_anterior="PLANEAMENTO", status_novo="EXECUCAO",
    ))
    persistence_db.commit()
    aid, hid = anexo.id, history.id
    persistence_db.delete(occurrence)
    persistence_db.commit()
    assert persistence_db.get(Anexo, aid).ocorrencia_id is None
    persistence_db.delete(ownership.pedidos[0])
    persistence_db.commit()
    persistence_db.expire_all()
    assert persistence_db.scalar(select(Anexo).where(Anexo.id == aid)) is None
    assert persistence_db.scalar(select(HistoricoStatusPedido).where(HistoricoStatusPedido.id == hid)) is None


def test_repository_flush_is_reversible_without_implicit_commit(persistence_db, ownership):
    repo = PedidoRepository(persistence_db)
    pedido = repo.create(dict(codigo_identificador="reversible", titulo="Pedido", cliente_id=ownership.c1.id))
    pid = pedido.id
    persistence_db.rollback()
    assert persistence_db.get(Pedido, pid) is None


@pytest.mark.parametrize("value", [None, "../path", "' OR 1=1 --", "not-a-uuid"])
def test_invalid_identifiers_are_rejected_without_database_access(value):
    db = MagicMock()
    repo = PedidoRepository(db)
    with pytest.raises(ValueError):
        repo.get_by_id(value)
    if value is not None:
        with pytest.raises(ValueError):
            repo.create({"cliente_id": value, "titulo": "Pedido", "codigo_identificador": "id"})
    db.get.assert_not_called()
    db.add.assert_not_called()

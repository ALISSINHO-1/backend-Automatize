from unittest.mock import MagicMock
from uuid import uuid4

import pytest # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.anexo import Anexo
from app.infrastructure.storage.supabase_storage import SupabaseStorage
from app.repositories.anexo_repository import AnexoRepository
from app.services.anexo_service import (
    AnexoNaoEncontradoError,
    AnexoService,
    ArquivoInvalidoError,
)


@pytest.fixture
def db_session() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def repository() -> MagicMock:
    return MagicMock(spec=AnexoRepository)


@pytest.fixture
def storage() -> MagicMock:
    return MagicMock(spec=SupabaseStorage)


@pytest.fixture
def service(
    db_session: MagicMock,
    repository: MagicMock,
    storage: MagicMock,
) -> AnexoService:
    return AnexoService(
        db=db_session,
        repository=repository,
        storage=storage,
    )


def criar_anexo() -> Anexo:
    return Anexo(
        id=uuid4(),
        pedido_id=uuid4(),
        enviado_por_id=uuid4(),
        nome_arquivo="evidencia.pdf",
        caminho_storage="pedidos/teste/evidencia.pdf",
        extensao="pdf",
        tamanho_bytes=100,
    )


def test_listar_por_pedido(
    service: AnexoService,
    repository: MagicMock,
) -> None:
    pedido_id = uuid4()
    anexos = [criar_anexo(), criar_anexo()]

    repository.get_by_pedido.return_value = anexos

    resultado = service.listar_por_pedido(pedido_id)

    assert resultado == anexos
    repository.get_by_pedido.assert_called_once_with(pedido_id)


def test_buscar_por_id(
    service: AnexoService,
    repository: MagicMock,
) -> None:
    anexo = criar_anexo()
    repository.get_by_id.return_value = anexo

    resultado = service.buscar_por_id(anexo.id)

    assert resultado is anexo
    repository.get_by_id.assert_called_once_with(anexo.id)


def test_buscar_por_id_inexistente(
    service: AnexoService,
    repository: MagicMock,
) -> None:
    anexo_id = uuid4()
    repository.get_by_id.return_value = None

    with pytest.raises(
        AnexoNaoEncontradoError,
        match="não encontrado",
    ):
        service.buscar_por_id(anexo_id)


def test_criar_anexo_faz_upload_e_commit(
    service: AnexoService,
    repository: MagicMock,
    storage: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido_id = uuid4()
    usuario_id = uuid4()

    conteudo = b"arquivo de teste"

    storage.upload.return_value = (
        f"pedidos/{pedido_id}/arquivo.pdf"
    )

    anexo = criar_anexo()
    repository.create.return_value = anexo

    resultado = service.criar(
        pedido_id=pedido_id,
        enviado_por_id=usuario_id,
        nome_arquivo="arquivo.pdf",
        conteudo=conteudo,
        content_type="application/pdf",
    )

    assert resultado is anexo

    storage.upload.assert_called_once_with(
        pedido_id=pedido_id,
        nome_arquivo="arquivo.pdf",
        conteudo=conteudo,
        content_type="application/pdf",
    )

    repository.create.assert_called_once()

    db_session.commit.assert_called_once()
    db_session.refresh.assert_called_once_with(anexo)
    db_session.rollback.assert_not_called()


def test_criar_rejeita_extensao_invalida(
    service: AnexoService,
    repository: MagicMock,
    storage: MagicMock,
) -> None:
    with pytest.raises(
        ArquivoInvalidoError,
        match="não permitida",
    ):
        service.criar(
            pedido_id=uuid4(),
            enviado_por_id=uuid4(),
            nome_arquivo="programa.exe",
            conteudo=b"teste",
            content_type="application/octet-stream",
        )

    storage.upload.assert_not_called()
    repository.create.assert_not_called()


def test_criar_rejeita_arquivo_vazio(
    service: AnexoService,
    repository: MagicMock,
    storage: MagicMock,
) -> None:
    with pytest.raises(
        ArquivoInvalidoError,
        match="vazio",
    ):
        service.criar(
            pedido_id=uuid4(),
            enviado_por_id=uuid4(),
            nome_arquivo="arquivo.pdf",
            conteudo=b"",
            content_type="application/pdf",
        )

    storage.upload.assert_not_called()
    repository.create.assert_not_called()


def test_criar_rejeita_arquivo_maior_que_limite(
    service: AnexoService,
    storage: MagicMock,
) -> None:
    conteudo = b"x" * (
        AnexoService.TAMANHO_MAXIMO_BYTES + 1
    )

    with pytest.raises(
        ArquivoInvalidoError,
        match="10 MB",
    ):
        service.criar(
            pedido_id=uuid4(),
            enviado_por_id=uuid4(),
            nome_arquivo="arquivo.pdf",
            conteudo=conteudo,
            content_type="application/pdf",
        )

    storage.upload.assert_not_called()


def test_criar_faz_rollback_e_remove_storage_se_banco_falhar(
    service: AnexoService,
    repository: MagicMock,
    storage: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido_id = uuid4()

    caminho = f"pedidos/{pedido_id}/arquivo.pdf"

    storage.upload.return_value = caminho
    repository.create.side_effect = RuntimeError(
        "Erro no banco"
    )

    with pytest.raises(
        RuntimeError,
        match="Erro no banco",
    ):
        service.criar(
            pedido_id=pedido_id,
            enviado_por_id=uuid4(),
            nome_arquivo="arquivo.pdf",
            conteudo=b"teste",
            content_type="application/pdf",
        )

    db_session.commit.assert_not_called()
    db_session.rollback.assert_called_once()
    storage.delete.assert_called_once_with(caminho)


def test_refresh_failure_after_commit_keeps_storage_object(service, repository, storage, db_session):
    repository.create.return_value = criar_anexo()
    db_session.refresh.side_effect = RuntimeError("refresh failed")
    with pytest.raises(RuntimeError, match="refresh failed"):
        service.criar(
            pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo="arquivo.pdf",
            conteudo=b"teste", content_type="application/pdf",
        )
    db_session.commit.assert_called_once()
    db_session.rollback.assert_not_called()
    storage.delete.assert_not_called()


def test_commit_failure_rolls_back_and_removes_uploaded_object(service, repository, storage, db_session):
    repository.create.return_value = criar_anexo()
    storage.upload.return_value = "pedidos/teste/arquivo.pdf"
    db_session.commit.side_effect = RuntimeError("commit failed")
    with pytest.raises(RuntimeError, match="commit failed"):
        service.criar(
            pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo="arquivo.pdf",
            conteudo=b"teste", content_type="application/pdf",
        )
    db_session.rollback.assert_called_once()
    storage.delete.assert_called_once_with("pedidos/teste/arquivo.pdf")

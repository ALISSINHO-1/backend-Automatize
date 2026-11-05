from unittest.mock import MagicMock
from uuid import uuid4

import pytest # type: ignore
from sqlalchemy.orm import Session # type: ignore

from app.domain.models.anexo import Anexo
from app.infrastructure.storage.supabase_storage import SupabaseStorage
from app.repositories.anexo_repository import AnexoRepository
from tests import amostras
from app.services.anexo_service import (
    AnexoNaoEncontradoError,
    AnexoService,
    ArquivoInvalidoError,
)
from tests.attachment_samples import pdf
from tests import attachment_samples


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

    conteudo = pdf()

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
            conteudo=pdf(),
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
            conteudo=pdf(),
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
            conteudo=pdf(), content_type="application/pdf",
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
            conteudo=pdf(), content_type="application/pdf",
        )
    db_session.rollback.assert_called_once()
    storage.delete.assert_called_once_with("pedidos/teste/arquivo.pdf")


def test_storage_failure_rolls_back_without_creating_metadata(service, repository, storage, db_session):
    from app.infrastructure.storage.supabase_storage import StorageUploadError
    storage.upload.side_effect = StorageUploadError("upload failed", caminho_storage="generated")
    with pytest.raises(StorageUploadError):
        service.criar(pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo="e.pdf",
                      conteudo=pdf(), content_type="application/pdf")
    repository.create.assert_not_called()
    db_session.commit.assert_not_called()
    db_session.rollback.assert_called_once()
    storage.delete.assert_not_called()


@pytest.mark.parametrize("rollback_fails", [False, True])
def test_compensation_runs_even_when_rollback_fails(service, repository, storage, db_session, rollback_fails):
    repository.create.side_effect = RuntimeError("database failed")
    storage.upload.return_value = "generated"
    if rollback_fails:
        db_session.rollback.side_effect = RuntimeError("rollback failed")
    with pytest.raises(RuntimeError):
        service.criar(pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo="e.pdf",
                      conteudo=pdf(), content_type="application/pdf")
    storage.delete.assert_called_once_with("generated")


def test_failed_compensation_is_explicit_and_retains_cleanup_path(service, repository, storage, db_session):
    from app.infrastructure.storage.supabase_storage import StorageDeleteError
    from app.services.anexo_service import AnexoCompensacaoError
    repository.create.side_effect = RuntimeError("database private detail")
    storage.upload.return_value = "generated"
    storage.delete.side_effect = StorageDeleteError("provider private detail")
    with pytest.raises(AnexoCompensacaoError) as error:
        service.criar(pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo="e.pdf",
                      conteudo=pdf(), content_type="application/pdf")
    assert error.value.caminho_storage == "generated"
    assert "private detail" not in str(error.value)
    assert error.value.__suppress_context__
    db_session.rollback.assert_called_once()


@pytest.mark.parametrize("name,data", [
    ("fake.pdf", b"<html>fake</html>"), ("wrong.png", pdf()), ("empty.pdf", b""),
    ("../file.pdf", pdf()), ("..\\file.pdf", pdf()),
])
def test_invalid_file_never_reaches_storage_or_metadata(service, storage, repository, name, data):
    with pytest.raises(ArquivoInvalidoError):
        service.criar(pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo=name,
                      conteudo=data, content_type="application/pdf")
    repository.create.assert_not_called()
    storage.upload.assert_not_called()


def test_lost_commit_confirmation_preserves_object_for_reconciliation(service, storage, repository, db_session):
    from sqlalchemy.exc import OperationalError
    from app.services.anexo_service import AnexoCommitIncertoError
    storage.upload.return_value = "generated"
    db_session.commit.side_effect = OperationalError(None, None, ConnectionError("private detail"), connection_invalidated=True)
    with pytest.raises(AnexoCommitIncertoError) as error:
        service.criar(pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo="e.pdf",
                      conteudo=pdf(), content_type="application/pdf")
    assert error.value.caminho_storage == "generated"
    assert "private detail" not in str(error.value)
    db_session.rollback.assert_called_once()
    storage.delete.assert_not_called()


def test_criar_recusa_conteudo_que_nao_corresponde_a_extensao(
    service: AnexoService,
    repository: MagicMock,
    storage: MagicMock,
) -> None:
    with pytest.raises(ArquivoInvalidoError, match="Conteúdo incompatível"):
        service.criar(
            pedido_id=uuid4(),
            enviado_por_id=uuid4(),
            nome_arquivo="foto.png",
            conteudo=b"MZ\x90\x00 executavel renomeado",
            content_type="image/png",
        )

    storage.upload.assert_not_called()
    repository.create.assert_not_called()


def test_criar_usa_content_type_detectado_e_audita_envio(
    service: AnexoService,
    repository: MagicMock,
    storage: MagicMock,
    db_session: MagicMock,
) -> None:
    pedido_id = uuid4()
    usuario_id = uuid4()
    storage.upload.return_value = f"pedidos/{pedido_id}/foto.png"
    repository.create.return_value = criar_anexo()

    service.criar(
        pedido_id=pedido_id,
        enviado_por_id=usuario_id,
        nome_arquivo="foto.png",
        conteudo=amostras.png(),
        content_type="application/octet-stream",
    )

    upload = storage.upload.call_args.kwargs
    assert upload["content_type"] == "image/png"
    assert upload["nome_arquivo"] == "foto.png"
    auditoria = db_session.add.call_args.args[0]
    assert auditoria.acao == "ENVIO_EVIDENCIA"
    assert auditoria.usuario_id == usuario_id
    assert auditoria.pedido_id == pedido_id
    assert auditoria.detalhes["anexo_id"] == str(repository.create.return_value.id)
    assert auditoria.detalhes["nome_arquivo"] == "foto.png"
    assert auditoria.detalhes["tamanho_bytes"] == len(amostras.png())


@pytest.mark.parametrize("nome,conteudo,mime", [
    ("real.pdf", amostras.pdf(), "application/pdf"),
    ("real.PNG", amostras.png(), "image/png"),
    ("real.jpg", amostras.jpeg(), "image/jpeg"),
    ("real.jpeg", amostras.jpeg(), "image/jpeg"),
    ("real.docx", amostras.docx(),
     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("legado.doc", attachment_samples.word_ole(), "application/msword"),
], ids=lambda value: value if isinstance(value, str) else "conteudo")
def test_formatos_validos_preservados_na_integracao(
    service, repository, storage, db_session, nome, conteudo, mime,
):
    repository.create.return_value = criar_anexo()
    resultado = service.criar(
        pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo=nome,
        conteudo=conteudo,
    )
    assert resultado is repository.create.return_value
    assert storage.upload.call_args.kwargs["content_type"] == mime
    dados = repository.create.call_args.args[0]
    assert dados["extensao"] == nome.rsplit(".", 1)[1].lower()
    assert dados["tamanho_bytes"] == len(conteudo)
    assert db_session.add.call_args.args[0].acao == "ENVIO_EVIDENCIA"
    db_session.commit.assert_called_once()


@pytest.mark.parametrize("nome,conteudo,mime", [
    ("falso.pdf", b"%PDF-1.4\n<html>falso</html>\n%%EOF", "application/pdf"),
    ("truncado.pdf", pdf()[:-20], "application/pdf"),
    ("falso.png", b"\x89PNG\r\n\x1a\n" + b"fake" * 20, "image/png"),
    ("truncado.png", amostras.png()[:-15], "image/png"),
    ("falso.jpg", b"\xff\xd8\xfffake\xff\xd9", "image/jpeg"),
    ("truncado.jpg", amostras.jpeg()[:40] + b"\xff\xd9", "image/jpeg"),
    ("errado.png", pdf(), "image/png"),
    ("foto.png", amostras.png(), "application/x-msdownload"),
    (r"C:\fotos\foto.png", amostras.png(), "image/png"),
], ids=lambda value: value if isinstance(value, str) else "conteudo")
def test_integracao_recusa_falsificacoes_antes_de_upload_e_auditoria(
    service, repository, storage, db_session, nome, conteudo, mime,
):
    from app.core.exceptions import ArquivoInvalidoException
    with pytest.raises(ArquivoInvalidoException):
        service.criar(
            pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo=nome,
            conteudo=conteudo, content_type=mime,
        )
    storage.upload.assert_not_called()
    repository.create.assert_not_called()
    db_session.add.assert_not_called()
    db_session.commit.assert_not_called()


def test_integracao_preserva_limite_de_processamento(service, storage, repository, monkeypatch):
    from app.infrastructure.storage import file_validation
    monkeypatch.setattr(file_validation, "PARSER_TIMEOUT_SECONDS", 0.0001)
    with pytest.raises(ArquivoInvalidoError):
        service.criar(
            pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo="arquivo.pdf",
            conteudo=pdf(),
        )
    storage.upload.assert_not_called()
    repository.create.assert_not_called()


@pytest.mark.parametrize("acao", [b"/JavaScript", b"/J#61vaScript", b"/Launch"])
def test_integracao_preserva_rejeicao_de_pdf_ativo_da_hml(service, storage, repository, acao):
    with pytest.raises(ArquivoInvalidoError, match="conteúdo ativo"):
        service.criar(
            pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo="ativo.pdf",
            conteudo=amostras.pdf(b"3 0 obj << /S " + acao + b" >> endobj"),
        )
    storage.upload.assert_not_called()
    repository.create.assert_not_called()


def test_falha_na_auditoria_compensa_upload(service, repository, storage, db_session):
    repository.create.return_value = criar_anexo()
    storage.upload.return_value = "generated"
    db_session.add.side_effect = RuntimeError("audit failed")
    with pytest.raises(RuntimeError, match="audit failed"):
        service.criar(
            pedido_id=uuid4(), enviado_por_id=uuid4(), nome_arquivo="arquivo.pdf",
            conteudo=pdf(),
        )
    db_session.rollback.assert_called_once()
    db_session.commit.assert_not_called()
    storage.delete.assert_called_once_with("generated")


@pytest.mark.parametrize("perfil,participa", [
    ("ADMIN", False), ("CLIENTE", True), ("TECNICO", True),
    ("CLIENTE", False), ("TECNICO", False),
])
def test_demand_service_preserva_escopo_de_evidencias_da_hml(
    service, repository, storage, db_session, perfil, participa,
):
    from app.core.exceptions import RecursoNaoEncontradoException
    from app.domain.models.enums import PerfilEnum, StatusPedidoEnum
    from app.domain.models.pedido import Pedido
    from app.domain.models.user import User
    from app.services.demand_service import DemandService
    usuario = User(id=uuid4(), perfil=PerfilEnum(perfil), ativo=True)
    pedido = Pedido(
        id=uuid4(), cliente_id=usuario.id if participa else uuid4(),
        responsavel_id=usuario.id if participa else uuid4(),
        status=StatusPedidoEnum.EXECUCAO,
    )
    db_session.scalar.return_value = pedido
    repository.create.return_value = criar_anexo()
    demand_service = DemandService(db_session, anexo_service=service)
    if participa or perfil == "ADMIN":
        resultado = demand_service.registrar_evidencia(
            usuario, pedido.id, nome_arquivo="foto.png", conteudo=amostras.png(),
        )
        assert resultado is repository.create.return_value
        assert repository.create.call_args.args[0]["enviado_por_id"] == usuario.id
        db_session.commit.assert_called_once()
    else:
        with pytest.raises(RecursoNaoEncontradoException):
            demand_service.registrar_evidencia(
                usuario, pedido.id, nome_arquivo="foto.png", conteudo=amostras.png(),
            )
        repository.create.assert_not_called()
        storage.upload.assert_not_called()
        db_session.commit.assert_not_called()
        db_session.rollback.assert_called_once()

"""Rotas de escrita das demandas: ciclo de vida, aceite, etapas e evidencias.

O usuario de toda operacao vem do Bearer token (get_current_user); nenhum
cliente_id/autor_id do corpo e usado para autorizar ou auditar.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.openapi import ERROR_RESPONSES
from app.core.database import get_db
from app.core.exceptions import (
    AcessoNegadoException,
    AprovacaoNaoAutorizadaException,
    RecursoNaoEncontradoException,
    RegistroImutavelException,
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
)
from app.domain.models.user import User
from app.domain.regras.arquivos import TAMANHO_MAXIMO_BYTES
from app.domain.schemas.anexo_consulta_schema import AnexoConsultaResponse
from app.domain.schemas.aprovacao_schema import (
    AprovacaoRespostaSchema,
    AprovacaoSolicitacaoSchema,
)
from app.domain.schemas.demanda_acoes_schema import (
    AuditoriaResponse,
    DemandaCreateRequest,
    DemandaUpdateRequest,
    EtapaCreateRequest,
    EtapaResponse,
    RejeicaoRequest,
    ResponsavelRequest,
    StatusUpdateRequest,
)
from app.domain.schemas.demanda_schema import DemandaResponse
from app.domain.schemas.ocorrencia_schema import (
    OcorrenciaCreate,
    OcorrenciaResponse,
    OcorrenciaUpdate,
)
from app.infrastructure.storage.supabase_storage import StorageReadError
from app.schemas.anexo import AnexoResponse
from app.services.demand_service import DemandService

router = APIRouter(prefix="/demandas", responses=ERROR_RESPONSES)

_STATUS_POR_EXCECAO: tuple[tuple[type[RegraNegocioException], int], ...] = (
    (RecursoNaoEncontradoException, status.HTTP_404_NOT_FOUND),
    (AcessoNegadoException, status.HTTP_403_FORBIDDEN),
    (AprovacaoNaoAutorizadaException, status.HTTP_403_FORBIDDEN),
    (RegistroImutavelException, status.HTTP_409_CONFLICT),
    (TransicaoEstadoInvalidaException, status.HTTP_409_CONFLICT),
    (RegraNegocioException, 422),
)


@contextmanager
def _regras_como_http() -> Iterator[None]:
    try:
        yield
    except RegraNegocioException as erro:
        for tipo, codigo in _STATUS_POR_EXCECAO:
            if isinstance(erro, tipo):
                raise HTTPException(status_code=codigo, detail=erro.mensagem) from None
        raise


def get_demand_service(db: Session = Depends(get_db)) -> DemandService:
    return DemandService(db)


@router.post(
    "",
    tags=["Demandas"],
    response_model=DemandaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra uma demanda",
)
def criar_demanda(
    dados: DemandaCreateRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.criar(
            usuario,
            titulo=dados.titulo,
            descricao=dados.descricao,
            cliente_id=dados.cliente_id,
        )
    return DemandaResponse.model_validate(pedido)


@router.put(
    "/{id}",
    response_model=DemandaResponse,
    tags=["Demandas"],
    summary="Atualiza título e descrição",
    description="CLIENTE proprietário ou ADMIN. Recusa campos protegidos e demandas concluídas.",
)
@router.patch(
    "/{id}",
    response_model=DemandaResponse,
    tags=["Demandas"],
    summary="Edita título e descrição",
    description="Compatibilidade: exige título e descrição; mesmas regras do PUT.",
)
def editar_demanda(
    id: UUID,
    dados: DemandaUpdateRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.editar(
            usuario, id, titulo=dados.titulo, descricao=dados.descricao
        )
    return DemandaResponse.model_validate(pedido)


@router.delete(
    "/{id}",
    tags=["Demandas"],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui uma demanda nao concluida",
)
def excluir_demanda(
    id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> Response:
    with _regras_como_http():
        service.excluir(usuario, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{id}/status",
    tags=["Homologação"],
    response_model=DemandaResponse,
    summary="Avanca o estado (PLANEAMENTO -> EXECUCAO -> HOMOLOGACAO)",
)
def alterar_status(
    id: UUID,
    dados: StatusUpdateRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.alterar_status(usuario, id, dados.status)
    return DemandaResponse.model_validate(pedido)


@router.post(
    "/{id}/aceite",
    tags=["Homologação"],
    response_model=AprovacaoRespostaSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Registra o aceite formal do cliente autenticado",
)
def aprovar_homologacao(
    id: UUID,
    dados: AprovacaoSolicitacaoSchema,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> AprovacaoRespostaSchema:
    with _regras_como_http():
        aceite = service.aprovar_homologacao(
            usuario,
            id,
            versao_entregavel=dados.versao_entregavel,
            declaracao_aceite=dados.declaracao_aceite,
        )
    return AprovacaoRespostaSchema.model_validate(aceite)


@router.post(
    "/{id}/rejeicao",
    tags=["Homologação"],
    response_model=DemandaResponse,
    summary="Rejeita a homologacao e devolve para EXECUCAO",
)
def rejeitar_homologacao(
    id: UUID,
    dados: RejeicaoRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.rejeitar_homologacao(usuario, id, motivo=dados.motivo)
    return DemandaResponse.model_validate(pedido)


@router.put(
    "/{id}/responsavel",
    tags=["Demandas"],
    response_model=DemandaResponse,
    summary="Atribui o tecnico responsavel",
)
def atribuir_responsavel(
    id: UUID,
    dados: ResponsavelRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.atribuir_responsavel(
            usuario, id, responsavel_id=dados.responsavel_id
        )
    return DemandaResponse.model_validate(pedido)


@router.get(
    "/{id}/etapas",
    tags=["Etapas"],
    response_model=list[EtapaResponse],
    summary="Lista as etapas operacionais",
)
def listar_etapas(
    id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> list[EtapaResponse]:
    with _regras_como_http():
        etapas = service.listar_etapas(usuario, id)
    return [EtapaResponse.model_validate(etapa) for etapa in etapas]


@router.post(
    "/{id}/etapas",
    tags=["Etapas"],
    response_model=EtapaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra uma etapa operacional",
)
def adicionar_etapa(
    id: UUID,
    dados: EtapaCreateRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> EtapaResponse:
    with _regras_como_http():
        etapa = service.adicionar_etapa(usuario, id, descricao=dados.descricao)
    return EtapaResponse.model_validate(etapa)


@router.post(
    "/{id}/etapas/{etapa_id}/conclusao",
    tags=["Etapas"],
    response_model=EtapaResponse,
    summary="Conclui uma etapa operacional",
)
def concluir_etapa(
    id: UUID,
    etapa_id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> EtapaResponse:
    with _regras_como_http():
        etapa = service.concluir_etapa(usuario, id, etapa_id)
    return EtapaResponse.model_validate(etapa)


@router.post(
    "/{id}/evidencias",
    tags=["Anexos"],
    response_model=AnexoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Envia uma evidencia (pdf, png, jpg, jpeg ou docx, ate 10 MB)",
)
def enviar_evidencia(
    id: UUID,
    arquivo: UploadFile = File(...),
    ocorrencia_id: UUID | None = Form(default=None),
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> AnexoResponse:
    # Le no maximo 1 byte alem do limite: o suficiente para recusar sem
    # carregar arquivos arbitrariamente grandes na memoria.
    conteudo = arquivo.file.read(TAMANHO_MAXIMO_BYTES + 1)
    with _regras_como_http():
        anexo = service.registrar_evidencia(
            usuario,
            id,
            nome_arquivo=arquivo.filename or "",
            conteudo=conteudo,
            ocorrencia_id=ocorrencia_id,
        )
    return AnexoResponse.model_validate(anexo)


@router.get(
    "/{id}/historico",
    tags=["Auditoria"],
    response_model=list[AuditoriaResponse],
    summary="Historico de auditoria da demanda (somente leitura)",
)
def listar_historico(
    id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> list[AuditoriaResponse]:
    with _regras_como_http():
        registros = service.listar_auditoria(usuario, id)
    return [AuditoriaResponse.model_validate(registro) for registro in registros]


@router.get(
    "/{id}/ocorrencias",
    response_model=list[OcorrenciaResponse],
    tags=["Ocorrências"],
    summary="Lista ocorrências da demanda",
)
def listar_ocorrencias(
    id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
):
    with _regras_como_http():
        return service.listar_ocorrencias(usuario, id, offset=offset, limit=limit)


@router.post(
    "/{id}/ocorrencias",
    response_model=OcorrenciaResponse,
    status_code=201,
    tags=["Ocorrências"],
    summary="Registra ocorrência com autor do token",
)
def criar_ocorrencia(
    id: UUID,
    dados: OcorrenciaCreate,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
):
    with _regras_como_http():
        return service.criar_ocorrencia(usuario, id, **dados.model_dump())


@router.get(
    "/{id}/ocorrencias/{ocorrencia_id}",
    response_model=OcorrenciaResponse,
    tags=["Ocorrências"],
    summary="Consulta ocorrência vinculada à demanda",
)
def obter_ocorrencia(
    id: UUID,
    ocorrencia_id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
):
    with _regras_como_http():
        return service.obter_ocorrencia(usuario, id, ocorrencia_id)


@router.put(
    "/{id}/ocorrencias/{ocorrencia_id}",
    response_model=OcorrenciaResponse,
    tags=["Ocorrências"],
    summary="Atualiza descrição da ocorrência",
    description="Autor ou ADMIN. Rejeições e demandas concluídas são somente leitura; vínculo, tipo e autor são imutáveis.",
)
def editar_ocorrencia(
    id: UUID,
    ocorrencia_id: UUID,
    dados: OcorrenciaUpdate,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
):
    with _regras_como_http():
        return service.editar_ocorrencia(
            usuario, id, ocorrencia_id, **dados.model_dump()
        )


@router.get(
    "/{id}/anexos",
    response_model=list[AnexoConsultaResponse],
    tags=["Anexos"],
    summary="Lista metadados dos anexos autorizados",
    description="Paginação estável. Não expõe caminho do bucket nem credenciais. Use a operação de acesso para obter um link temporário.",
)
def listar_anexos(
    id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
):
    with _regras_como_http():
        return service.listar_anexos(usuario, id, offset=offset, limit=limit)


@router.get(
    "/{id}/anexos/{anexo_id}/acesso",
    tags=["Anexos"],
    response_class=RedirectResponse,
    status_code=307,
    summary="Acessa arquivo privado por link de 60 segundos",
    responses={503: {"description": "Storage indisponível."}},
)
def acessar_anexo(
    id: UUID,
    anexo_id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
):
    try:
        with _regras_como_http():
            url = service.acessar_anexo(usuario, id, anexo_id)
    except StorageReadError:
        raise HTTPException(
            503, "Acesso ao arquivo temporariamente indisponível."
        ) from None
    return RedirectResponse(
        url, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    )

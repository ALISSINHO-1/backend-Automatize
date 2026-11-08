"""Rotas de escrita das demandas: ciclo de vida, aceite, etapas e evidencias.

O usuario de toda operacao vem do Bearer token (get_current_user); nenhum
cliente_id/autor_id do corpo e usado para autorizar ou auditar.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_application_settings, get_current_user
from app.core.config import Settings
from app.core.database import get_db
from app.core.exceptions import (
    AcessoNegadoException,
    AprovacaoNaoAutorizadaException,
    OperacaoConflitanteException,
    RecursoNaoEncontradoException,
    RegistroImutavelException,
    RegraNegocioException,
    TransicaoEstadoInvalidaException,
)
from app.domain.models.user import User
from app.domain.regras.arquivos import TAMANHO_MAXIMO_BYTES
from app.domain.schemas.aprovacao_schema import AprovacaoRespostaSchema, AprovacaoSolicitacaoSchema
from app.domain.schemas.demanda_acoes_schema import (
    AuditoriaResponse,
    DemandaCreateRequest,
    DemandaPrevisaoRequest,
    DemandaDisponivelResponse,
    DemandaUpdateRequest,
    EtapaCreateRequest,
    EtapaResponse,
    EtapaUpdateRequest,
    OcorrenciaCreateRequest,
    OcorrenciaResponse,
    RejeicaoRequest,
    ResolucaoOcorrenciaRequest,
    ResponsavelRequest,
    StatusUpdateRequest,
)
from app.domain.schemas.demanda_schema import DemandaResponse
from app.schemas.anexo import AnexoResponse
from app.domain.schemas.anexo_consulta import AnexoPublico, AnexoAcesso
from app.infrastructure.storage.supabase_storage import StorageReadError
from app.services.demand_service import DemandService


router = APIRouter(prefix="/demandas", tags=["Demandas - Acoes"], responses={
    401: {"description": "Token ausente, invalido, expirado ou usuario inativo."},
    403: {"description": "Perfil sem permissao para esta operacao."},
    404: {"description": "Recurso inexistente ou fora do escopo do usuario."},
    409: {"description": "Conflito com o estado ou a imutabilidade do recurso."},
    422: {"description": "Entrada invalida ou campo protegido/nao permitido."},
})

_STATUS_POR_EXCECAO: tuple[tuple[type[RegraNegocioException], int], ...] = (
    (RecursoNaoEncontradoException, status.HTTP_404_NOT_FOUND),
    (AcessoNegadoException, status.HTTP_403_FORBIDDEN),
    (AprovacaoNaoAutorizadaException, status.HTTP_403_FORBIDDEN),
    (RegistroImutavelException, status.HTTP_409_CONFLICT),
    (OperacaoConflitanteException, status.HTTP_409_CONFLICT),
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


def get_demand_service(
    db: Session = Depends(get_db),
    configured_settings: Settings = Depends(get_application_settings),
) -> DemandService:
    return DemandService(db, storage_settings=configured_settings)


@router.post("", response_model=DemandaResponse, status_code=status.HTTP_201_CREATED,
             summary="Cadastra uma demanda")
def criar_demanda(
    dados: DemandaCreateRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.criar(usuario, titulo=dados.titulo, descricao=dados.descricao,
                               cliente_id=dados.cliente_id, data_previsao=dados.data_previsao)
    return DemandaResponse.model_validate(pedido)


@router.patch("/{id}", response_model=DemandaResponse, summary="Edita titulo e descricao")
def editar_demanda(
    id: UUID,
    dados: DemandaUpdateRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.editar(usuario, id, titulo=dados.titulo, descricao=dados.descricao)
    return DemandaResponse.model_validate(pedido)


@router.patch("/{id}/previsao", status_code=status.HTTP_204_NO_CONTENT,
              summary="Atualiza ou remove a data prevista de uma demanda")
def atualizar_previsao(
    id: UUID,
    dados: DemandaPrevisaoRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> Response:
    with _regras_como_http():
        service.atualizar_previsao(usuario, id, dados.data_previsao)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, summary="Exclui uma demanda nao concluida")
def excluir_demanda(
    id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> Response:
    with _regras_como_http():
        service.excluir(usuario, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{id}/status", response_model=DemandaResponse,
             summary="Avanca o estado (PLANEAMENTO -> EXECUCAO -> HOMOLOGACAO)")
def alterar_status(
    id: UUID,
    dados: StatusUpdateRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.alterar_status(usuario, id, dados.status)
    return DemandaResponse.model_validate(pedido)


@router.post("/{id}/aceite", response_model=AprovacaoRespostaSchema, status_code=status.HTTP_201_CREATED,
             summary="Registra o aceite formal do cliente autenticado")
def aprovar_homologacao(
    id: UUID,
    dados: AprovacaoSolicitacaoSchema,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> AprovacaoRespostaSchema:
    with _regras_como_http():
        aceite = service.aprovar_homologacao(usuario, id, versao_entregavel=dados.versao_entregavel,
                                             declaracao_aceite=dados.declaracao_aceite)
    return AprovacaoRespostaSchema.model_validate(aceite)


@router.post("/{id}/rejeicao", response_model=DemandaResponse,
             summary="Rejeita a homologacao e devolve para EXECUCAO")
def rejeitar_homologacao(
    id: UUID,
    dados: RejeicaoRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.rejeitar_homologacao(usuario, id, motivo=dados.motivo)
    return DemandaResponse.model_validate(pedido)


@router.get("/chat/fila", response_model=list[DemandaDisponivelResponse],
            summary="Lista demandas sem responsavel para atendimento tecnico")
def listar_fila_atendimento(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> list[DemandaDisponivelResponse]:
    with _regras_como_http():
        pedidos = service.listar_fila_atendimento(usuario, offset=offset, limit=limit)
    return [DemandaDisponivelResponse.model_validate(pedido) for pedido in pedidos]


@router.post("/{id}/assumir", status_code=status.HTTP_204_NO_CONTENT,
             summary="Assume uma demanda disponivel como tecnico responsavel")
def assumir_demanda(
    id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> Response:
    with _regras_como_http():
        service.assumir_demanda(usuario, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{id}/responsavel", response_model=DemandaResponse,
            summary="Atribui ou reatribui o tecnico responsavel (reatribuicao exige motivo)")
def atribuir_responsavel(
    id: UUID,
    dados: ResponsavelRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.atribuir_responsavel(usuario, id, responsavel_id=dados.responsavel_id,
                                              motivo=dados.motivo)
    return DemandaResponse.model_validate(pedido)


@router.get("/{id}/etapas", response_model=list[EtapaResponse], summary="Lista as etapas operacionais")
def listar_etapas(
    id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> list[EtapaResponse]:
    with _regras_como_http():
        etapas = service.listar_etapas(usuario, id)
    return [EtapaResponse.model_validate(etapa) for etapa in etapas]


@router.post("/{id}/etapas", response_model=EtapaResponse, status_code=status.HTTP_201_CREATED,
             summary="Cadastra uma etapa operacional")
def adicionar_etapa(
    id: UUID,
    dados: EtapaCreateRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> EtapaResponse:
    with _regras_como_http():
        etapa = service.adicionar_etapa(usuario, id, descricao=dados.descricao, ordem=dados.ordem)
    return EtapaResponse.model_validate(etapa)


@router.patch("/{id}/etapas/{etapa_id}", response_model=EtapaResponse,
              summary="Edita descricao ou reposiciona uma etapa pendente")
def editar_etapa(id: UUID, etapa_id: UUID, dados: EtapaUpdateRequest,
                 usuario: User = Depends(get_current_user),
                 service: DemandService = Depends(get_demand_service)):
    with _regras_como_http():
        etapa = service.editar_etapa(usuario, id, etapa_id, **dados.model_dump(exclude_none=True))
    return EtapaResponse.model_validate(etapa)


@router.delete("/{id}/etapas/{etapa_id}", status_code=204,
               summary="Remove etapa pendente com justificativa e auditoria")
def remover_etapa(id: UUID, etapa_id: UUID, motivo: str = Query(..., min_length=10, max_length=500),
                  usuario: User = Depends(get_current_user),
                  service: DemandService = Depends(get_demand_service)):
    with _regras_como_http():
        service.remover_etapa(usuario, id, etapa_id, motivo=motivo)
    return Response(status_code=204)


@router.post("/{id}/etapas/{etapa_id}/conclusao", response_model=EtapaResponse,
             summary="Conclui uma etapa operacional")
def concluir_etapa(
    id: UUID,
    etapa_id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> EtapaResponse:
    with _regras_como_http():
        etapa = service.concluir_etapa(usuario, id, etapa_id)
    return EtapaResponse.model_validate(etapa)


@router.post("/{id}/evidencias", response_model=AnexoResponse, status_code=status.HTTP_201_CREATED,
             summary="Envia uma evidencia (pdf, png, jpg, jpeg ou docx, ate 10 MB)")
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
        anexo = service.registrar_evidencia(usuario, id, nome_arquivo=arquivo.filename or "",
                                            conteudo=conteudo, content_type=arquivo.content_type,
                                            ocorrencia_id=ocorrencia_id)
    return AnexoResponse.model_validate(anexo)


@router.get("/{id}/historico", response_model=list[AuditoriaResponse],
            summary="Historico de auditoria da demanda (somente leitura)")
def listar_historico(
    id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> list[AuditoriaResponse]:
    with _regras_como_http():
        registros = service.listar_auditoria(usuario, id)
    return [AuditoriaResponse.model_validate(registro) for registro in registros]


@router.get("/{id}/anexos", response_model=list[AnexoPublico],
            summary="Lista metadados dos anexos da demanda autorizada")
def listar_anexos(id: UUID, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                  usuario: User = Depends(get_current_user),
                  service: DemandService = Depends(get_demand_service)):
    with _regras_como_http():
        anexos = service.listar_anexos(usuario, id, offset=offset, limit=limit)
    return [AnexoPublico(
        id=a.id, pedido_id=a.pedido_id, ocorrencia_id=a.ocorrencia_id,
        nome_arquivo=a.nome_arquivo, extensao=a.extensao, tamanho_bytes=a.tamanho_bytes,
        created_at=a.created_at, referencia_acesso=f"/demandas/{id}/anexos/{a.id}/acesso",
    ) for a in anexos]


@router.get("/{id}/anexos/{anexo_id}/acesso", response_model=AnexoAcesso,
            summary="Gera link assinado valido por cinco minutos",
            responses={404: {"description": "Anexo ou demanda inexistente ou fora do escopo."},
                       503: {"description": "Storage indisponivel ou nao configurado."}})
def acessar_anexo(id: UUID, anexo_id: UUID, response: Response,
                   usuario: User = Depends(get_current_user),
                   service: DemandService = Depends(get_demand_service)):
    # O link e uma credencial temporaria: nao deve ser armazenado em cache.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    expira_em = datetime.now(timezone.utc) + timedelta(seconds=300)
    with _regras_como_http():
        try:
            url = service.acessar_anexo(usuario, id, anexo_id)
        except (StorageReadError, RuntimeError):
            raise HTTPException(503, "Acesso ao arquivo temporariamente indisponivel.") from None
    return AnexoAcesso(url=url, expira_em=expira_em, validade_segundos=300)


@router.get("/{id}/ocorrencias", response_model=list[OcorrenciaResponse],
            summary="Lista as ocorrencias (erros, correcoes e regressos) da demanda")
def listar_ocorrencias(
    id: UUID,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> list[OcorrenciaResponse]:
    with _regras_como_http():
        ocorrencias = service.listar_ocorrencias(usuario, id)
    return [OcorrenciaResponse.model_validate(ocorrencia) for ocorrencia in ocorrencias]


@router.post("/{id}/ocorrencias", response_model=OcorrenciaResponse, status_code=status.HTTP_201_CREATED,
             summary="Registra um erro ou pedido de correcao (bloqueia a HOMOLOGACAO ate ser resolvido)")
def registrar_ocorrencia(
    id: UUID,
    dados: OcorrenciaCreateRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> OcorrenciaResponse:
    with _regras_como_http():
        ocorrencia = service.registrar_ocorrencia(usuario, id, tipo=dados.tipo, descricao=dados.descricao)
    return OcorrenciaResponse.model_validate(ocorrencia)


@router.post("/{id}/ocorrencias/{ocorrencia_id}/resolucao", response_model=OcorrenciaResponse,
             summary="Registra a correcao de uma ocorrencia")
def resolver_ocorrencia(
    id: UUID,
    ocorrencia_id: UUID,
    dados: ResolucaoOcorrenciaRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> OcorrenciaResponse:
    with _regras_como_http():
        ocorrencia = service.resolver_ocorrencia(usuario, id, ocorrencia_id,
                                                 descricao_resolucao=dados.descricao_resolucao)
    return OcorrenciaResponse.model_validate(ocorrencia)

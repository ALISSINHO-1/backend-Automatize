"""Rotas de escrita das demandas: ciclo de vida, aceite, etapas e evidencias.

O usuario de toda operacao vem do Bearer token (get_current_user); nenhum
cliente_id/autor_id do corpo e usado para autorizar ou auditar.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
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
from app.domain.schemas.aprovacao_schema import AprovacaoRespostaSchema, AprovacaoSolicitacaoSchema
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
from app.schemas.anexo import AnexoResponse
from app.services.demand_service import DemandService


router = APIRouter(prefix="/demandas", tags=["Demandas - Acoes"])

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


@router.post("", response_model=DemandaResponse, status_code=status.HTTP_201_CREATED,
             summary="Cadastra uma demanda")
def criar_demanda(
    dados: DemandaCreateRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.criar(usuario, titulo=dados.titulo, descricao=dados.descricao,
                               cliente_id=dados.cliente_id)
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


@router.put("/{id}/responsavel", response_model=DemandaResponse, summary="Atribui o tecnico responsavel")
def atribuir_responsavel(
    id: UUID,
    dados: ResponsavelRequest,
    usuario: User = Depends(get_current_user),
    service: DemandService = Depends(get_demand_service),
) -> DemandaResponse:
    with _regras_como_http():
        pedido = service.atribuir_responsavel(usuario, id, responsavel_id=dados.responsavel_id)
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
        etapa = service.adicionar_etapa(usuario, id, descricao=dados.descricao)
    return EtapaResponse.model_validate(etapa)


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
                                            conteudo=conteudo, ocorrencia_id=ocorrencia_id)
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

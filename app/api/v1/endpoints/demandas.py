from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.domain.models.user import User
from app.domain.schemas.demanda_schema import DemandaResponse
from app.domain.schemas.demanda_filtros import DemandaFiltros, DemandaIndicadores
from app.domain.models.enums import StatusPedidoEnum
from app.services.demanda_service import DemandAccessDenied, DemandaQueryService


router = APIRouter(prefix="/demandas", tags=["Demandas"])

_DEMANDA_EXAMPLE = {
    "id": "ca57c5bc-0efa-4202-9c3e-7b46c560bbef",
    "codigo_identificador": "DEM-0001",
    "titulo": "Atualizar painel",
    "descricao": None,
    "status": "PLANEAMENTO",
    "percentual_progresso": "0.00",
    "cliente_id": "b32e49ec-f8dd-4a8f-9ae9-dc3f90b4a4b1",
    "responsavel_id": None,
    "created_at": "2026-05-06T07:08:00Z",
    "updated_at": "2026-05-06T07:08:00Z",
}

_UNAUTHORIZED_RESPONSE = {
    "description": "Token ausente, inválido ou expirado.",
    "headers": {
        "WWW-Authenticate": {
            "description": "Esquema de autenticação exigido.",
            "schema": {"type": "string", "example": "Bearer"},
        }
    },
    "content": {
        "application/json": {
            "example": {"detail": "Não foi possível autenticar."}
        }
    },
}


def filtros_demanda(
    busca: str | None = Query(None, min_length=1, max_length=255),
    status: StatusPedidoEnum | None = Query(None),
    cliente_id: UUID | None = Query(None),
    responsavel_id: UUID | None = Query(None),
    criado_de: datetime | None = Query(None, description="Inicio inclusivo; data/hora com fuso."),
    criado_ate: datetime | None = Query(None, description="Fim inclusivo; data/hora com fuso."),
) -> DemandaFiltros | None:
    for valor in (criado_de, criado_ate):
        if valor is not None and valor.utcoffset() is None:
            raise HTTPException(422, "Informe datas com fuso horario (Z ou -03:00).")
    if criado_de and criado_ate and criado_de > criado_ate:
        raise HTTPException(422, "criado_de deve ser anterior ou igual a criado_ate.")
    if busca is not None and not busca.strip():
        raise HTTPException(422, "A busca nao pode conter apenas espacos.")
    valores = dict(busca=busca, status=status, cliente_id=cliente_id, responsavel_id=responsavel_id,
                   criado_de=criado_de, criado_ate=criado_ate)
    return DemandaFiltros(**valores) if any(v is not None for v in valores.values()) else None


@router.get(
    "",
    response_model=list[DemandaResponse],
    summary="Lista demandas acessíveis ao usuário autenticado",
    description=(
        "ADMIN consulta todas as demandas; CLIENTE consulta apenas as demandas "
        "com cliente_id igual ao seu UUID; TECNICO consulta apenas as demandas "
        "com responsavel_id igual ao seu UUID. Perfis desconhecidos recebem 403. "
        "A ordenação é crescente por created_at e id. percentual_progresso é "
        "retornado como string decimal para preservar a precisão."
    ),
    responses={
        200: {
            "description": "Lista paginada de demandas acessíveis.",
            "content": {"application/json": {"example": [_DEMANDA_EXAMPLE]}},
        },
        401: _UNAUTHORIZED_RESPONSE,
        403: {"description": "Perfil sem política de consulta de demandas."},
        422: {"description": "Paginacao, filtros ou intervalo de datas invalidos."},
    },
)
def list_demandas(
    offset: int = Query(default=0, ge=0, description="Número de registros a pular."),
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
        description="Quantidade de registros por página, entre 1 e 100.",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    filtros: DemandaFiltros | None = Depends(filtros_demanda),
) -> list[DemandaResponse]:
    try:
        argumentos = {"filtros": filtros} if filtros is not None else {}
        results = DemandaQueryService(db).list_demands(
            user,
            offset=offset,
            limit=limit,
            **argumentos,
        )
    except DemandAccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Perfil sem permissão para consultar demandas.",
        ) from None
    return [DemandaResponse.model_validate(item) for item in results]


@router.get("/indicadores", response_model=DemandaIndicadores,
            summary="Conta todas as demandas do conjunto filtrado autorizado",
            responses={401: _UNAUTHORIZED_RESPONSE, 403: {"description": "Perfil sem permissao."},
                       422: {"description": "Filtros ou intervalo de datas invalidos."}})
def indicadores_demandas(
    filtros: DemandaFiltros | None = Depends(filtros_demanda),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return DemandaQueryService(db).indicadores(user, filtros or DemandaFiltros())
    except DemandAccessDenied:
        raise HTTPException(403, "Perfil sem permissao para consultar demandas.") from None


@router.get(
    "/{id}",
    response_model=DemandaResponse,
    summary="Consulta uma demanda acessível",
    description=(
        "Aplica a mesma política de acesso da listagem. Um UUID inexistente ou "
        "fora do escopo do usuário retorna 404. percentual_progresso é retornado "
        "como string decimal para preservar a precisão."
    ),
    responses={
        200: {
            "description": "Demanda acessível ao usuário autenticado.",
            "content": {"application/json": {"example": _DEMANDA_EXAMPLE}},
        },
        401: _UNAUTHORIZED_RESPONSE,
        403: {"description": "Perfil sem política de consulta de demandas."},
        404: {"description": "Demanda inexistente ou fora do escopo."},
        422: {"description": "UUID inválido."},
    },
)
def get_demanda(
    id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DemandaResponse:
    try:
        result = DemandaQueryService(db).get_demand(user, id)
    except DemandAccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Perfil sem permissão para consultar demandas.",
        ) from None
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demanda não encontrada.",
        )
    return DemandaResponse.model_validate(result)

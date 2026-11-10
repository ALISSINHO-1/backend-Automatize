"""Aprovacao de entidades comerciais. Nenhum cliente pode se promover."""
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.endpoints.demandas_acoes import _regras_como_http
from app.core.database import get_db
from app.domain.models.enums import PerfilEnum
from app.domain.models.organizacao import Organizacao
from app.domain.models.user import User
from app.domain.regras import autorizacao
from app.domain.schemas.comercial_schema import (
    ContratoDEV, ContratoSAAS, ContratoResposta, NovaOrganizacao,
    NovoMembro, OrganizacaoResposta, VinculoResposta, ContaPendenteResposta,
)
from app.services.comercial_service import ComercialService

router = APIRouter(prefix="/comercial", tags=["Comercial interno"])

@router.post("/organizacoes", response_model=OrganizacaoResposta,
             status_code=status.HTTP_201_CREATED)
def criar_empresa(
    dados: NovaOrganizacao, usuario: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    with _regras_como_http():
        return ComercialService(db).criar_organizacao(usuario, nome=dados.nome)

@router.get("/organizacoes", response_model=list[OrganizacaoResposta])
def listar_empresas(
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    usuario: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        autorizacao.exigir_perfil(usuario, PerfilEnum.ADMIN)
        return db.scalars(
            select(Organizacao).order_by(Organizacao.nome, Organizacao.id)
            .offset(offset).limit(limit)
        ).all()

@router.post("/organizacoes/{organizacao_id}/membros",
             response_model=VinculoResposta, status_code=status.HTTP_201_CREATED)
def vincular_membro(
    organizacao_id: UUID, dados: NovoMembro,
    usuario: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return ComercialService(db).vincular_membro(
            usuario, organizacao_id=organizacao_id,
            usuario_id=dados.usuario_id, papel=dados.papel,
        )

@router.post("/contratos/dev", response_model=ContratoResposta,
             status_code=status.HTTP_201_CREATED)
def criar_contrato_dev(
    dados: ContratoDEV,
    usuario: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return ComercialService(db).criar_contrato_dev(
            usuario, usuario_id=dados.usuario_id,
        )

@router.post("/contratos/saas", response_model=ContratoResposta,
             status_code=status.HTTP_201_CREATED)
def criar_contrato_saas(
    dados: ContratoSAAS,
    usuario: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return ComercialService(db).criar_contrato_saas(
            usuario, organizacao_id=dados.organizacao_id,
        )

@router.patch("/contratos/{contrato_id}/ativar", response_model=ContratoResposta)
def ativar_contrato_dev(
    contrato_id: UUID,
    usuario: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return ComercialService(db).ativar_contrato_dev(
            usuario, contrato_id=contrato_id,
        )

@router.get("/contas/pendentes", response_model=list[ContaPendenteResposta])
def listar_contas_pendentes(
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    usuario: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        autorizacao.exigir_perfil(usuario, PerfilEnum.ADMIN)
        return db.scalars(
            select(User)
            .where(User.situacao_cadastro == "PENDENTE")
            .order_by(User.created_at, User.id)
            .offset(offset).limit(limit)
        ).all()

@router.post("/contas/{usuario_id}/aprovar-dev", response_model=ContratoResposta)
def aprovar_conta_dev(
    usuario_id: UUID,
    usuario: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Somente ADMIN global, com email verificado; cria contrato DEV ATIVO."""
    with _regras_como_http():
        return ComercialService(db).aprovar_conta_dev(
            usuario, usuario_id=usuario_id,
        )

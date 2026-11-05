from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.endpoints.demandas_acoes import _regras_como_http
from app.core.database import get_db
from app.domain.models.enums import PerfilEnum
from app.domain.models.user import User
from app.domain.schemas.user_schema import (
    AtivoUpdateRequest,
    PerfilUpdateRequest,
    UserSummary,
    UsuarioAdminResponse,
    UsuarioCreateRequest,
)
from app.services.user_query_service import UserQueryService
from app.services.usuario_admin_service import UsuarioAdminService

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("/tecnicos", response_model=list[UserSummary])
def technicians(
    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return UserQueryService(db).technicians(user, offset=offset, limit=limit)


@router.get("/clientes", response_model=list[UserSummary])
def clients(
    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return UserQueryService(db).clients(user, offset=offset, limit=limit)


@router.get("/clientes/{client_id}", response_model=UserSummary)
def client(
    client_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return UserQueryService(db).client(user, client_id)


# Gestao de usuarios e perfis pelo ADMIN (SCRUM-96 / SCRUM-99).

@router.get("", response_model=list[UsuarioAdminResponse], summary="Lista usuarios (somente ADMIN)")
def listar_usuarios(
    perfil: PerfilEnum | None = Query(None), ativo: bool | None = Query(None),
    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return UsuarioAdminService(db).listar(user, perfil=perfil, ativo=ativo, offset=offset, limit=limit)


@router.post("", response_model=UsuarioAdminResponse, status_code=status.HTTP_201_CREATED,
             summary="Cadastra um usuario (somente ADMIN)")
def criar_usuario(
    dados: UsuarioCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return UsuarioAdminService(db).criar(user, nome=dados.nome, email=dados.email,
                                             senha=dados.senha, perfil=dados.perfil)


@router.patch("/{usuario_id}/perfil", response_model=UsuarioAdminResponse,
              summary="Altera o perfil de um usuario (somente ADMIN)")
def alterar_perfil(
    usuario_id: UUID, dados: PerfilUpdateRequest,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return UsuarioAdminService(db).alterar_perfil(user, usuario_id, perfil=dados.perfil)


@router.patch("/{usuario_id}/ativo", response_model=UsuarioAdminResponse,
              summary="Ativa ou inativa um usuario (somente ADMIN)")
def alterar_ativo(
    usuario_id: UUID, dados: AtivoUpdateRequest,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    with _regras_como_http():
        return UsuarioAdminService(db).alterar_ativo(user, usuario_id, ativo=dados.ativo)

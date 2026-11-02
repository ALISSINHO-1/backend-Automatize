from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.endpoints.demandas_acoes import _regras_como_http
from app.core.database import get_db
from app.domain.models.user import User
from app.domain.schemas.user_schema import UserSummary
from app.services.user_query_service import UserQueryService

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

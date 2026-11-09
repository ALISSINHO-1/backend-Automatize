"""Cadastro publico recebe conta limitada e nao habilita servicos."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.dependencies import get_application_settings
from app.core.config import Settings
from app.core.database import get_db
from app.domain.schemas.cadastro_schema import CadastroPublicoRequest, CadastroPublicoResponse
from app.services.cadastro_publico_service import CadastroPublicoService

router = APIRouter(prefix="/auth", tags=["Cadastro"])

@router.post("/cadastro", response_model=CadastroPublicoResponse, status_code=status.HTTP_202_ACCEPTED)
def solicitar_cadastro(
    dados: CadastroPublicoRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_application_settings),
) -> CadastroPublicoResponse:
    # Nao habilitar publicamente sem rate limit na borda e verificacao de email.
    if not settings.PUBLIC_SIGNUP_ENABLED:
        raise HTTPException(status_code=503, detail="Novos cadastros temporariamente indisponiveis.")
    CadastroPublicoService(db).solicitar(nome=dados.nome, email=dados.email, senha=dados.senha)
    return CadastroPublicoResponse()

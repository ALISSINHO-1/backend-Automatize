"""Solicitacoes publicas; captcha e mail obrigatorios, conta com acesso limitado."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_application_settings
from app.core.config import Settings
from app.core.database import get_db
from app.domain.schemas.cadastro_schema import (
    CadastroPublicoRequest, CadastroPublicoResponse, EmailPublicoRequest,
    TokenConfirmacaoRequest, RedefinirSenhaRequest,
)
from app.services.cadastro_publico_service import CadastroPublicoService
from app.services.email_sender import EmailDeliveryError, EmailSender
from app.services.tokens_conta_service import TokenInvalido, TokensContaService
from app.services.turnstile_service import valida_turnstile


router = APIRouter(prefix="/auth", tags=["Cadastro"])
logger = logging.getLogger(__name__)
GENERIC = CadastroPublicoResponse()


def _habilitado(settings: Settings, *, reset: bool = False) -> None:
    enabled = settings.PASSWORD_RECOVERY_ENABLED if reset else settings.PUBLIC_SIGNUP_ENABLED
    if not enabled or not EmailSender.ready(settings) or not settings.TURNSTILE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Funcionalidade temporariamente indisponivel.",
        )


def _captcha(token: str | None, settings: Settings) -> None:
    if not valida_turnstile(token, settings):
        raise HTTPException(status_code=400, detail="Nao foi possivel validar a solicitacao.")


def _generic_send(task) -> CadastroPublicoResponse:
    try:
        task()
    except EmailDeliveryError:
        # Nunca colocar segredos, endereco ou link em logs.
        logger.error("Falha do provedor de e-mail na operacao de conta.")
        raise HTTPException(
            status_code=503, detail="Servico temporariamente indisponivel."
        ) from None
    return GENERIC


@router.post("/cadastro", response_model=CadastroPublicoResponse,
             status_code=status.HTTP_202_ACCEPTED)
def solicitar_cadastro(
    dados: CadastroPublicoRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_application_settings),
) -> CadastroPublicoResponse:
    _habilitado(settings)
    _captcha(dados.turnstile_token, settings)
    sender = EmailSender(settings)
    return _generic_send(lambda: CadastroPublicoService(db, sender).solicitar(
        nome=dados.nome, email=dados.email, senha=dados.senha
    ))


@router.post("/verificacao/reenviar", response_model=CadastroPublicoResponse,
             status_code=status.HTTP_202_ACCEPTED)
def reenviar_confirmacao(
    dados: EmailPublicoRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_application_settings),
) -> CadastroPublicoResponse:
    _habilitado(settings)
    _captcha(dados.turnstile_token, settings)
    sender = EmailSender(settings)
    return _generic_send(lambda: CadastroPublicoService(db, sender).reenviar(email=dados.email))


@router.post("/verificar-email", status_code=204)
def confirmar_email(
    dados: TokenConfirmacaoRequest,
    db: Session = Depends(get_db),
) -> None:
    try:
        TokensContaService(db).confirmar_email(dados.token)
    except TokenInvalido:
        raise HTTPException(
            status_code=400, detail="Link de confirmacao invalido ou expirado."
        ) from None


@router.post("/senha/solicitar", response_model=CadastroPublicoResponse,
             status_code=status.HTTP_202_ACCEPTED)
def solicitar_recuperacao(
    dados: EmailPublicoRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_application_settings),
) -> CadastroPublicoResponse:
    _habilitado(settings, reset=True)
    _captcha(dados.turnstile_token, settings)
    sender = EmailSender(settings)
    return _generic_send(lambda: CadastroPublicoService(db, sender).solicitar_reset(email=dados.email))


@router.post("/senha/redefinir", status_code=204)
def redefinir_senha(
    dados: RedefinirSenhaRequest,
    db: Session = Depends(get_db),
) -> None:
    try:
        TokensContaService(db).redefinir_senha(dados.token, dados.nova_senha)
    except TokenInvalido:
        raise HTTPException(status_code=400, detail="Link invalido ou expirado.") from None

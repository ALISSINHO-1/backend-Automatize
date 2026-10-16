from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import get_db
from app.domain.schemas.auth_schema import LoginRequest, TokenResponse
from app.services.auth_service import AuthenticationError, AuthService


router = APIRouter(prefix="/auth", tags=["Autenticação"])


def get_application_settings(request: Request) -> Settings:
    return request.app.state.settings


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Autentica um usuário e emite um token de acesso",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "<JWT>",
                        "token_type": "bearer",
                    }
                }
            }
        },
        401: {
            "description": "Credenciais inválidas ou conta inativa.",
            "headers": {
                "WWW-Authenticate": {
                    "description": "Esquema de autenticação exigido.",
                    "schema": {"type": "string", "example": "Bearer"},
                }
            },
            "content": {
                "application/json": {
                    "example": {"detail": "Credenciais inválidas."}
                }
            },
        },
        422: {"description": "Corpo da requisição inválido."},
    },
)
def login(
    credentials: LoginRequest = Body(
        openapi_examples={
            "login": {
                "summary": "Login de usuário",
                "value": {
                    "email": "cliente@example.com",
                    "senha": "senha-do-usuario",
                },
            }
        }
    ),
    db: Session = Depends(get_db),
    configured_settings: Settings = Depends(get_application_settings),
) -> TokenResponse:
    try:
        token = AuthService(db, configured_settings).authenticate(
            credentials.email,
            credentials.senha,
        )
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    return TokenResponse(access_token=token, token_type="bearer")

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.security import hash_password, verify_password, password_exceeds_bcrypt_limit

from app.api.dependencies import get_application_settings, get_current_user
from app.core.config import Settings
from app.core.database import get_db
from app.domain.models.user import User
from app.domain.schemas.auth_schema import (
    LoginRequest, TokenResponse, UsuarioAtualResponse,
    MeuPerfilDetalhesResponse, MeuNomeUpdateRequest, MinhaSenhaUpdateRequest,
)
from app.services.auth_service import AuthenticationError, AuthService


router = APIRouter(prefix="/auth", tags=["Autenticação"])


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


@router.get(
    "/me",
    response_model=UsuarioAtualResponse,
    summary="Retorna o usuario autenticado (id, nome, e-mail e perfil)",
    responses={401: {"description": "Token ausente, invalido, expirado ou conta inativa."}},
)
def usuario_atual(usuario: User = Depends(get_current_user)) -> UsuarioAtualResponse:
    return UsuarioAtualResponse.model_validate(usuario)


@router.get("/me/detalhes", response_model=MeuPerfilDetalhesResponse,
            summary="Informacoes reais da propria conta")
def meus_detalhes(usuario: User = Depends(get_current_user)) -> MeuPerfilDetalhesResponse:
    return MeuPerfilDetalhesResponse(
        id=usuario.id,
        nome=usuario.nome,
        email=usuario.email,
        perfil=usuario.perfil,
        ativo=usuario.ativo is True,
        criado_em=usuario.created_at,
        email_verificado=usuario.email_verificado_em is not None,
        origem_cadastro=usuario.origem_cadastro,
    )


@router.patch("/me", response_model=UsuarioAtualResponse,
              summary="Edita somente o nome do dono da sessao")
def editar_meu_nome(
    dados: MeuNomeUpdateRequest,
    usuario: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UsuarioAtualResponse:
    usuario.nome = dados.nome
    db.commit()
    db.refresh(usuario)
    return UsuarioAtualResponse.model_validate(usuario)


@router.post("/me/senha", status_code=status.HTTP_204_NO_CONTENT,
             summary="Troca a senha da propria conta, invalidando sessoes anteriores")
def trocar_minha_senha(
    dados: MinhaSenhaUpdateRequest,
    usuario: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(dados.senha_atual, usuario.senha_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")
    if dados.senha_atual == dados.nova_senha:
        raise HTTPException(status_code=422, detail="Escolha uma senha diferente da atual.")
    if password_exceeds_bcrypt_limit(dados.nova_senha):
        raise HTTPException(status_code=422, detail="A senha excede o tamanho permitido.")
    usuario.senha_hash = hash_password(dados.nova_senha)
    usuario.token_version = (usuario.token_version or 0) + 1
    db.commit()

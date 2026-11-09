"""Entradas publicas nunca aceitam perfil, empresa ou contrato."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.security import password_exceeds_bcrypt_limit


def validar_email(email: str) -> str:
    email = email.strip().lower()
    local, sep, dominio = email.rpartition("@")
    if not sep or not local or "." not in dominio or any(c.isspace() for c in email):
        raise ValueError("Informe um e-mail valido.")
    return email


def validar_senha(senha: str) -> str:
    if len(senha) < 8 or password_exceeds_bcrypt_limit(senha):
        raise ValueError("Senha deve ter pelo menos 8 caracteres e no maximo 72 bytes.")
    return senha


class CadastroPublicoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=3, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    senha: str = Field(min_length=8, max_length=1024)
    turnstile_token: str | None = Field(default=None, max_length=2048)

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, valor: str) -> str:
        valor = valor.strip()
        if len(valor) < 3:
            raise ValueError("Informe um nome com pelo menos 3 caracteres.")
        return valor

    @field_validator("email")
    @classmethod
    def validar_email_formato(cls, valor: str) -> str:
        return validar_email(valor)

    @field_validator("senha")
    @classmethod
    def validar_senha_formato(cls, valor: str) -> str:
        return validar_senha(valor)


class CadastroPublicoResponse(BaseModel):
    mensagem: str = "Se o cadastro puder ser processado, recebera um e-mail de verificacao."


class EmailPublicoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=255)
    turnstile_token: str | None = Field(default=None, max_length=2048)

    @field_validator("email")
    @classmethod
    def validar_formato(cls, valor: str) -> str:
        return validar_email(valor)


class TokenConfirmacaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=256)


class RedefinirSenhaRequest(TokenConfirmacaoRequest):
    nova_senha: str = Field(min_length=8, max_length=1024)

    @field_validator("nova_senha")
    @classmethod
    def validar_senha_nova(cls, valor: str) -> str:
        return validar_senha(valor)

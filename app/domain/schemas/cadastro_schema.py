"""Contrato publico do cadastro. O cliente nunca informa seu proprio perfil."""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.security import password_exceeds_bcrypt_limit

class CadastroPublicoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=3, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    senha: str = Field(min_length=8, max_length=1024)

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, valor: str) -> str:
        valor = valor.strip()
        if len(valor) < 3:
            raise ValueError("Informe um nome com pelo menos 3 caracteres.")
        return valor

    @field_validator("email")
    @classmethod
    def validar_email(cls, valor: str) -> str:
        valor = valor.strip().lower()
        local, separador, dominio = valor.rpartition("@")
        if not separador or not local or "." not in dominio or any(c.isspace() for c in valor):
            raise ValueError("Informe um e-mail valido.")
        return valor

    @field_validator("senha")
    @classmethod
    def validar_senha(cls, valor: str) -> str:
        if password_exceeds_bcrypt_limit(valor):
            raise ValueError("A senha deve ter no maximo 72 bytes UTF-8.")
        return valor

class CadastroPublicoResponse(BaseModel):
    mensagem: str = "Se o cadastro puder ser processado, ele ficara pendente de validacao."

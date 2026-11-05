from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models.enums import PerfilEnum


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    senha: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def validate_email_shape(cls, email: str) -> str:
        local, separator, domain = email.rpartition("@")
        if (
            not separator
            or not local
            or not domain
            or "." not in domain
            or any(character.isspace() for character in email)
        ):
            raise ValueError("Informe um e-mail válido.")
        return email


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class UsuarioAtualResponse(BaseModel):
    """Identidade do dono do token. O JWT so carrega o `sub`; o front precisa
    do perfil para decidir quais telas mostrar (a autorizacao real continua no backend)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    email: str
    perfil: PerfilEnum

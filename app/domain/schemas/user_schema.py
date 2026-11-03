from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models.enums import PerfilEnum


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    perfil: PerfilEnum
    ativo: bool | None


class _RequisicaoAdmin(BaseModel):
    # Campos desconhecidos sao recusados (ex.: "senha_hash" ou "ativo" na criacao).
    model_config = ConfigDict(extra="forbid")


class UsuarioCreateRequest(_RequisicaoAdmin):
    nome: str = Field(max_length=255)
    email: str = Field(min_length=3, max_length=255)
    senha: str = Field(min_length=1, max_length=1024)
    perfil: PerfilEnum

    @field_validator("email")
    @classmethod
    def validar_formato_email(cls, email: str) -> str:
        local, separador, dominio = email.strip().rpartition("@")
        if not separador or not local or "." not in dominio or any(c.isspace() for c in email.strip()):
            raise ValueError("Informe um e-mail valido.")
        return email


class PerfilUpdateRequest(_RequisicaoAdmin):
    perfil: PerfilEnum


class AtivoUpdateRequest(_RequisicaoAdmin):
    ativo: bool


class UsuarioAdminResponse(BaseModel):
    """Visao do ADMIN: inclui e-mail e datas, mas nunca o hash da senha."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    email: str
    perfil: PerfilEnum
    ativo: bool | None
    created_at: datetime | None

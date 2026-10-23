from pydantic import BaseModel, ConfigDict, Field, field_validator


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

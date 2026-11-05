from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import get_db
from app.domain.models.user import User
from app.repositories.user_repository import UserRepository


bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")
AUTHENTICATION_ERROR_DETAIL = "Não foi possível autenticar."


def get_application_settings(request: Request) -> Settings:
    return request.app.state.settings


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=AUTHENTICATION_ERROR_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    configured_settings: Settings = Depends(get_application_settings),
) -> User:
    """Validate an application-signed access token and load its active user."""
    if credentials is None:
        raise _unauthorized()

    secret_key = configured_settings.JWT_SECRET_KEY
    if not secret_key:
        # A missing application secret is a configuration failure, not bad input.
        raise RuntimeError("JWT_SECRET_KEY não está configurada.")
    if configured_settings.JWT_ALGORITHM != "HS256":
        raise RuntimeError("JWT_ALGORITHM deve ser HS256.")

    try:
        payload = jwt.decode(
            credentials.credentials,
            secret_key,
            algorithms=["HS256"],
            options={"verify_exp": False, "verify_iat": False},
        )
        if not isinstance(payload, dict):
            raise ValueError("Invalid token payload")
        subject = payload.get("sub")
        issued_at = payload.get("iat")
        expires_at = payload.get("exp")

        if (
            not isinstance(subject, str)
            or type(issued_at) is not int
            or type(expires_at) is not int
        ):
            raise ValueError("Invalid token claims")

        user_id = UUID(subject)
        now = datetime.now(timezone.utc).timestamp()
        if issued_at > now or expires_at <= issued_at or expires_at <= now:
            raise ValueError("Invalid token times")
    except (JWTError, TypeError, ValueError):
        raise _unauthorized() from None

    # Keep persistence outside the token-validation handler: database failures
    # must remain server errors, never be mistaken for invalid credentials.
    user = UserRepository(db).get_by_id(user_id)
    if user is None or user.ativo is not True:
        raise _unauthorized()
    return user

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    password_exceeds_bcrypt_limit,
    verify_password,
    verify_password_against_dummy,
)
from app.repositories.user_repository import UserRepository


class AuthenticationError(Exception):
    """Raised when credentials are invalid or the account is inactive."""


class AuthService:
    def __init__(self, db: Session, configured_settings: Settings) -> None:
        self.users = UserRepository(db)
        self.configured_settings = configured_settings

    def authenticate(self, email: str, password: str) -> str:
        if password_exceeds_bcrypt_limit(password):
            verify_password_against_dummy()
            raise AuthenticationError

        user = self.users.get_by_email(email)
        if user is None:
            verify_password_against_dummy()
            raise AuthenticationError

        password_is_valid = verify_password(password, user.senha_hash)
        if not password_is_valid or not user.ativo:
            raise AuthenticationError

        return create_access_token(str(user.id), self.configured_settings)

from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from app.core.config import Settings


_password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
MAX_BCRYPT_PASSWORD_BYTES = 72
_DUMMY_PASSWORD = "fixed-dummy-password-for-login-timing"
_DUMMY_PASSWORD_HASH = "$2b$12$/tsDQcGPjuZPZZGMC37owO/AzJYYBJ7vRb0MTRZZWlUtCqo74U20C"


def password_exceeds_bcrypt_limit(plain_password: str) -> bool:
    try:
        return len(plain_password.encode("utf-8")) > MAX_BCRYPT_PASSWORD_BYTES
    except UnicodeEncodeError:
        return True


def hash_password(plain_password: str) -> str:
    if password_exceeds_bcrypt_limit(plain_password):
        raise ValueError("A senha deve ter no máximo 72 bytes em UTF-8.")
    return _password_context.hash(plain_password)


def verify_password(plain_password: str, stored_hash: str) -> bool:
    if password_exceeds_bcrypt_limit(plain_password):
        return False
    try:
        return _password_context.verify(plain_password, stored_hash)
    except (UnknownHashError, TypeError, ValueError):
        return False


def verify_password_against_dummy() -> None:
    verify_password(_DUMMY_PASSWORD, _DUMMY_PASSWORD_HASH)


def create_access_token(subject: str, configured_settings: Settings) -> str:
    secret_key = configured_settings.JWT_SECRET_KEY
    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY não está configurada.")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(
        minutes=configured_settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": subject, "iat": now, "exp": expires_at},
        secret_key,
        algorithm=configured_settings.JWT_ALGORITHM,
    )

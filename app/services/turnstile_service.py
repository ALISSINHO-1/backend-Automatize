"""Valida Cloudflare Turnstile no servidor. Falha fechada por padrao."""
import httpx
from app.core.config import Settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def valida_turnstile(token: str | None, settings: Settings) -> bool:
    secret = settings.TURNSTILE_SECRET_KEY
    if not secret or not token or len(token) > 2048:
        return False
    try:
        with httpx.Client(timeout=5) as client:
            response = client.post(
                VERIFY_URL,
                data={
                    "secret": secret.get_secret_value(),
                    "response": token,
                },
            )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError):
        return False
    if not isinstance(result, dict) or result.get("success") is not True:
        return False
    hostname = settings.TURNSTILE_EXPECTED_HOSTNAME
    if hostname and result.get("hostname") != hostname:
        return False
    return True

"""Fail closed before any local integration fixture/seed/restore write."""
from app.core.config import validate_database_url
from app.core.postgres_tls import parameters_from_url
from sqlalchemy.engine import make_url


def require_isolated_database(value: str) -> str:
    try:
        normalized = validate_database_url(value)
        parsed = make_url(normalized)
        effective = parameters_from_url(parsed)
        if (effective.get("host") not in {"localhost", "127.0.0.1", "::1"}
                or not effective.get("port")
                or "test" not in (effective.get("dbname") or "").lower()
                or effective.get("hostaddr") not in {None, "127.0.0.1", "::1"}):
            raise ValueError
    except Exception:
        raise ValueError("Use PostgreSQL descartavel local com porta explicita e nome contendo test.") from None
    return normalized

"""Validate the effective psycopg2/libpq options without opening a connection."""
from __future__ import annotations

from collections.abc import Mapping
from ipaddress import ip_address
import os
from typing import Any

from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy.engine import URL


_OPTIONS = frozenset({
    "host", "hostaddr", "port", "dbname", "user", "password", "sslmode",
    "sslrootcert", "sslcert", "sslkey", "sslpassword", "sslcrl", "sslcrldir",
    "ssl_min_protocol_version", "ssl_max_protocol_version", "sslnegotiation",
    "connect_timeout", "application_name", "options", "keepalives",
    "keepalives_idle", "keepalives_interval", "keepalives_count", "tcp_user_timeout",
    "target_session_attrs", "load_balance_hosts", "channel_binding", "gssencmode",
})
_SECURE_MODES = frozenset({"require", "verify-ca", "verify-full"})


def _local_host(host: str) -> bool:
    if host.lower() == "localhost" or host.startswith(("/", "@")):
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def secure_connect_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed for opaque DSNs/services and enforce TLS on any remote hop.

    Called after SQLAlchemy's own host/multihost precedence and connect_args
    merging. Explicit sslmode also overrides libpq's PGSSLMODE defaults.
    """
    result = dict(parameters)
    if set(result) - _OPTIONS:
        raise ValueError("Parâmetro de conexão PostgreSQL não permitido.")
    if any(not isinstance(value, (str, int)) or isinstance(value, bool) for value in result.values()):
        raise ValueError("Parâmetros de conexão PostgreSQL devem ser escalares.")
    database = str(result.get("dbname", ""))
    if "=" in database or database.lower().startswith(("postgres://", "postgresql://")):
        raise ValueError("DSN aninhado não é permitido em DATABASE_URL.")

    hosts = str(result.get("host", "")).split(",")
    addresses = str(result.get("hostaddr", "")).split(",") if result.get("hostaddr") else []
    # A hostaddr inherited from the environment can change the actual network
    # destination even when host='localhost' was explicitly supplied.
    if not addresses and os.environ.get("PGHOSTADDR"):
        addresses = os.environ["PGHOSTADDR"].split(",")
    remote = (
        any(not _local_host(host) for host in hosts)
        or any(not _local_host(address) for address in addresses)
        or bool(os.environ.get("PGSERVICE"))
    )
    mode = result.get("sslmode")
    if remote:
        if mode is not None and mode not in _SECURE_MODES:
            raise ValueError("DATABASE_URL remota exige sslmode=require, verify-ca ou verify-full.")
        if result.get("gssencmode") == "require":
            raise ValueError("gssencmode=require conflita com a exigência de TLS.")
        result["sslmode"] = mode or "require"
        # GSS encryption otherwise takes precedence over sslmode in libpq.
        result["gssencmode"] = "disable"
    elif mode is not None and mode not in _SECURE_MODES | {"disable", "allow", "prefer"}:
        raise ValueError("sslmode PostgreSQL inválido.")
    return result


def parameters_from_url(url: URL) -> dict[str, Any]:
    # These aliases can change libpq precedence outside the URL's authority.
    if set(url.query) - (_OPTIONS - {"dbname", "user", "password"}):
        raise ValueError("Parâmetro de DATABASE_URL não permitido.")
    for key, value in url.query.items():
        if isinstance(value, tuple) and key not in {"host", "port"}:
            raise ValueError("Parâmetros PostgreSQL conflitantes ou duplicados.")
    try:
        positional, parameters = PGDialect_psycopg2().create_connect_args(url)
    except Exception:
        raise ValueError("Parâmetros de DATABASE_URL inválidos.") from None
    if positional:
        raise ValueError("DSN posicional PostgreSQL não permitido.")
    return secure_connect_parameters(parameters)

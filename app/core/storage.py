"""Compatibility imports for Storage infrastructure, initialized on demand."""

from functools import cache

from supabase import Client

from app.infrastructure.storage.supabase_storage import create_supabase_client


@cache
def _legacy_client() -> Client:
    return create_supabase_client()


def __getattr__(name: str) -> Client:
    # Preserve `from app.core.storage import supabase` without requiring
    # Storage credentials when the module is merely imported by an API/tool.
    if name == "supabase":
        return _legacy_client()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

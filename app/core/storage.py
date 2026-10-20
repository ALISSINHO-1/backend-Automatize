from __future__ import annotations

from supabase import Client, create_client # type: ignore

from app.core.config import settings


def create_supabase_client() -> Client:
    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL não configurada.")

    if not settings.SUPABASE_KEY:
        raise RuntimeError("SUPABASE_KEY não configurada.")

    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_KEY,
    )


supabase: Client = create_supabase_client()

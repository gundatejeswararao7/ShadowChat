"""
Supabase client provider for ShadowChat.
"""
from typing import Optional
from supabase import create_client, Client
from . import config

_supabase_client: Optional[Client] = None


def get_supabase() -> Client:
    """Return a singleton Supabase client instance."""
    global _supabase_client
    if _supabase_client is None:
        if not config.SUPABASE_URL or not config.SUPABASE_KEY:
            raise RuntimeError(
                "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in your .env file."
            )
        _supabase_client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _supabase_client


def get_db() -> Client:
    """FastAPI dependency yielding the Supabase client."""
    return get_supabase()

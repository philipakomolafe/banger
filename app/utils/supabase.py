import os
from supabase import create_client, Client

_supabase_anon: Client | None = None
_supabase_admin: Client | None = None


def get_supabase(admin: bool) -> Client:
    global _supabase_anon, _supabase_admin

    url = os.environ["SUPABASE_URL"]

    if admin:
        if _supabase_admin is None:
            key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
            _supabase_admin = create_client(url, key)
        return _supabase_admin

    if _supabase_anon is None:
        key = os.environ["SUPABASE_ANON_KEY"]
        _supabase_anon = create_client(url, key)
    return _supabase_anon
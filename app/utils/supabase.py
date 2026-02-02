"""
Supabase client utilities with connection handling.
"""

import os
import logging
from functools import lru_cache
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Don't cache clients to avoid SSL connection issues
_admin_client: Client = None
_anon_client: Client = None


def get_supabase(admin: bool = False) -> Client:
    """
    Get a Supabase client.
    admin=True uses service role key (bypasses RLS).
    admin=False uses anon key (respects RLS).
    """
    global _admin_client, _anon_client
    
    url = os.environ.get("SUPABASE_URL", "").strip()
    
    if not url:
        raise ValueError("SUPABASE_URL not configured")
    
    if admin:
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY not configured")
        # Create fresh client each time to avoid SSL issues
        return create_client(url, key)
    else:
        key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
        if not key:
            raise ValueError("SUPABASE_ANON_KEY not configured")
        return create_client(url, key)


def get_supabase_with_retry(admin: bool = False, retries: int = 3) -> Client:
    """Get Supabase client with retry logic for transient SSL errors."""
    import time
    
    last_error = None
    for attempt in range(retries):
        try:
            return get_supabase(admin=admin)
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
                logger.warning(f"Supabase connection retry {attempt + 1}/{retries}: {e}")
    
    raise last_error
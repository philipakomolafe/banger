"""
Usage tracking and paywall logic for Banger.
Free: 3 generations/day
Paid: unlimited
"""
from datetime import datetime, timezone
from typing import Optional, Tuple
import logging
import time

logger = logging.getLogger(__name__)

FREE_DAILY_LIMIT = 3


def _today_key() -> str:
    """Get today's date as a string key."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_admin_client():
    """Get admin client with import to avoid circular imports."""
    from app.utils.supabase import get_supabase
    return get_supabase(admin=True)


def _safe_query(query_fn, default=None, retries=2):
    """Execute a query with retry logic for transient SSL errors."""
    last_error = None
    for attempt in range(retries):
        try:
            return query_fn()
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # Retry on SSL/connection errors
            if 'ssl' in error_str or 'connection' in error_str or 'timeout' in error_str:
                if attempt < retries - 1:
                    time.sleep(0.3 * (attempt + 1))
                    logger.warning(f"Retrying query (attempt {attempt + 2}/{retries}): {e}")
                    continue
            # Non-retryable error
            break
    
    logger.warning(f"Query failed after {retries} attempts: {last_error}")
    return default


def get_user_usage(user_id: str) -> dict:
    """Get user's usage data from Supabase."""
    def query():
        admin = _get_admin_client()
        result = admin.table("user_usage").select("*").eq("user_id", user_id).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
        return {}
    
    return _safe_query(query, default={})


def get_user_subscription(user_id: str) -> dict:
    """Get user's subscription status from Supabase."""
    def query():
        admin = _get_admin_client()
        result = admin.table("subscriptions").select("*").eq("user_id", user_id).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
        return {}
    
    return _safe_query(query, default={})


def is_user_paid(user_id: str) -> bool:
    """Check if user has an active paid subscription."""
    sub = get_user_subscription(user_id)
    return sub.get("status") == "active"


def get_daily_generations(user_id: str) -> int:
    """Get how many generations user has used today."""
    usage = get_user_usage(user_id)
    today = _today_key()
    
    if usage.get("last_generation_date") != today:
        return 0
    
    return usage.get("daily_generations", 0)


def can_generate(user_id: str) -> Tuple[bool, int, str]:
    """
    Check if user can generate.
    Returns: (can_generate, remaining, reason)
    """
    if is_user_paid(user_id):
        return True, -1, "unlimited"  # -1 means unlimited
    
    used = get_daily_generations(user_id)
    remaining = FREE_DAILY_LIMIT - used
    
    if remaining > 0:
        return True, remaining, "free_tier"
    
    return False, 0, "limit_reached"


def increment_usage(user_id: str) -> int:
    """
    Increment user's daily generation count.
    Returns new count.
    """
    today = _today_key()
    usage = get_user_usage(user_id)
    
    # Reset if new day
    if usage.get("last_generation_date") != today:
        new_count = 1
    else:
        new_count = usage.get("daily_generations", 0) + 1
    
    def update():
        admin = _get_admin_client()
        admin.table("user_usage").upsert(
            {
                "user_id": user_id,
                "daily_generations": new_count,
                "last_generation_date": today,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id",
        ).execute()
        return new_count
    
    result = _safe_query(update, default=new_count)
    return result if result is not None else new_count


def get_usage_status(user_id: Optional[str]) -> dict:
    """Get full usage status for a user."""
    if not user_id:
        return {
            "is_paid": False,
            "daily_limit": FREE_DAILY_LIMIT,
            "used_today": 0,
            "remaining": FREE_DAILY_LIMIT,
            "can_generate": True,
        }
    
    is_paid = is_user_paid(user_id)
    used = get_daily_generations(user_id)
    
    if is_paid:
        return {
            "is_paid": True,
            "daily_limit": -1,
            "used_today": used,
            "remaining": -1,
            "can_generate": True,
        }
    
    remaining = max(0, FREE_DAILY_LIMIT - used)
    return {
        "is_paid": False,
        "daily_limit": FREE_DAILY_LIMIT,
        "used_today": used,
        "remaining": remaining,
        "can_generate": remaining > 0,
    }
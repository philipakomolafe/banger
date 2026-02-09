"""
API routes module - HTTP endpoints for the Banger application.
"""

import os
import time
import asyncio
import logging
import traceback
from typing import List, Optional
from datetime import datetime, timezone

import anyio
from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel

from app.core.x_client import (
    post_to_x,
    _tweet_url,
    build_intent_url,
    remaining_posts_this_month,
    record_post_to_ledger,
    extract_tweet_id_from_url,
)
from app.core import generator as gen
from app.utils.email import send_email
from app.utils.supabase import get_supabase
from app.utils.cache import get_cached_options, set_cached_options, append_perf, read_perf_entries
from app.utils.usage import can_generate, increment_usage, get_usage_status

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["api"])


def _get_user_id_from_request(request: Request) -> Optional[str]:
    """
    Extract user_id from Bearer token via Supabase Auth.
    Returns None if not authenticated (allows anonymous usage if desired).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        return None

    try:
        supabase = get_supabase(admin=False)
        result = supabase.auth.get_user(token)
        return result.user.id if result.user else None
    except Exception as e:
        logger.warning(f"Failed to get user from token: {e}")
        return None


def _save_post_to_supabase(
    user_id: str,
    text: str,
    method: str,
    tweet_id: Optional[str] = None,
    tweet_url: Optional[str] = None,
) -> None:
    """Save a post entry to Supabase post_ledger table."""
    if not user_id:
        return

    try:
        from datetime import datetime, timezone
        from app.core.x_client import _month_key

        now = datetime.now(timezone.utc)
        mk = _month_key()
        norm_text = text.strip().lower()[:500]

        # Create a stable ledger_key from method + timestamp
        ts_ms = int(now.timestamp() * 1000)
        ledger_key = f"{method}_{ts_ms}"

        admin = get_supabase(admin=True)
        
        # Upsert record.
        admin.table("post_ledger").insert(
            {
                "user_id": user_id,
                "ledger_key": ledger_key,
                "ts": now.isoformat(),
                "month": mk,
                "norm_text": norm_text,
                "method": method,
                "tweet_id": tweet_id,
                "tweet_url": _tweet_url(tweet_id) if tweet_id else None,
            }
        ).execute()

        logger.info(f"Saved post to Supabase for user_id={user_id}, ledger_key={ledger_key}")


    except Exception as e:
        logger.error(f"Failed to save post to Supabase: {e}\n{traceback.format_exc()}")


def _save_perf_to_supabase(
    user_id: str,
    mode: str,
    cache_hit: bool,
    gen_time_ms: float,
    options_count: int,
) -> None:
    """Save a perf entry to Supabase perf_entries table."""
    if not user_id:
        return

    try:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)

        admin = get_supabase(admin=True)
        admin.table("perf_entries").insert(
            {
                "user_id": user_id,
                "ts": now.isoformat(),
                "mode": mode,
                "cache_hit": cache_hit,
                "gen_time_ms": gen_time_ms,
                "options_count": options_count,
            }
        ).execute()
    except Exception as e:
        logger.error(f"Failed to save perf to Supabase: {e}\n{traceback.format_exc()}")


class GenerateRequest(BaseModel):
    today_context: Optional[str] = None
    current_mood: Optional[str] = None
    optional_angle: Optional[str] = None


class GenerateResponse(BaseModel):
    mode: str
    remaining_writes: int
    options: List[str]
    gen_time_ms: float
    cache_hit: bool
    # Add usage info
    usage: Optional[dict] = None


class PostRequest(BaseModel):
    text: str
    method: str = "manual"  # 'api' | 'manual' | 'community'
    tweet_url: Optional[str] = None


class PostResponse(BaseModel):
    success: bool
    tweet_id: Optional[str] = None
    error: Optional[str] = None
    remaining: int
    intent_url: Optional[str] = None


class EmailRequest(BaseModel):
    subject: str
    options: List[str]
    to_email: str | None = None  # Optional override for recipient email

class WaitlistRequest(BaseModel):
    email: str

# If the user wants to just record a post without posting.
class RecordRequest(PostRequest):
    pass

@router.get("/config")
def get_config():
    """Get application configuration."""
    return {
        "remaining_writes": remaining_posts_this_month(),
        "community_url": os.environ.get("X_COMMUNITY_URL"),
        "supabase_url": os.environ.get("SUPABASE_URL"),
        "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY"),
    }


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, request: Request, response: Response):
    """Generate post options using AI."""
    t0 = time.perf_counter()

    user_id = _get_user_id_from_request(request)
    
    # PAYWALL CHECK
    if user_id:
        allowed, remaining, reason = can_generate(user_id)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "limit_reached",
                    "message": "You've used all 3 free generations today. Upgrade to continue.",
                    "checkout_url": os.environ.get("LEMONSQUEEZY_CHECKOUT_URL", ""),
                }
            )
        
    else:
        raise HTTPException(
            status_code=401,
            detail= "Authentication required"
        )

    today_context = (req.today_context or "").strip()
    current_mood = (req.current_mood or "").strip()
    optional_angle = (req.optional_angle or "").strip()

    if not all([today_context, current_mood, optional_angle]):
        raise HTTPException(status_code=400, detail="All fields required")

    cache_hit = False
    try:
        mode = gen.pick_mode_for_today()

        daily_context = {
            "today_context": today_context or None,
            "current_mood": current_mood or None,
            "optional_angle": optional_angle or None,
        }
        logger.info(f"Daily context: {daily_context}")

        prompt = gen.build_prompt(mode, daily_context)
        logger.info(f"Prompt built, length: {len(prompt)}")

        cache_key = (mode, today_context, current_mood, optional_angle)
        cached = get_cached_options(cache_key)
        
        if cached:
            cache_hit = True
            total_ms = (time.perf_counter() - t0) * 1000.0

            response.headers["X-Gen-Time-Ms"] = f"{total_ms:.1f}"
            response.headers["X-Cache-Hit"] = "1"

            # Local perf log
            append_perf({
                "ts": datetime.now(timezone.utc).isoformat(),
                "mode": mode,
                "cache_hit": True,
                "gen_time_ms": round(total_ms, 1),
                "options_count": len(cached),
            })

            # Supabase perf log
            _save_perf_to_supabase(user_id, mode, True, round(total_ms, 1), len(cached))

            return GenerateResponse(
                mode=mode,
                remaining_writes=remaining_posts_this_month(),
                options=cached,
                gen_time_ms=round(total_ms, 1),
                cache_hit=True,
                usage=get_usage_status(user_id),
            )

        async def _one_call() -> str:
            return (await anyio.to_thread.run_sync(gen.generate_human_post, prompt, mode)).strip()

        # also adjust the range lenght from 2 -> 3.
        results = await asyncio.gather(*[_one_call() for _ in range(2)], return_exceptions=True)

        options: List[str] = []
        seen = set()
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"Generation call failed: {r}")
                continue
            if r and r not in seen:
                seen.add(r)
                options.append(r)

        extra_tries = 1  # 2
        while len(options) < 2 and extra_tries > 0:  # options initial length < 3
            extra_tries -= 1
            try:
                post = (await anyio.to_thread.run_sync(gen.generate_human_post, prompt, mode)).strip()
                if post and post not in seen:
                    seen.add(post)
                    options.append(post)
            except Exception as e:
                logger.warning(f"Extra generation try failed: {e}\n{traceback.format_exc()}")

        if not options:
            raise HTTPException(status_code=500, detail="Generation failed")

        set_cached_options(cache_key, options)

        total_ms = (time.perf_counter() - t0) * 1000.0
        response.headers["X-Gen-Time-Ms"] = f"{total_ms:.1f}"
        response.headers["X-Cache-Hit"] = "0"
        response.headers["X-Options-Count"] = str(len(options))

        # Local perf log
        append_perf({
            "ts": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "cache_hit": False,
            "gen_time_ms": round(total_ms, 1),
            "options_count": len(options),
        })

        # Supabase perf log
        _save_perf_to_supabase(user_id, mode, False, round(total_ms, 1), len(options))

        # INCREMENT USAGE AFTER SUCCESS 
        if user_id:
            increment_usage(user_id)
        
        usage = get_usage_status(user_id)
        
        return GenerateResponse(
            mode=mode,
            remaining_writes=remaining_posts_this_month(),
            options=options,
            gen_time_ms=round(total_ms, 1),
            cache_hit=False,
            usage=usage,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /api/generate: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/post", response_model=PostResponse)
def post_to_x_api(req: PostRequest, request: Request):
    """Post content to X (Twitter)."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    method = (req.method or "manual").lower()
    if method not in ("api", "manual", "community"):
        raise HTTPException(status_code=400, detail="method must be 'api', 'manual', or 'community'")

    user_id = _get_user_id_from_request(request)

    # API posting: consumes X write quota (and whatever your post_to_x tracks)
    if method == "api" and request.headers.get("x-use-x-api") != "1":
        raise HTTPException(status_code=400, detail="To post via API, set method='api' and include 'X-Use-X-API: 1' header")

    if method == "api":
        result = post_to_x(text)
        tweet_id = result.get("tweet_id")

        # Save to Supabase
        _save_post_to_supabase(user_id, text, method, tweet_id=tweet_id, tweet_url=_tweet_url(tweet_id) if tweet_id is not None else None)

        if result.get("success"):
            return PostResponse(
                success=True,
                tweet_id=tweet_id,
                remaining=result.get("remaining", remaining_posts_this_month()),
                intent_url=build_intent_url(text),
            )

        return PostResponse(
            success=False,
            error=result.get("error", "Unknown error"),
            remaining=result.get("remaining", remaining_posts_this_month()),
            intent_url=build_intent_url(text),
        )

    # Manual/community: do NOT call the API at all (no write quota usage)
    tweet_url = req.tweet_url or ""
    tweet_id = extract_tweet_id_from_url(tweet_url)
    
    record_post_to_ledger(text, method=method, tweet_id=tweet_id, tweet_url=tweet_url)

    # Save to Supabase with tweet_id if tweet_url is provided
    _save_post_to_supabase(user_id, text, method, tweet_id=tweet_id, tweet_url=tweet_url)

    return PostResponse(
        success=True,
        tweet_id=None,
        remaining=remaining_posts_this_month(),
        intent_url=build_intent_url(text),
    )

@router.post("/email")
def email_options(req: EmailRequest):
    """Send post options via email."""
    recipient_email = req.to_email or os.environ.get("TO_EMAIL")
    if not recipient_email:
        raise HTTPException(status_code=500, detail="Recipient email not configured (set TO_EMAIL env var)")
    
    body = ("\n\n---\n\n").join(
        [f"Option {i+1}: \n{opt}" for i, opt in enumerate(req.options)]
    )
    ok = send_email(req.subject, body, to_email=recipient_email)
    if not ok:
        raise HTTPException(
            status_code=500, 
            detail="Email not configured (set SMTP_* and EMAIL_* env vars)"
        )
    return {"ok": True}

@router.post("/waitlist")
async def join_waitlist(req: WaitlistRequest):
    """Join the waitlist by providing an email."""
    email = (req.email or "").strip().lower()

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address.")
    try:
        supabase = get_supabase(admin=True)
        data = {
            "email": email,
        }
        supabase.table("waitlist").upsert(data).execute()
        return {"ok": True}
    
    except Exception as e:
        logger.error(f"Error joining waitlist: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to join waitlist")



@router.post("/record")
def record_tweet_url(req: RecordRequest, request: Request):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    method = (req.method or "manual").lower()
    if method not in ("manual", "community"):
        raise HTTPException(status_code=400, detail="method must be 'manual' or 'community'")

    user_id = _get_user_id_from_request(request)
    tid = extract_tweet_id_from_url((req.tweet_url or "").strip())

    # Local ledger (existing behavior)
    record_post_to_ledger(text, method=method, tweet_id=tid, tweet_url=req.tweet_url)

    # Supabase ledger
    _save_post_to_supabase(user_id, text, method, tweet_id=tid, tweet_url=req.tweet_url)

    return {"ok": True, "tweet_id": tid}



@router.get("/perf")
def get_perf(limit: int = 20):
    """Returns last N perf entries for comparison."""
    return {"items": read_perf_entries(limit)}

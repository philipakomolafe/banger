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
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.core.x_client import post_to_x, build_intent_url, remaining_posts_this_month, record_post_to_ledger
from app.core import generator as gen
from app.utils.email import send_email
from app.utils.cache import get_cached_options, set_cached_options, append_perf, read_perf_entries

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["api"])


# === Pydantic Models ===

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


class PostRequest(BaseModel):
    text: str
    method: str = "api"  # 'api' | 'manual' | 'community'


class PostResponse(BaseModel):
    success: bool
    tweet_id: Optional[str] = None
    error: Optional[str] = None
    remaining: int
    intent_url: Optional[str] = None


class EmailRequest(BaseModel):
    subject: str
    options: List[str]


# === Routes ===

@router.get("/config")
def get_config():
    """Get application configuration."""
    return {
        "remaining_writes": remaining_posts_this_month(),
        "community_url": os.environ.get("X_COMMUNITY_URL"),
    }


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, response: Response):
    """Generate post options using AI."""
    t0 = time.perf_counter()

    today_context = (req.today_context or "").strip()
    current_mood = (req.current_mood or "").strip()
    optional_angle = (req.optional_angle or "").strip()

    if not all([today_context, current_mood, optional_angle]):
        raise HTTPException(
            status_code=400, 
            detail="today_context, current_mood, and optional_angle are required"
        )

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
            append_perf({
                "ts": datetime.now(timezone.utc).isoformat(),
                "mode": mode,
                "cache_hit": True,
                "gen_time_ms": round(total_ms, 1),
            })

            return GenerateResponse(
                mode=mode,
                remaining_writes=remaining_posts_this_month(),
                options=cached,
                gen_time_ms=round(total_ms, 1),
                cache_hit=True,
            )

        async def _one_call() -> str:
            return (await anyio.to_thread.run_sync(gen.generate_human_post, prompt, mode)).strip()

        results = await asyncio.gather(*[_one_call() for _ in range(3)], return_exceptions=True)

        options: List[str] = []
        seen = set()
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"Generation call failed: {r}")
                continue
            if r and r not in seen:
                seen.add(r)
                options.append(r)

        extra_tries = 2
        while len(options) < 3 and extra_tries > 0:
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
        append_perf({
            "ts": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "cache_hit": False,
            "gen_time_ms": round(total_ms, 1),
        })

        return GenerateResponse(
            mode=mode,
            remaining_writes=remaining_posts_this_month(),
            options=options,
            gen_time_ms=round(total_ms, 1),
            cache_hit=False,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /api/generate: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/post", response_model=PostResponse)
def post_to_x_api(req: PostRequest):
    """Post content to X (Twitter)."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    method = req.method.lower()
    if method not in ("api", "manual", "community"):
        raise HTTPException(status_code=400, detail="method must be 'api', 'manual', or 'community'")

    result = post_to_x(text)
    
    if method == "api":
        if result["success"]:   
            return PostResponse(
                success=True,
                tweet_id=result["tweet_id"],
                remaining=result["remaining"],
                intent_url=build_intent_url(text),
            )

    elif method in ["manual", "community"]:
        record_post_to_ledger(text, method=method, tweet_id=result.get("tweet_id"))  
        return PostResponse(
            success=True,   
            tweet_id=result.get("tweet_id"),
            remaining=result["remaining"],
            intent_url=build_intent_url(text),
        )  

    return PostResponse(
        success=False,
        error=result["error"],
        remaining=result["remaining"],
        intent_url=build_intent_url(text),
    )


@router.post("/email")
def email_options(req: EmailRequest):
    """Send post options via email."""
    body = ("\n\n---\n\n").join([o.strip() for o in req.options if o.strip()])
    ok = send_email(req.subject, body)
    if not ok:
        raise HTTPException(
            status_code=500, 
            detail="Email not configured (set SMTP_* and EMAIL_* env vars)"
        )
    return {"ok": True}


@router.get("/perf")
def get_perf(limit: int = 20):
    """Returns last N perf entries for comparison."""
    return {"items": read_perf_entries(limit)}

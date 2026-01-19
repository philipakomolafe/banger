import os
import traceback
import logging
import json
from typing import List, Optional, Tuple, Dict
from datetime import datetime, timezone
from pathlib import Path
import time
import asyncio
import anyio
from fastapi import FastAPI, HTTPException, Response  # <-- add Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Local imports
from api import post_to_x, build_intent_url, remaining_posts_this_month, record_post_to_ledger
import main as gen
import importlib
from email_utils import send_email

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Try to import your generation pipeline from main.py
try:
    gen = importlib.import_module("main")
    logger.info("✓ Imported main.py")
except Exception as e:
    logger.error(f"✗ Failed to import main.py: {e}")
    raise

app = FastAPI(title="Banger API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files.
web_path = Path(__file__).parent / "web"
if web_path.exists():
    app.mount("/web", StaticFiles(directory=web_path, html=True), name="web")

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

# --- Simple in-memory cache for faster repeated clicks ---
# Keyed by (mode, today_context, current_mood, optional_angle)
_GEN_CACHE: Dict[Tuple[str, str, str, str], Tuple[float, List[str]]] = {}
_GEN_CACHE_TTL_SECONDS = 120  # 2 minutes (adjust as you like)

def _get_cached_options(key: Tuple[str, str, str, str]) -> Optional[List[str]]:
    item = _GEN_CACHE.get(key)
    if not item:
        return None
    ts, options = item
    if (time.time() - ts) > _GEN_CACHE_TTL_SECONDS:
        _GEN_CACHE.pop(key, None)
        return None
    return options

def _set_cached_options(key: Tuple[str, str, str, str], options: List[str]) -> None:
    _GEN_CACHE[key] = (time.time(), options)

# Perf logging
_PERF_LOG_PATH = Path(__file__).parent / "data" / "perf_log.jsonl"

def _append_perf(entry: Dict) -> None:
    try:
        _PERF_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PERF_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Failed to write perf log: {e}")

@app.get("/api/config")
def get_config():
    return {
        "remaining_writes": remaining_posts_this_month(),
        "community_url": os.environ.get("X_COMMUNITY_URL"),
    }

@app.post("/api/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, response: Response):
    t0 = time.perf_counter()

    today_context = (req.today_context or "").strip()
    current_mood = (req.current_mood or "").strip()
    optional_angle = (req.optional_angle or "").strip()

    if not all([today_context, current_mood, optional_angle]):
        raise HTTPException(status_code=400, detail="today_context, current_mood, and optional_angle are required")

    for fn in ("pick_mode_for_today", "build_prompt", "generate_human_post"):
        if not hasattr(gen, fn):
            raise HTTPException(status_code=500, detail=f"Missing function in main.py: {fn}")

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
        cached = _get_cached_options(cache_key)
        if cached:
            cache_hit = True
            total_ms = (time.perf_counter() - t0) * 1000.0

            response.headers["X-Gen-Time-Ms"] = f"{total_ms:.1f}"
            response.headers["X-Cache-Hit"] = "1"
            _append_perf({
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

        _set_cached_options(cache_key, options)

        total_ms = (time.perf_counter() - t0) * 1000.0
        response.headers["X-Gen-Time-Ms"] = f"{total_ms:.1f}"
        response.headers["X-Cache-Hit"] = "0"
        _append_perf({
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

@app.post("/api/post", response_model=PostResponse)
def post_to_x_api(req: PostRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    method = req.method.lower()
    if method not in ("api", "manual", "community"):
        raise HTTPException(status_code=400, detail="method must be 'api', 'manual', or 'community'")

    if method == "api":
        result = post_to_x(text)

        if result["success"]:
            return PostResponse(
                success=True,
                tweet_id=result["tweet_id"],
                remaining=result["remaining"],
                intent_url=build_intent_url(text),
            )
        return PostResponse(
            success=False,
            error=result["error"],
            remaining=result["remaining"],
            intent_url=build_intent_url(text),
        )

    else:
        record_post_to_ledger(text, method=method)
        return PostResponse(
            success=True,
            tweet_id=None,
            remaining=remaining_posts_this_month(),
            intent_url=build_intent_url(text),
        )

@app.post("/api/email")
def email_options(req: EmailRequest):
    body = ("\n\n---\n\n").join([o.strip() for o in req.options if o.strip()])
    ok = send_email(req.subject, body)
    if not ok:
        raise HTTPException(status_code=500, detail="Email not configured (set SMTP_* and EMAIL_* env vars)")
    return {"ok": True}

@app.get("/api/perf")
def get_perf(limit: int = 20):
    # Returns last N perf entries so you can compare "before vs after"
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    if not _PERF_LOG_PATH.exists():
        return {"items": []}

    lines = _PERF_LOG_PATH.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:]
    items = []
    for line in tail:
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return {"items": items}
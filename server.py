import os
import traceback
import logging
import json
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException
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

@app.get("/api/config")
def get_config():
    return {
        "remaining_writes": remaining_posts_this_month(),
        "community_url": os.environ.get("X_COMMUNITY_URL"),
    }

@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    # Ensure required functions exist
    for fn in ("pick_mode_for_today", "build_prompt", "generate_human_post"):
        if not hasattr(gen, fn):
            raise HTTPException(status_code=500, detail=f"Missing function in main.py: {fn}")

    try:
        mode = gen.pick_mode_for_today()
        logger.info(f"Mode selected: {mode}")
        
        # Build the prompt with explicit context
        daily_context = {
            "today_context": (req.today_context or "").strip() or None,
            "current_mood": (req.current_mood or "").strip() or None,
            "optional_angle": (req.optional_angle or "").strip() or None,
        }
        logger.info(f"Daily context: {daily_context}")
        
        prompt = gen.build_prompt(mode, daily_context)
        logger.info(f"Prompt built, length: {len(prompt)}")

        # Generate up to 3 options, allow duplicates filtering
        options = []
        seen = set()
        for attempt in range(3):  # try up to 3 to collect 3 decent ones
            try:
                post = gen.generate_human_post(prompt, mode).strip()
                logger.info(f"Attempt {attempt + 1}: Generated {len(post)} chars")
                if post and post not in seen:
                    seen.add(post)
                    options.append(post)
                if len(options) >= 3:
                    break
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}\n{traceback.format_exc()}")
                continue

        if not options:
            logger.error("No options generated after 3 attempts")
            raise HTTPException(status_code=500, detail="Generation failed after 3 attempts")

        logger.info(f"✓ Generated {len(options)} options")
        return GenerateResponse(
            mode=mode,
            remaining_writes=remaining_posts_this_month(),
            options=options
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

    # If using API method, post via X API (already records to ledger inside post_to_x)
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
    
    # For manual/community: record to ledger using existing helper
    else:
        record_post_to_ledger(text, method=method)
        return PostResponse(
            success=True,
            tweet_id=None,
            remaining=remaining_posts_this_month(),  # unchanged
            intent_url=build_intent_url(text),
        )

@app.post("/api/email")
def email_options(req: EmailRequest):
    body = ("\n\n---\n\n").join([o.strip() for o in req.options if o.strip()])
    ok = send_email(req.subject, body)
    if not ok:
        raise HTTPException(status_code=500, detail="Email not configured (set SMTP_* and EMAIL_* env vars)")
    return {"ok": True}
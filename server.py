import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Local imports
from api import post_to_x, build_intent_url, remaining_posts_this_month
import importlib
from email_utils import send_email

load_dotenv()

# Try to import your generation pipeline from main.py
gen = importlib.import_module("main")

app = FastAPI(title="Banger API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

    mode = gen.pick_mode_for_today()
    # Build the prompt with explicit context
    daily_context = {
        "today_context": (req.today_context or "").strip() or None,
        "current_mood": (req.current_mood or "").strip() or None,
        "optional_angle": (req.optional_angle or "").strip() or None,
    }
    prompt = gen.build_prompt(mode, daily_context)

    # Generate up to 3 options, allow duplicates filtering
    options = []
    seen = set()
    for _ in range(6):  # try up to 6 to collect 3 decent ones
        try:
            post = gen.generate_human_post(prompt, mode).strip()
            if post and post not in seen:
                seen.add(post)
                options.append(post)
            if len(options) >= 3:
                break
        except Exception:
            continue

    if not options:
        raise HTTPException(status_code=500, detail="Generation failed")

    return GenerateResponse(
        mode=mode,
        remaining_writes=remaining_posts_this_month(),
        options=options
    )

@app.post("/api/post", response_model=PostResponse)
def post_to_x_api(req: PostRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

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

@app.post("/api/email")
def email_options(req: EmailRequest):
    body = ("\n\n---\n\n").join([o.strip() for o in req.options if o.strip()])
    ok = send_email(req.subject, body)
    if not ok:
        raise HTTPException(status_code=500, detail="Email not configured (set SMTP_* and EMAIL_* env vars)")
    return {"ok": True}
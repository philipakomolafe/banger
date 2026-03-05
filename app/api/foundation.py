"""Foundational Tier 1 endpoints: git integration, auto drafts, engagement tracking, and feedback loop."""

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.routes import _get_user_id_from_request
from app.core import generator as gen
from app.utils.supabase import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/foundation", tags=["foundation"])

DATA_DIR = Path(__file__).parent.parent.parent / "data"
STATE_PATH = DATA_DIR / "git_autodraft_state.json"
ENGAGEMENT_PATH = DATA_DIR / "engagement_events.jsonl"
FEEDBACK_PATH = DATA_DIR / "draft_feedback.jsonl"


class GitCommit(BaseModel):
    hash: str
    author: str
    date: str
    message: str


class AutoDraftResponse(BaseModel):
    triggered: bool
    reason: str
    commit: Optional[GitCommit] = None
    mode: Optional[str] = None
    options: list[str] = []


class EngagementRequest(BaseModel):
    tweet_url: str
    impressions: int = Field(0, ge=0)
    likes: int = Field(0, ge=0)
    retweets: int = Field(0, ge=0)
    replies: int = Field(0, ge=0)
    bookmarks: int = Field(0, ge=0)


class FeedbackRequest(BaseModel):
    draft_text: str
    score: int = Field(..., ge=1, le=5)
    notes: Optional[str] = None
    commit_hash: Optional[str] = None


def _git_repo_path() -> Path:
    return Path(os.environ.get("BANGER_GIT_REPO", os.getcwd())).resolve()


def _run_git_log(limit: int = 10) -> list[GitCommit]:
    repo = _git_repo_path()
    if not (repo / ".git").exists():
        raise HTTPException(status_code=400, detail=f"No git repository found at {repo}")

    fmt = "%H|%an|%aI|%s"
    cmd = ["git", "-C", str(repo), "log", f"-n{limit}", f"--pretty=format:{fmt}"]
    try:
        out = subprocess.check_output(cmd, text=True)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=f"git log failed: {exc}") from exc

    commits = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) != 4:
            continue
        commits.append(GitCommit(hash=parts[0], author=parts[1], date=parts[2], message=parts[3]))
    return commits


def _read_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


@router.get("/git/commits")
def get_git_commits(limit: int = 10):
    safe_limit = max(1, min(30, limit))
    return {"items": [c.model_dump() for c in _run_git_log(safe_limit)]}


@router.post("/git/auto-draft", response_model=AutoDraftResponse)
def auto_trigger_draft(request: Request):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    commits = _run_git_log(limit=1)
    if not commits:
        return AutoDraftResponse(triggered=False, reason="No commits found")

    latest = commits[0]
    state = _read_state()
    last_seen = state.get(user_id)
    if last_seen == latest.hash:
        return AutoDraftResponse(triggered=False, reason="No new commit since last auto-draft", commit=latest)

    mode = gen.pick_mode_for_today()
    context = {
        "today_context": f"Latest commit: {latest.message}",
        "current_mood": "focused",
        "optional_angle": "share progress update",
    }
    prompt = gen.build_prompt(mode, context)

    options = []
    for _ in range(2):
        options.append(gen.generate_human_post(prompt, mode).strip())

    state[user_id] = latest.hash
    _write_state(state)

    return AutoDraftResponse(
        triggered=True,
        reason="New commit detected and draft suggestions generated",
        commit=latest,
        mode=mode,
        options=[o for o in options if o],
    )


@router.post("/engagement")
def track_engagement(body: EngagementRequest, request: Request):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = {
        "user_id": user_id,
        "tweet_url": body.tweet_url,
        "impressions": body.impressions,
        "likes": body.likes,
        "retweets": body.retweets,
        "replies": body.replies,
        "bookmarks": body.bookmarks,
        "engagement_rate": round(((body.likes + body.retweets + body.replies) / max(body.impressions, 1)) * 100, 3),
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    _append_jsonl(ENGAGEMENT_PATH, payload)

    try:
        admin = get_supabase(admin=True)
        admin.table("engagement_events").insert(payload).execute()
    except Exception as exc:
        logger.warning("Supabase engagement insert skipped/failed: %s", exc)

    return {"ok": True, "item": payload}


@router.get("/engagement")
def list_engagement(request: Request, limit: int = 20):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not ENGAGEMENT_PATH.exists():
        return {"items": []}

    rows = []
    for line in ENGAGEMENT_PATH.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            if item.get("user_id") == user_id:
                rows.append(item)
        except Exception:
            continue

    return {"items": rows[-max(1, min(100, limit)):][::-1]}


@router.post("/feedback")
def submit_feedback(body: FeedbackRequest, request: Request):
    user_id = _get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = {
        "user_id": user_id,
        "draft_text": body.draft_text.strip(),
        "score": body.score,
        "notes": (body.notes or "").strip(),
        "commit_hash": (body.commit_hash or "").strip() or None,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _append_jsonl(FEEDBACK_PATH, payload)

    try:
        admin = get_supabase(admin=True)
        admin.table("draft_feedback").insert(payload).execute()
    except Exception as exc:
        logger.warning("Supabase draft feedback insert skipped/failed: %s", exc)

    return {"ok": True}

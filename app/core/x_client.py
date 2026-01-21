"""
X (Twitter) API module - handles posting and ledger management.
"""

import os
import json
import time
import platform
import subprocess
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import tweepy
from dotenv import load_dotenv

load_dotenv()

# Data paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
LEDGER_PATH = DATA_DIR / "post_ledger.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Rate limiting
MAX_WRITES = int(os.environ.get("MAX_X_WRITES_PER_MONTH", "280"))

# Community URL for manual posting
COMMUNITY_URL = os.environ.get("X_COMMUNITY_URL")


def _load_ledger() -> dict:
    """Load the post ledger from disk."""
    if LEDGER_PATH.exists():
        try:
            return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_ledger(data: dict) -> None:
    """Save the post ledger to disk."""
    LEDGER_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _month_key(ts: float = None) -> str:
    """Get the current month key for tracking monthly usage."""
    dt = datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)
    return dt.strftime("%Y-%m")


def remaining_posts_this_month() -> int:
    """Calculate remaining posts allowed this month."""
    led = _load_ledger()
    mk = _month_key()
    used = len([x for x in led.values() if x.get("month") == mk])
    return max(0, MAX_WRITES - used)


def was_recently_posted(text: str, days: int = 2) -> bool:
    """Check if same text was posted recently (duplicate guard)."""
    led = _load_ledger()
    norm = " ".join((text or "").split())
    cutoff = time.time() - days * 86400
    for rec in led.values():
        if rec.get("norm_text") == norm and rec.get("ts", 0) >= cutoff:
            return True
    return False


def _tweet_url(tweet_id: str) -> str:
    """Build the URL for a tweet."""
    return f"https://x.com/i/web/status/{tweet_id}"


def record_post_to_ledger(text: str, method: str = "manual", tweet_id: str = None) -> None:
    """
    Record any post (api/manual/community) to ledger.
    Only records if not already posted in last 48h (duplicate check).
    
    Args:
        text: The post text
        method: 'api' | 'manual' | 'community'
        tweet_id: Optional tweet ID if available
    """
    text = (text or "").strip()
    if not text:
        return
    
    # Duplicate check: don't record same text twice in 48h
    if was_recently_posted(text, days=2):
        return
    
    led = _load_ledger()
    record_id = f"{method}_{int(time.time() * 1000)}"
    
    led[record_id] = {
        "ts": time.time(),
        "month": _month_key(),
        "norm_text": " ".join(text.split()),
        "method": method,
        "tweet_id": tweet_id,
        "tweet_url": _tweet_url(tweet_id) if tweet_id else None
    }
    _save_ledger(led)


def build_intent_url(tweet_text: str) -> str:
    """Build Twitter web intent URL for manual posting."""
    return f"https://twitter.com/intent/tweet?{urlencode({'text': tweet_text})}"


def post_to_x(tweet_text: str) -> dict:
    """
    Posts directly to X using API v2.
    
    Returns:
        {"success": bool, "tweet_id": str|None, "error": str|None, "remaining": int}
    """
    tweet_text = (tweet_text or "").strip()
    
    if not tweet_text:
        return {"success": False, "tweet_id": None, "error": "empty_text", "remaining": remaining_posts_this_month()}
    
    if len(tweet_text) > 280:
        return {"success": False, "tweet_id": None, "error": "over_280_chars", "remaining": remaining_posts_this_month()}
    
    if was_recently_posted(tweet_text, days=2):
        return {"success": False, "tweet_id": None, "error": "duplicate_guard_48h", "remaining": remaining_posts_this_month()}
    
    if remaining_posts_this_month() <= 0:
        return {"success": False, "tweet_id": None, "error": "monthly_quota_reached", "remaining": 0}

    try:
        client = tweepy.Client(
            bearer_token=os.environ.get("X_BEARER_TOKEN"),
            consumer_key=os.environ.get("X_API_KEY"),
            consumer_secret=os.environ.get("X_API_SECRET"),
            access_token=os.environ.get("X_ACCESS_TOKEN"),
            access_token_secret=os.environ.get("X_ACCESS_SECRET"),
        )
        response = client.create_tweet(text=tweet_text)
        tid = response.data["id"]
        record_post_to_ledger(tweet_text, method="api", tweet_id=tid)
        return {"success": True, "tweet_id": tid, "error": None, "remaining": remaining_posts_this_month()}
    except Exception as e:
        # Common: 403 duplicate, 429 rate limit
        return {"success": False, "tweet_id": None, "error": str(e), "remaining": remaining_posts_this_month()}


def open_community_with_clipboard(tweet_text: str) -> dict:
    """
    Copies text to clipboard and opens the X Community page for manual posting.
    
    Returns:
        {"success": bool, "copied": bool, "url": str}
    """
    text = (tweet_text or "").strip()
    if not text:
        return {"success": False, "copied": False, "url": COMMUNITY_URL or ""}

    copied = False
    try:
        # Windows clipboard
        if platform.system() == "Windows":
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
            proc.communicate(input=text.encode("utf-8"))
            copied = True
    except Exception:
        copied = False

    url = COMMUNITY_URL or "https://twitter.com/communities"
    webbrowser.open(url)
    return {"success": True, "copied": copied, "url": url}

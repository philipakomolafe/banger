import os
import tweepy
from dotenv import load_dotenv
import json
import time
from pathlib import Path
from urllib.parse import urlencode, quote_plus
from datetime import datetime, timezone
import webbrowser
import subprocess
import platform

load_dotenv()

LEDGER_PATH = Path("data/post_ledger.json")
LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)

MAX_WRITES = int(os.environ.get("MAX_X_WRITES_PER_MONTH", "480"))  # leave buffer under 500

def _load_ledger() -> dict:
    if LEDGER_PATH.exists():
        try:
            return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_ledger(data: dict) -> None:
    LEDGER_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _month_key(ts: float = None) -> str:
    dt = datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)
    return dt.strftime("%Y-%m")

def remaining_posts_this_month() -> int:
    led = _load_ledger()
    mk = _month_key()
    used = len([x for x in led.values() if x.get("month") == mk])
    return max(0, MAX_WRITES - used)

def was_recently_posted(text: str, days: int = 2) -> bool:
    led = _load_ledger()
    norm = " ".join((text or "").split())
    cutoff = time.time() - days * 86400
    for rec in led.values():
        if rec.get("norm_text") == norm and rec.get("ts", 0) >= cutoff:
            return True
    return False

def _record_post(tweet_id: str, text: str) -> None:
    led = _load_ledger()
    led[tweet_id] = {
        "ts": time.time(),
        "month": _month_key(),
        "norm_text": " ".join((text or "").split())
    }
    _save_ledger(led)

def build_intent_url(tweet_text: str) -> str:
    # Newlines and special chars safe for web intent
    return f"https://twitter.com/intent/tweet?{urlencode({'text': tweet_text})}"

def post_to_x(tweet_text: str) -> dict:
    """
    Posts directly to X using API v2.
    Returns: {"success": bool, "tweet_id": str|None, "error": str|None, "remaining": int}
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
        _record_post(tid, tweet_text)
        return {"success": True, "tweet_id": tid, "error": None, "remaining": remaining_posts_this_month()}
    except Exception as e:
        # Common: 403 duplicate, 429 rate limit
        return {"success": False, "tweet_id": None, "error": str(e), "remaining": remaining_posts_this_month()}

COMMUNITY_URL = os.environ.get("X_COMMUNITY_URL")  # e.g., https://twitter.com/i/communities/1234567890

def open_community_with_clipboard(tweet_text: str) -> dict:
    """
    Copies text to clipboard and opens the X Community page for manual posting.
    Returns: {"success": bool, "copied": bool, "url": str}
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

    url = COMMUNITY_URL or "https://twitter.com/communities"  # fallback to communities hub
    webbrowser.open(url)
    return {"success": True, "copied": copied, "url": url}


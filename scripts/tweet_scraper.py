"""
Tweet Scraper - Fetches tweets via RSS and builds style profiles.

This script analyzes public writing patterns to generate aggregate
style guidance (without storing actual tweet content).

Usage:
    Set environment variables:
        NITTER_BASE: Nitter instance URL (default: https://nitter.net)
        TARGET_USERS: Comma-separated usernames (e.g., "patio11,levelsio,naval")
        MAX_PER_USER: Max tweets per user (default: 100)
    
    Run:
        python -m scripts.tweet_scraper
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

# Output path
CONFIG_DIR = Path(__file__).parent.parent / "config"
OUTPUT_PATH = CONFIG_DIR / "style_profile.json"

# Regex patterns
URL_RE = re.compile(r"https?://\S+")
WS_RE = re.compile(r"\s+")
SENT_SPLIT_RE = re.compile(r"[.!?]+")


def clean_text(text: str) -> str:
    """Remove URLs and normalize whitespace."""
    text = URL_RE.sub("", text)
    text = WS_RE.sub(" ", text).strip()
    return text


def fetch_rss(rss_url: str, timeout: int = 30) -> str:
    """Fetch RSS feed content."""
    req = Request(
        url=rss_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; banger-style-profiler/1.0)",
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        },
        method="GET",
    )
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_rss_items(xml_text: str, max_items: int) -> list[str]:
    """
    Returns a list of item titles (tweet text usually appears in <title> for Nitter RSS).
    We will immediately transform to metrics and never persist these strings.
    """
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []

    titles: list[str] = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        titles.append(title)
        if len(titles) >= max_items:
            break

    return titles


def percentile(sorted_vals: list[int], p: float) -> int:
    """Calculate percentile value from sorted list."""
    if not sorted_vals:
        return 0
    idx = int(round((len(sorted_vals) - 1) * p))
    return sorted_vals[max(0, min(idx, len(sorted_vals) - 1))]


def text_metrics(text: str) -> dict:
    """Extract style metrics from text."""
    t = clean_text(text)

    char_len = len(t)
    words = [w for w in t.split(" ") if w]
    word_count = len(words)

    # Rough sentence count
    sentences = [s.strip() for s in SENT_SPLIT_RE.split(t) if s.strip()]
    sentence_count = max(1, len(sentences)) if t else 0

    has_question = "?" in t
    has_colon = ":" in t
    has_dash = "—" in t or "-" in t
    has_quotes = '"' in t or """ in t or """ in t or "'" in t
    starts_with_but = t.lower().startswith("but ")
    contains_contrast = any(x in t.lower() for x in (" but ", " however ", " instead ", " rather "))

    return {
        "char_len": char_len,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "has_question": has_question,
        "has_colon": has_colon,
        "has_dash": has_dash,
        "has_quotes": has_quotes,
        "starts_with_but": starts_with_but,
        "contains_contrast": contains_contrast,
    }


def aggregate(metrics: list[dict]) -> dict:
    """Aggregate metrics into a style profile."""
    if not metrics:
        return {"count": 0}

    chars = sorted(m["char_len"] for m in metrics)
    words = sorted(m["word_count"] for m in metrics)
    sentences = sorted(m["sentence_count"] for m in metrics)

    def rate(key: str) -> float:
        return sum(1 for m in metrics if m.get(key)) / len(metrics)

    profile = {
        "count": len(metrics),
        "char_len": {
            "p25": percentile(chars, 0.25),
            "p50": percentile(chars, 0.50),
            "p75": percentile(chars, 0.75),
        },
        "word_count": {
            "p25": percentile(words, 0.25),
            "p50": percentile(words, 0.50),
            "p75": percentile(words, 0.75),
        },
        "sentence_count": {
            "p25": percentile(sentences, 0.25),
            "p50": percentile(sentences, 0.50),
            "p75": percentile(sentences, 0.75),
        },
        "rates": {
            "question": round(rate("has_question"), 3),
            "colon": round(rate("has_colon"), 3),
            "dash": round(rate("has_dash"), 3),
            "quotes": round(rate("has_quotes"), 3),
            "starts_with_but": round(rate("starts_with_but"), 3),
            "contrast_language": round(rate("contains_contrast"), 3),
        },
    }

    # Turn stats into prompt-friendly guidance
    profile["guidance"] = {
        "recommended_char_range": [max(80, profile["char_len"]["p25"]), min(260, profile["char_len"]["p75"])],
        "recommended_sentence_range": [max(1, profile["sentence_count"]["p25"]), min(5, profile["sentence_count"]["p75"])],
        "notes": [
            "Prefer short punchy sentences.",
            "Use contrast sparingly (but/however/instead) when it clarifies a point.",
            "Questions are optional; use when it feels natural.",
        ],
    }

    return profile


def main():
    """Main entry point for tweet scraper."""
    # Inputs
    nitter_base = os.environ.get("NITTER_BASE", "https://nitter.net").rstrip("/")
    users_raw = os.environ.get("TARGET_USERS", "jackfriks,patio11,levelsio,naval")
    per_user = int(os.environ.get("MAX_PER_USER", "100"))

    usernames = [u.strip().lstrip("@") for u in users_raw.split(",") if u.strip()]
    if not usernames:
        raise RuntimeError("TARGET_USERS is empty. Provide comma-separated usernames.")

    all_metrics: list[dict] = []
    per_user_counts: dict[str, int] = {}

    for username in usernames:
        print(f"Fetching tweets for @{username}...")
        rss_url = f"{nitter_base}/{username}/rss"
        xml_text = fetch_rss(rss_url)
        titles = parse_rss_items(xml_text, max_items=per_user)

        # Convert to metrics and discard text
        count_added = 0
        for title in titles:
            m = text_metrics(title)
            if m["char_len"] < 40:
                continue
            all_metrics.append(m)
            count_added += 1

        per_user_counts[username] = count_added
        print(f"  Added {count_added} tweets from @{username}")

    profile = aggregate(all_metrics)
    profile["source"] = {
        "nitter_base": nitter_base,
        "usernames": usernames,
        "per_user_counts": per_user_counts,
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
    }

    # Ensure config directory exists
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    OUTPUT_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved style profile -> {OUTPUT_PATH.resolve()}")
    print(f"Total counted items: {profile.get('count', 0)}")


if __name__ == "__main__":
    main()

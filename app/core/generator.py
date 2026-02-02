"""
Post generation module - handles AI-powered tweet/post generation.
"""

import os
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Configuration paths
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
STYLE_PROFILE_PATH = CONFIG_DIR / "style_profile.json"
TRAINING_TWEETS_PATH = CONFIG_DIR / "training_tweets.json"

# Content rotation modes
ROTATION = ["product_building", "feature_cutting"]

PROMPT_RULES = """
You are writing ONE post for X (Twitter).
Goal: Say what you ACTUALLY DID today. Not what you think about doing things.

Hard rules (must follow):
- Output exactly ONE post. No title, no bullets, no thread markers.
- Max 235 characters (no more than 4 sentences).
- No hashtags. No emojis.
- Do not say: "I'm building X", "feature", "architecture", "API", "pipeline", "LLM", "model", "database", "workflow".
- Write like you're texting a friend who asked "what'd you do today?"
- Tone: direct, specific, casual. Real update, not content.

BANNED phrases (auto-fail if used):
- "the urge to", "the key is", "the real X is Y", "X isn't Y it's Z"
- "I'm convinced", "I believe", "I think", "in my experience"
- "stripping it down", "tack on more", "chasing every idea"
- Any sentence that could work in a productivity blog post

REQUIRED structure:
- Start with what you DID (past tense action): "Removed X", "Shipped Y", "Tested Z with N users"
- Say what happened as a result: "It worked/broke/surprised me because..."
- End with what's next: "Trying X tomorrow" or "Sticking with Y for now"

Examples of GOOD posts (structure, not content to copy):
- "Removed the playlist shuffle button. 80% of users never clicked it anyway. Keeping the state transition flow clean."
- "Tested one-click post generation with 3 people. Two said it didn't sound like them. Adding voice calibration tomorrow."
- "Shipped mood transition paths using tempo gradients. First user said it actually worked. Running it for 7 more days."

Examples of BAD posts (do NOT sound like this):
- "The key to building is focus." ❌ (Generic wisdom)
- "I'm convinced persistence matters." ❌ (Opinion, not action)
- "Today I was tempted to add more features but resisted." ❌ (Talking about building, not building)

Content pillars (rotate daily):
1) Music insight: what happened when you tested music for state transitions
2) Product philosophy: what you removed/kept and why (with data/feedback)
3) Minimalism in building: what you deleted today and what broke/improved

If this could be in a Medium article about productivity, you failed.
If you didn't say what you ACTUALLY DID, you failed.
"""

AD_LIKE_PHRASES = [
    "introducing", "launching", "now live", "big announcement",
    "sign up", "join", "subscribe", "download", "try it", "check it out",
    "dm me", "link in bio", "limited time",
    "game-changer", "revolutionary", "ultimate", "secret", "unlock",
]

BUILDER_CUES = [
    "tradeoff", "constraint", "default", "edge case", "friction",
    "timing", "intent", "outcome", "failure mode", "feedback loop",
]

GENERIC_ABSTRACT = [
    "the brain", "dopamine", "neuroscience", "psychology",
    "patterns",
]

TOPIC_SEEDS_PER_MODE = {
    "product_building": ["feature removed", "user feedback", "testing flow", "iteration"],
    "feature_cutting": ["deleted feature", "constraint added", "simplified path"],
}


def pick_mode_for_today() -> str:
    """Pick content mode based on current date."""
    day_index = int(datetime.now(timezone.utc).strftime("%Y%m%d")) % len(ROTATION)
    return ROTATION[day_index]


def load_style_guidance() -> str:
    """
    Loads aggregate style guidance only (no tweet text).
    If missing, returns empty string.
    """
    try:
        with open(STYLE_PROFILE_PATH, "r", encoding="utf-8") as f:
            profile = json.load(f)

        g = profile.get("guidance", {})
        char_lo, char_hi = (g.get("recommended_char_range") or [0, 0])
        sent_lo, sent_hi = (g.get("recommended_sentence_range") or [0, 0])
        notes = g.get("notes", [])
        notes = [str(note).strip() for note in notes if str(note).strip()]

        notes_lines = ""
        if notes:
            notes_lines = "\n".join(f"- {note}" for note in notes)

        out = [
            "Style (derived from aggregate public writing patterns; do not copy anyone):",
            f"- Target {char_lo}–{char_hi} characters.",
            f"- Target {sent_lo}–{sent_hi} sentences.",
            "- Prefer clean, plain language.",
            "- Contrast is allowed when it clarifies.",
        ]
        if notes_lines:
            out.append("Voice cues:")
            out.append(notes_lines)

        return "\n".join(out).strip()

    except FileNotFoundError:
        return ""
    except (json.JSONDecodeError, OSError):
        return ""


def _coerce_tweet_text(item) -> str:
    """
    training_tweets.json can be a list of strings or objects like {"text": "..."}.
    """
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("text", "")).strip()
    return str(item).strip()


def get_daily_context() -> dict:
    """
    Get today's context from user input (CLI mode).
    Returns dict with: today_context, current_mood, optional_angle
    """
    print("\n=== Daily Context Input ===")
    print("(Press Enter to skip any field)\n")
    
    today_context = input("What's happening today? (e.g., 'shipped MoodFM beta'): ").strip()
    current_mood = input("Current mood/state: (e.g., 'building', 'reflecting', 'shipping'): ").strip()
    optional_angle = input("Optional angle: (e.g., 'persistence', 'constraints', 'tradeoffs'): ").strip()
    
    return {
        "today_context": today_context or None,
        "current_mood": current_mood or None,
        "optional_angle": optional_angle or None
    }


def build_prompt(mode: str, daily_context: dict = None) -> str:
    """Build the full prompt for AI generation."""
    seed = random.choice(TOPIC_SEEDS_PER_MODE[mode])

    texts = ""
    try:
        with open(TRAINING_TWEETS_PATH, "r", encoding="utf-8") as file:
            tweet_examples = json.load(file) or []
            tweet_texts = [_coerce_tweet_text(t) for t in tweet_examples]
            tweet_texts = [t for t in tweet_texts if t]

            if tweet_texts:
                sample_tweets = random.sample(tweet_texts, min(5, len(tweet_texts)))
                texts = "\n".join(f"- {t}" for t in sample_tweets)
    except FileNotFoundError:
        texts = ""
    except (json.JSONDecodeError, OSError, ValueError):
        texts = ""

    mode_line = {
        "product_building": f"Mode: What you shipped/broke/learned building today. Seed: {seed}.",
        "feature_cutting": f"Mode: What you deleted and what happened. Seed: {seed}.",
    }[mode]

    few_shot = ""
    if texts:
        few_shot = f"""
Here are examples of the TONE to match (do not copy text, only match vibe):
{texts}

Write in this style: casual, specific, grounded observations. Not promotional or polished.
""".strip()

    style = load_style_guidance()
    style_block = f"\n\n{style}\n" if style else ""

    # Add daily context if provided
    context_injection = ""
    if daily_context and daily_context.get("today_context"):
        context_injection = f"""

                            TODAY'S ACTUAL WORK (use this; do not invent):
                            {daily_context['today_context']}

                            Current state: {daily_context.get('current_mood', 'building')}
                            Angle: {daily_context.get('optional_angle', 'persistence')}

                            Hard constraint:
                            - Your post MUST include at least all concrete detail copied from the text in TODAY'S ACTUAL WORK (a noun/number/tool/result).
                            - If you can't do that, output: "NEED_MORE_CONTEXT"
                            """

    tail = "\n\n".join(x for x in [few_shot, mode_line, context_injection, "Write the post now."] if x)
    return f"{PROMPT_RULES}{style_block}\n\n{tail}"


def is_ad_like(text: str) -> bool:
    """Check if text sounds promotional/ad-like."""
    t = text.strip().lower()
    if not t:
        return True
    if len(text) > 500:
        return True
    return any(p in t for p in AD_LIKE_PHRASES)


def is_builder_feel(text: str, mode: str) -> bool:
    """Check if text has authentic builder voice."""
    t = " ".join((text or "").strip().lower().split())
    if not t:
        return False

    # Avoid the "generic smart quote" vibe
    if t.startswith("the brain"):
        return False
    if any(x in t for x in ("neuroscience", "dopamine", "psychology says")):
        return False

    return True


def generate_with_gemini(prompt: str, temperature: float = 0.4) -> str:
    """Call Gemini API to generate content."""
    api_key = os.environ["GOOGLE_API_KEY"]
    model_name = os.environ["MODEL_NAME"]

    genai.configure(api_key=api_key)
    llm = genai.GenerativeModel(model_name=model_name)

    response = llm.generate_content(
        contents=prompt,
        generation_config={"temperature": temperature},
    )

    text = getattr(response, "text", "") or ""
    text = text.strip()
    if not text:
        raise RuntimeError(f"Empty response from Gemini: {response!r}")
    return text


def generate_human_post(prompt: str, mode: str) -> str:
    """Generate a single human-sounding post with quality filters."""
    # Try a few times; slightly lower temperature helps reduce "ad voice".
    for temp in (0.5, 0.4, 0.3, 0.2):
        post = generate_with_gemini(prompt, temperature=temp)

        if not is_ad_like(post) and is_builder_feel(post, mode):
            return post

    # Last attempt: explicit rewrite (force builder voice + ban generic framing)
    rewrite_prompt = (
        prompt
        + "\n\nRewrite to sound like a builder. Include one constraint/tradeoff/default. "
          "Avoid generic brain/neuroscience language. Keep it under 235 chars. No CTA."
    )
    return generate_with_gemini(rewrite_prompt, temperature=0.2)


def generate_multiple_options(prompt: str, mode: str, count: int = 2) -> list:
    """Generate multiple post options for user to choose from."""
    options = []

    for _ in range(count):
        try:
            post = generate_human_post(prompt, mode)
            options.append(post)
        except Exception as e:
            print(f"Error generating post option: {e}")
            continue
    
    return options

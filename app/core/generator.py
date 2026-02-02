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
ROTATION = ["daily_wins", "lesson_learned", "shipping_update"]

PROMPT_RULES = """
You are writing ONE post for X (Twitter) in a specific format.
Goal: Turn messy build notes into a structured, engaging post.

OUTPUT FORMAT (follow exactly):
```
[Opening line - what you're sharing]

→ [Win/update 1]
→ [Win/update 2]
→ [Win/update 3 (optional)]

[Closing line with energy]
```

STYLE RULES:
- Use → arrows for each win/update (2-4 items max)
- Opening line sets context (e.g., "Today's wins:", "Shipped some stuff:", "Quick update:")
- Closing line has forward energy (what's next, or a vibe)
- Emojis allowed but sparse (1-2 max, at the end)
- Keep total post under 280 characters
- Sound like a real person texting a friend, not a LinkedIn post

TONE:
- Casual, direct, builder energy
- Specific details > vague claims
- Show personality (humor, honesty, excitement all okay)
- It's fine to say "LFG", "let's go", "shipping", "building" etc.

AVOID:
- Hashtags
- Generic motivational fluff ("the key is...", "I believe...")
- Sounding like a press release or ad
- Being boring

GOOD EXAMPLES:
```
Today's wins:

→ Fixed a nasty auth bug
→ Stripe webhooks now live
→ Talked to 2 users (they want dark mode 👀)

Shipping tomorrow. LFG 🚀
```

```
Quiet shipping day:

→ Refactored the onboarding flow
→ Cut 200 lines of dead code

Feels cleaner. More tomorrow.
```

```
Built in public update:

→ Landing page live
→ 47 waitlist signups
→ First user feedback (they want mobile)

Sleep now, iterate tomorrow 😴
```

BAD EXAMPLES (don't do this):
- "I'm convinced that persistence is key..." ❌
- "Here are my thoughts on building..." ❌
- Long paragraphs with no structure ❌
"""

AD_LIKE_PHRASES = [
    "introducing", "launching soon", "big announcement",
    "sign up now", "subscribe", "download now", "limited time",
    "game-changer", "revolutionary", "ultimate guide",
]

BANNED_PHRASES = [
    "the key is", "the real X is Y", "I'm convinced",
    "in my experience", "here's the thing", "hot take:",
]


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
        char_lo, char_hi = (g.get("recommended_char_range") or [120, 280])
        notes = g.get("notes", [])
        notes = [str(note).strip() for note in notes if str(note).strip()]

        notes_lines = ""
        if notes:
            notes_lines = "\n".join(f"- {note}" for note in notes)

        out = [
            "Style guidance:",
            f"- Target {char_lo}–{char_hi} characters.",
            "- Be specific about what you did.",
            "- Energy is good. Personality is good.",
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
    
    today_context = input("What did you do today? (e.g., 'fixed auth bug, added stripe, talked to users'): ").strip()
    current_mood = input("Mood/vibe: (e.g., 'hyped', 'tired but happy', 'grinding'): ").strip()
    optional_angle = input("What's next? (e.g., 'shipping tomorrow', 'more testing'): ").strip()
    
    return {
        "today_context": today_context or None,
        "current_mood": current_mood or None,
        "optional_angle": optional_angle or None
    }


def build_prompt(mode: str, daily_context: dict = None) -> str:
    """Build the full prompt for AI generation."""
    
    mode_openers = {
        "daily_wins": "Today's wins:",
        "lesson_learned": "Learned something today:",
        "shipping_update": "Shipped some stuff:",
    }
    
    suggested_opener = mode_openers.get(mode, "Today's wins:")

    texts = ""
    try:
        with open(TRAINING_TWEETS_PATH, "r", encoding="utf-8") as file:
            tweet_examples = json.load(file) or []
            tweet_texts = [_coerce_tweet_text(t) for t in tweet_examples]
            tweet_texts = [t for t in tweet_texts if t]

            if tweet_texts:
                sample_tweets = random.sample(tweet_texts, min(3, len(tweet_texts)))
                texts = "\n".join(f"- {t}" for t in sample_tweets)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        texts = ""

    few_shot = ""
    if texts:
        few_shot = f"""
Reference tone (match the vibe, not the words):
{texts}
""".strip()

    style = load_style_guidance()
    style_block = f"\n\n{style}\n" if style else ""

    # Add daily context if provided
    context_injection = ""
    if daily_context and daily_context.get("today_context"):
        context_injection = f"""

USER'S RAW NOTES (transform these into the structured format):
{daily_context['today_context']}

Mood: {daily_context.get('current_mood', 'building')}
What's next: {daily_context.get('optional_angle', 'more tomorrow')}

INSTRUCTIONS:
- Extract 2-4 concrete wins/updates from the notes above
- Use the → arrow format
- Suggested opener: "{suggested_opener}"
- Add a closing line with energy
- Keep their personality, just structure it nicely
"""
    else:
        context_injection = f"""
No specific context provided. Create a realistic example post using the format.
Suggested opener: "{suggested_opener}"
"""

    tail = "\n\n".join(x for x in [few_shot, context_injection, "Write the post now:"] if x)
    return f"{PROMPT_RULES}{style_block}\n\n{tail}"


def is_ad_like(text: str) -> bool:
    """Check if text sounds promotional/ad-like."""
    t = text.strip().lower()
    if not t:
        return True
    if len(text) > 500:
        return True
    return any(p in t for p in AD_LIKE_PHRASES)


def has_banned_phrases(text: str) -> bool:
    """Check for banned generic phrases."""
    t = text.strip().lower()
    return any(p in t for p in BANNED_PHRASES)


def has_correct_format(text: str) -> bool:
    """Check if the post follows the arrow format."""
    return "→" in text or "->" in text


def generate_with_gemini(prompt: str, temperature: float = 0.7) -> str:
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
    
    # Clean up any markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    
    if not text:
        raise RuntimeError(f"Empty response from Gemini: {response!r}")
    return text


def generate_human_post(prompt: str, mode: str) -> str:
    """Generate a single human-sounding post with quality filters."""
    # Higher temperature for more personality
    for temp in (0.7, 0.6, 0.5):
        post = generate_with_gemini(prompt, temperature=temp)

        if (not is_ad_like(post) and 
            not has_banned_phrases(post) and 
            has_correct_format(post)):
            return post

    # Fallback: ask for format fix
    rewrite_prompt = (
        prompt
        + "\n\nIMPORTANT: Use the → arrow format. Include 2-4 bullet points. "
          "Add personality. Keep it under 280 chars."
    )
    return generate_with_gemini(rewrite_prompt, temperature=0.6)


def generate_multiple_options(prompt: str, mode: str, count: int = 3) -> list:
    """Generate multiple post options for user to choose from."""
    options = []

    for i in range(count):
        try:
            # Vary temperature slightly for diversity
            post = generate_with_gemini(
                prompt, 
                temperature=0.6 + (i * 0.1)
            )
            if has_correct_format(post) and not is_ad_like(post):
                options.append(post)
        except Exception as e:
            print(f"Error generating post option: {e}")
            continue
    
    return options

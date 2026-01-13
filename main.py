import os
import json
import smtplib
import random
import urllib.request
from datetime import datetime, timezone
import google.generativeai as genai
from dotenv import load_dotenv
from email.message import EmailMessage

load_dotenv()

ROTATION = ["music_insight", "product_philosophy", "minimalism_in_building"]

PROMPT_RULES = """
You are writing ONE post for X (Twitter).
Goal: grow a following by posting consistently about music + product thinking, without revealing what is being built.

Hard rules (must follow):
- Output exactly ONE post. No title, no bullets, no thread markers.
- Max 235 characters (no more than 4 sentences).
- No hashtags. No emojis.
- Do not say: "I'm building X", "feature", "architecture", "API", "pipeline", "LLM", "model", "database", "workflow".
- No step-by-step instructions. No blueprints. No implementation detail.
- Write observations, not implementations. Signal without blueprint.
- Tone: calm, precise, contrarian when helpful.

Anti-ad rules (must follow):
- Do NOT sound like an ad, pitch, or announcement.
- No calls-to-action (no “try”, “sign up”, “join”, “DM me”, “link in bio”, “subscribe”).
- No hype words (no “game-changer”, “revolutionary”, “unlocked”, “secret”, “ultimate”).
- Write like a real person thinking out loud: specific, grounded, slightly imperfect, not promotional.

Builder-voice rules (must follow):
- Avoid generic neuroscience framing (do NOT start with “The brain…”, avoid “dopamine”, “neuroscience”, “psychology says”).
- Include at least ONE builder lens cue: constraint, tradeoff, default, edge case, friction, timing, outcome, intent.
- Use concrete nouns. No foggy abstractions.

Content pillars (rotate daily):
1) Music insight: music as timing/intent/state regulation (calm, focus, cope, reset).
2) Product philosophy: taste, restraint, "one is enough", outcomes over engagement.
3) Minimalism in building: delete noise, find truth, avoid feature-chasing.

If someone could copy a product from this post, you failed.
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

MUSIC_CONCRETE = [
    "song", "track", "loop", "hook", "verse", "chorus", "tempo", "drums",
    "bass", "silence", "melody", "rhythm", "playlist",
]

GENERIC_ABSTRACT = [
    "the brain", "dopamine", "neuroscience", "psychology",
    "patterns",  # too common; we only use it as a weak “generic” signal
]

TOPIC_SEEDS_PER_MODE = {
    "music_insight": ["focus", "overwhelm"],
    "product_philosophy": ["attention", "starting over"],
    "minimalism_in_building": ["attention", "overwhelm"],
}

def pick_mode_for_today() -> str:
    day_index = int(datetime.now(timezone.utc).strftime("%Y%m%d")) % len(ROTATION)
    return ROTATION[day_index]

def load_style_guidance() -> str:
    """
    Loads aggregate style guidance only (no tweet text).
    If missing, returns empty string.
    """
    try:
        with open("style_profile.json", "r", encoding="utf-8") as f:
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

def build_prompt(mode: str) -> str:
    seed = random.choice(TOPIC_SEEDS_PER_MODE[mode])

    texts = ""
    try:
        with open("training_tweets.json", "r", encoding="utf-8") as file:
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
        "music_insight": f"Mode: Music insight. Seed: {seed}. Include 1 concrete music detail (tempo/loop/track/etc.) + 1 builder lens cue (constraint/tradeoff/default/friction/etc.).",
        "product_philosophy": f"Mode: Product philosophy. Seed: {seed}. Include 1 builder lens cue (constraint/tradeoff/default/friction/etc.).",
        "minimalism_in_building": f"Mode: Minimalism in building. Seed: {seed}. Include 1 builder lens cue (constraint/tradeoff/default/friction/etc.).",
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

    tail = "\n\n".join(x for x in [few_shot, mode_line, "Write the post now."] if x)
    return f"{PROMPT_RULES}{style_block}\n\n{tail}"

def is_ad_like(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return True
    if len(text) > 500:
        return True
    return any(p in t for p in AD_LIKE_PHRASES)

def is_builder_feel(text: str, mode: str) -> bool:
    t = " ".join((text or "").strip().lower().split())
    if not t:
        return False

    # Avoid the “generic smart quote” vibe
    if t.startswith("the brain"):
        return False
    if any(x in t for x in ("neuroscience", "dopamine", "psychology says")):
        return False

    has_builder = any(cue in t for cue in BUILDER_CUES)
    if not has_builder:
        return False

    # Music mode should actually mention music concretely
    if mode == "music_insight":
        has_music = any(w in t for w in MUSIC_CONCRETE)
        if not has_music:
            return False

    return True

def generate_with_gemini(prompt: str, temperature: float = 0.4) -> str:
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
    # Try a few times; slightly lower temperature helps reduce “ad voice”.
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

def send_email(subject: str, body: str) -> None:
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    to_email = os.environ["TO_EMAIL"]

    smtp_debug = os.environ.get("SMTP_DEBUG", "0") == "1"

    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            if smtp_debug:
                server.set_debuglevel(1)
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if smtp_debug:
                server.set_debuglevel(1)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

def main():
    mode = pick_mode_for_today()
    prompt = build_prompt(mode)
    post = generate_human_post(prompt, mode)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"Daily X post ({mode}) — {today}"
    body = post

    send_email(subject, body)

if __name__ == "__main__":
    main()

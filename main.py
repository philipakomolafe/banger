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
- Max 500 characters (leave room for edits).
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

TOPIC_SEEDS_PER_MODE = {
    "music_insight": ["focus", "overwhelm"],
    "product_philosophy": ["attention", "starting over"],
    "minimalism_in_building": ["attention", "overwhelm"],
}

def pick_mode_for_today() -> str:
    # Stable daily rotation based on UTC date (keeps GitHub Actions consistent)
    # Also it output an integer value based off the modulus of 3 applied on the Date integer value.
    day_index = int(datetime.now(timezone.utc).strftime("%Y%m%d")) % len(ROTATION) 
    return ROTATION[day_index]

def build_prompt(mode: str) -> str:
    seed = random.choice(TOPIC_SEEDS_PER_MODE[mode])

    try:
        with open("training_tweets.json") as file:
            tweet_examples = json.load(file)

            # Ensures the maximum k-th samples selected would not exceed 5
            sample_tweets = random.sample(tweet_examples, min(5, len(tweet_examples)))
            texts = "/n".join(f"- {t}" for t in sample_tweets)

    except FileNotFoundError:
        texts = ""

    mode_line = {
        "music_insight": f"Mode: Music insight. Seed: {seed}.",
        "product_philosophy": f"Mode: Product philosophy. Seed: {seed}.",
        "minimalism_in_building": f"Mode: Minimalism in building. Seed: {seed}.",
    }[mode]

    few_shot = f"""
    Here are examples of the TONE to match (real human tweets): {texts}

Write in this exact style: casual, specific, grounded observations. Not promotional or polished.
"""
    return f"{PROMPT_RULES}\n\n{few_shot}\n\n{mode_line}\n\nWrite the post now."

def is_ad_like(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return True
    if len(text) > 500:
        return True
    return any(p in t for p in AD_LIKE_PHRASES)

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

def generate_human_post(prompt: str) -> str:
    # Try a few times; slightly lower temperature helps reduce “ad voice”.
    for temp in (0.4, 0.3, 0.2):
        post = generate_with_gemini(prompt, temperature=temp) 

        if not is_ad_like(post):
            return post

    # Last attempt: explicitly force “not an ad” rewrite.
    rewrite_prompt = prompt + "\n\nRewrite to sound like a real human note. Remove anything that sounds like marketing."
    post = generate_with_gemini(rewrite_prompt, temperature=0.2)
    return post


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
    post = generate_human_post(prompt)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"Daily X post ({mode}) — {today}"
    body = post

    send_email(subject, body)



if __name__ == "__main__":
    main()
 
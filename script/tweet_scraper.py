import os
import json
import re
from pathlib import Path

import tweepy
from dotenv import load_dotenv


load_dotenv()

URL_RE = re.compile(r"https?://\S+")
WS_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    text = URL_RE.sub("", text)
    text = WS_RE.sub(" ", text).strip()
    return text


def get_client() -> tweepy.Client:
    return tweepy.Client(
        bearer_token=os.environ["X_BEARER_TOKEN"],
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_KEY_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
        wait_on_rate_limit=True,
    )


def fetch_my_tweets(
    username: str,
    max_tweets: int = 300,
    include_replies: bool = False,
    include_retweets: bool = False,
) -> list[dict]:
    client = get_client()

    me = client.get_user(username=username)
    user_id = me.data.id

    exclude = []
    if not include_replies:
        exclude.append("replies")
    if not include_retweets:
        exclude.append("retweets")

    out: list[dict] = []

    paginator = tweepy.Paginator(
        client.get_users_tweets,
        id=user_id,
        tweet_fields=["created_at", "lang", "text"],
        exclude=exclude if exclude else None,
        max_results=100,
    )

    for page in paginator:
        if not page.data:
            continue

        for t in page.data:
            text = clean_text(t.text or "")
            if len(text) < 40:
                continue

            out.append(
                {
                    "id": str(t.id),
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "text": text,
                }
            )

            if len(out) >= max_tweets:
                return out
    return out


def main():
    username = os.environ["X_USERNAME"]
    tweets = fetch_my_tweets(
        username=username,
        max_tweets=int(os.environ.get("MAX_TWEETS", "300")),
        include_replies=os.environ.get("INCLUDE_REPLIES", "0") == "1",
        include_retweets=os.environ.get("INCLUDE_RETWEETS", "0") == "1",
    )

    out_path = Path("my_tweets.jsonl")
    with out_path.open("w", encoding="utf-8") as f:
        for row in tweets:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Saved {len(tweets)} tweets -> {out_path.resolve()}")


if __name__ == "__main__":
    main()
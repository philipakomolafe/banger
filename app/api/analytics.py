"""
Tweet analytics endpoints.
"""

import re
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.utils.supabase import get_supabase
from app.api.x_auth import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class TweetAnalyzeRequest(BaseModel):
    tweet_url: str


class TweetMetrics(BaseModel):
    impressions: int = 0
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quotes: int = 0
    bookmarks: int = 0


class TweetAnalysis(BaseModel):
    engagement_rate: float
    performance_level: str
    tip: str
    viral_score: float
    save_rate: float


class TweetAnalyzeResponse(BaseModel):
    success: bool
    tweet_id: str
    tweet_url: str
    text: str
    created_at: Optional[str] = None
    metrics: TweetMetrics
    analysis: TweetAnalysis


def extract_tweet_id(tweet_url: str) -> Optional[str]:
    """Extract tweet ID from Twitter/X URL."""
    pattern = r'(?:twitter\.com|x\.com)/\w+/status/(\d+)'
    match = re.search(pattern, tweet_url)
    return match.group(1) if match else None


def analyze_metrics(metrics: dict) -> dict:
    """Analyze tweet performance."""
    likes = metrics.get("like_count", 0)
    retweets = metrics.get("retweet_count", 0)
    replies = metrics.get("reply_count", 0)
    impressions = max(metrics.get("impression_count", 0), 1) # picks the max to avoid division by zero
    quotes = metrics.get("quote_count", 0)
    bookmarks = metrics.get("bookmark_count", 0)
    
    total_engagements = likes + retweets + replies + quotes
    engagement_rate = (total_engagements / impressions) * 100
    
    # Performance levels
    if engagement_rate >= 5:
        level = "🔥 Viral"
        tip = "Incredible! This is top 1% performance. Create more content like this!"
    elif engagement_rate >= 3:
        level = "🚀 Excellent"
        tip = "Amazing engagement! Consider creating a thread to expand on this."
    elif engagement_rate >= 1.5:
        level = "✅ Great"
        tip = "Above average for indie hackers. Your audience resonates with this!"
    elif engagement_rate >= 0.5:
        level = "📊 Average"
        tip = "Try a stronger hook or post at a different time (8-10am EST works well)."
    else:
        level = "📉 Below Average"
        tip = "Try: shorter tweets, add a question, or share a hot take."
    
    return {
        "engagement_rate": round(engagement_rate, 2),
        "performance_level": level,
        "tip": tip,
        "viral_score": round((retweets + quotes) / max(likes, 1) * 100, 1),
        "save_rate": round((bookmarks / impressions) * 100, 3),
    }


async def get_user_x_token(user_id: str) -> Optional[str]:
    """Get user's X access token."""
    try:
        admin = get_supabase(admin=True)
        result = admin.table("x_tokens")\
            .select("access_token")\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        
        if result.data:
            return result.data.get("access_token")
    except Exception as e:
        logger.error(f"Failed to get X token: {e}")
    
    return None


@router.post("/tweet", response_model=TweetAnalyzeResponse)
async def analyze_tweet(request: Request, body: TweetAnalyzeRequest):
    """
    Analyze a tweet's performance metrics.
    Requires user to have connected their X account.
    """
    user_id = get_current_user_id(request)
    
    # Extract tweet ID
    tweet_id = extract_tweet_id(body.tweet_url)
    if not tweet_id:
        raise HTTPException(status_code=400, detail="Invalid tweet URL. Use format: https://x.com/user/status/123456")
    
    # Get user's X token by querying the Supabase Table: `x_tokens`
    access_token = await get_user_x_token(user_id)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Please connect your X account first. Go to Settings → Connect X Account"
        )
    
    # Fetch tweet data
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.twitter.com/2/tweets/{tweet_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "tweet.fields": "public_metrics,created_at,text",
            }
        )

        # Handling Rate Limits and Token expiry.
        if response.status_code == 429:
            retry_after = response.headers.get("x-rate-limit-reset", 900)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Please wait {retry_after} seconds before trying again."
            )
        
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail="X token expired. Please reconnect your X account."
            )
        
        if response.status_code != 200:
            logger.error(f"Tweet fetch failed: {response.text}")
            raise HTTPException(
                status_code=400,
                detail="Could not fetch tweet. Make sure the URL is correct and the tweet exists."
            )
        
        data = response.json()
    
    tweet_data = data.get("data", {})
    metrics = tweet_data.get("public_metrics", {})
    
    analysis = analyze_metrics(metrics)
    
    return TweetAnalyzeResponse(
        success=True,
        tweet_id=tweet_id,
        tweet_url=body.tweet_url,
        text=tweet_data.get("text", "")[:280],
        created_at=tweet_data.get("created_at"),
        metrics=TweetMetrics(
            impressions=metrics.get("impression_count", 0),
            likes=metrics.get("like_count", 0),
            retweets=metrics.get("retweet_count", 0),
            replies=metrics.get("reply_count", 0),
            quotes=metrics.get("quote_count", 0),
            bookmarks=metrics.get("bookmark_count", 0),
        ),
        analysis=TweetAnalysis(**analysis),
    )
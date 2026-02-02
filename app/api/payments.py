"""
LemonSqueezy webhook handler for subscriptions.
"""
import hashlib
import hmac
import os
import logging
from dotenv import load_dotenv
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException

from app.utils.supabase import get_supabase

load_dotenv()

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])

LEMONSQUEEZY_WEBHOOK_SECRET = os.environ.get("LEMONSQUEEZY_WEBHOOK_SECRET", "")


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify LemonSqueezy webhook signature."""
    if not LEMONSQUEEZY_WEBHOOK_SECRET:
        logger.warning("No webhook secret configured")
        return False
    
    expected = hmac.new(
        LEMONSQUEEZY_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


@router.post("/webhook/lemonsqueezy")
async def lemonsqueezy_webhook(request: Request):
    """Handle LemonSqueezy subscription webhooks."""
    payload = await request.body()
    signature = request.headers.get("X-Signature", "")
    
    # Verify signature in production
    if LEMONSQUEEZY_WEBHOOK_SECRET and not verify_webhook_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    data = await request.json()
    event_name = data.get("meta", {}).get("event_name")
    
    logger.info(f"LemonSqueezy webhook: {event_name}")
    
    if event_name in ("subscription_created", "subscription_updated", "subscription_resumed"):
        await handle_subscription_active(data)
    elif event_name in ("subscription_cancelled", "subscription_expired", "subscription_paused"):
        await handle_subscription_inactive(data)
    
    return {"status": "ok"}


async def handle_subscription_active(data: dict):
    """Handle new or resumed subscription."""
    attrs = data.get("data", {}).get("attributes", {})
    user_email = attrs.get("user_email")
    subscription_id = data.get("data", {}).get("id")
    
    if not user_email:
        logger.error("No user_email in webhook")
        return
    
    try:
        admin = get_supabase(admin=True)
        
        # Find user by email
        user_result = admin.table("auth.users").select("id").eq("email", user_email).single().execute()
        
        if not user_result.data:
            # Store pending subscription for when user signs up
            admin.table("pending_subscriptions").upsert(
                {
                    "email": user_email,
                    "subscription_id": subscription_id,
                    "status": "active",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="email",
            ).execute()
            logger.info(f"Stored pending subscription for {user_email}")
            return
        
        user_id = user_result.data["id"]
        
        # Create/update subscription
        admin.table("subscriptions").upsert(
            {
                "user_id": user_id,
                "subscription_id": subscription_id,
                "status": "active",
                "plan": "pro",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id",
        ).execute()
        
        logger.info(f"Activated subscription for user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to process subscription: {e}")


async def handle_subscription_inactive(data: dict):
    """Handle cancelled or expired subscription."""
    attrs = data.get("data", {}).get("attributes", {})
    user_email = attrs.get("user_email")
    
    if not user_email:
        return
    
    try:
        admin = get_supabase(admin=True)
        
        # Find user and deactivate
        user_result = admin.table("auth.users").select("id").eq("email", user_email).single().execute()
        
        if user_result.data:
            user_id = user_result.data["id"]
            admin.table("subscriptions").update(
                {
                    "status": "inactive",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("user_id", user_id).execute()
            
            logger.info(f"Deactivated subscription for user {user_id}")
            
    except Exception as e:
        logger.error(f"Failed to deactivate subscription: {e}")


@router.get("/checkout-url")
def get_checkout_url(request: Request):
    """Get LemonSqueezy checkout URL with user's email prefilled."""
    # You'll set this in LemonSqueezy dashboard
    checkout_url = os.environ.get("LEMONSQUEEZY_CHECKOUT_URL", "")
    
    return {"checkout_url": checkout_url}


@router.get("/subscription-status")
async def get_subscription_status(request: Request):
    """Get user's subscription status and usage info."""
    from app.utils.usage import get_usage_status, is_user_paid, get_user_subscription
    
    # Extract user from token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return {
            "authenticated": False,
            "is_paid": False,
            "plan": "free",
            "usage": {
                "daily_limit": 3,
                "used_today": 0,
                "remaining": 3,
            }
        }
    
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        return {
            "authenticated": False,
            "is_paid": False,
            "plan": "free",
            "usage": {
                "daily_limit": 3,
                "used_today": 0,
                "remaining": 3,
            }
        }
    
    try:
        supabase = get_supabase(admin=False)
        result = supabase.auth.get_user(token)
        
        if not result.user:
            return {
                "authenticated": False,
                "is_paid": False,
                "plan": "free",
                "usage": {
                    "daily_limit": 3,
                    "used_today": 0,
                    "remaining": 3,
                }
            }
        
        user_id = result.user.id
        usage = get_usage_status(user_id)
        subscription = get_user_subscription(user_id)
        is_paid = is_user_paid(user_id)
        
        return {
            "authenticated": True,
            "is_paid": is_paid,
            "plan": "pro" if is_paid else "free",
            "subscription": {
                "status": subscription.get("status", "none"),
                "subscription_id": subscription.get("subscription_id"),
            } if subscription else None,
            "usage": {
                "daily_limit": -1 if is_paid else usage.get("daily_limit", 3),
                "used_today": usage.get("used_today", 0),
                "remaining": -1 if is_paid else usage.get("remaining", 3),
                "can_generate": usage.get("can_generate", True),
            },
            "checkout_url": os.environ.get("LEMONSQUEEZY_CHECKOUT_URL", ""),
        }
        
    except Exception as e:
        logger.error(f"Failed to get subscription status: {e}")
        return {
            "authenticated": False,
            "is_paid": False,
            "plan": "free",
            "usage": {
                "daily_limit": 3,
                "used_today": 0,
                "remaining": 3,
            }
        }


@router.post("/cancel-subscription")
async def cancel_subscription(request: Request):
    """
    Placeholder for subscription cancellation.
    In production, you'd call LemonSqueezy API to cancel.
    """
    from app.utils.usage import get_user_subscription
    
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = auth_header.replace("Bearer ", "").strip()
    
    try:
        supabase = get_supabase(admin=False)
        result = supabase.auth.get_user(token)
        
        if not result.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = result.user.id
        subscription = get_user_subscription(user_id)
        
        if not subscription or subscription.get("status") != "active":
            raise HTTPException(status_code=400, detail="No active subscription found")
        
        # In production, call LemonSqueezy API to cancel
        # For now, just return info about how to cancel
        customer_portal_url = os.environ.get("LEMONSQUEEZY_CUSTOMER_PORTAL_URL", "")
        
        return {
            "message": "To cancel your subscription, please visit the customer portal",
            "customer_portal_url": customer_portal_url,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel subscription: {e}")
        raise HTTPException(status_code=500, detail="Failed to process cancellation")
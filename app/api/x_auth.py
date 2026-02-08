"""
X (Twitter) OAuth 2.0 Authentication with PKCE.
Allows users to connect their X account to analyze tweet performance.
"""

import os
import secrets
import hashlib
import base64
import logging
from typing import Optional
from dotenv import load_dotenv
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from app.utils.supabase import get_supabase

logger = logging.getLogger(__name__)

load_dotenv()  # Load environment variables from .env file

router = APIRouter(prefix="/api/x", tags=["x-auth"])

# X OAuth 2.0 endpoints
X_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
X_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
X_USER_URL = "https://api.twitter.com/2/users/me"

# Scopes needed to read tweets and metrics
SCOPES = ["tweet.read", "users.read", "offline.access"]


class XAuthURLResponse(BaseModel):
    url: str
    state: str


class XCallbackRequest(BaseModel):
    code: str
    state: str
    code_verifier: str


class XConnectionStatus(BaseModel):
    connected: bool
    x_username: Optional[str] = None
    x_user_id: Optional[str] = None


def generate_code_verifier() -> str:
    """Generate a code verifier for PKCE."""
    return secrets.token_urlsafe(32)


def generate_code_challenge(verifier: str) -> str:
    """Generate code challenge from verifier using S256."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()


def get_client_credentials():
    """Get X OAuth client credentials from environment."""
    client_id = os.environ.get("CLIENT_ID", "").strip()
    client_secret = os.environ.get("CLIENT_SECRET", "").strip()
    
    if not client_id:
        raise HTTPException(status_code=500, detail="X OAuth CLIENT_ID not configured")
    
    return client_id, client_secret


def get_current_user_id(request: Request) -> str:
    """Extract user ID from Supabase auth token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = auth_header.replace("Bearer ", "").strip()
    
    try:
        supabase = get_supabase(admin=False)
        result = supabase.auth.get_user(token)
        
        if not result.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return result.user.id
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/auth-url", response_model=XAuthURLResponse)
async def get_x_auth_url(request: Request):
    """
    Generate X OAuth 2.0 authorization URL with PKCE.
    Frontend should store the code_verifier for the callback.
    """
    user_id = get_current_user_id(request)
    
    client_id, _ = get_client_credentials()
    redirect_uri = os.environ.get("X_AUTH_REDIRECT_URL", 
                                   os.environ.get("AUTH_REDIRECT_URL", "").replace("callback.html", "x-callback.html"))
    
    # Generate PKCE values
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(16)
    
    # Store state and verifier temporarily (in Supabase)
    try:
        admin = get_supabase(admin=True)
        admin.table("x_auth_states").upsert({
            "user_id": user_id,
            "state": state,
            "code_verifier": code_verifier,
        }, on_conflict="user_id").execute()
    except Exception as e:
        logger.error(f"Failed to store auth state: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate auth")
    
    # Build authorization URL
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    
    auth_url = f"{X_AUTH_URL}?{urlencode(params)}"
    
    return XAuthURLResponse(url=auth_url, state=state)


@router.post("/callback")
async def x_callback(request: Request, body: XCallbackRequest):
    """
    Handle X OAuth 2.0 callback.
    Exchange authorization code for access token.
    """
    user_id = get_current_user_id(request)
    client_id, client_secret = get_client_credentials()
    redirect_uri = os.environ.get("X_AUTH_REDIRECT_URL",
                                   os.environ.get("AUTH_REDIRECT_URL", "").replace("callback.html", "x-callback.html"))
    
    # Verify state
    try:
        admin = get_supabase(admin=True)
        state_result = admin.table("x_auth_states")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("state", body.state)\
            .single()\
            .execute()
        
        if not state_result.data:
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        
        code_verifier = state_result.data.get("code_verifier")
        
        # Clean up used state
        admin.table("x_auth_states").delete().eq("user_id", user_id).execute()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"State verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid state")
    
    # Exchange code for token
    token_data = {
        "grant_type": "authorization_code",
        "code": body.code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    
    # Use Basic auth with client credentials
    auth = (client_id, client_secret) if client_secret else None
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    if not client_secret:
        # Public client - include client_id in body
        token_data["client_id"] = client_id
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            X_TOKEN_URL,
            data=token_data,
            headers=headers,
            auth=auth,
        )
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.text}")
            raise HTTPException(status_code=400, detail="Failed to connect X account")
        
        tokens = response.json()
    
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    
    # Get X user info
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            X_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"user.fields": "username,name,profile_image_url"}
        )
        
        if user_response.status_code != 200:
            logger.error(f"Failed to get X user: {user_response.text}")
            raise HTTPException(status_code=400, detail="Failed to get X user info")
        
        x_user = user_response.json().get("data", {})
    
    # Store tokens and X user info
    try:
        admin = get_supabase(admin=True)
        admin.table("x_tokens").upsert({
            "user_id": user_id,
            "x_user_id": x_user.get("id"),
            "x_username": x_user.get("username"),
            "x_name": x_user.get("name"),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }, on_conflict="user_id").execute()
    except Exception as e:
        logger.error(f"Failed to store X tokens: {e}")
        raise HTTPException(status_code=500, detail="Failed to save X connection")
    
    return {
        "success": True,
        "message": "X account connected successfully!",
        "x_username": x_user.get("username"),
    }


@router.get("/status", response_model=XConnectionStatus)
async def get_x_connection_status(request: Request):
    """Check if user has connected their X account."""
    user_id = get_current_user_id(request)
    
    try:
        admin = get_supabase(admin=True)
        result = admin.table("x_tokens")\
            .select("x_username, x_user_id")\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        
        if result.data:
            return XConnectionStatus(
                connected=True,
                x_username=result.data.get("x_username"),
                x_user_id=result.data.get("x_user_id"),
            )
    except Exception:
        pass
    
    return XConnectionStatus(connected=False)


@router.delete("/disconnect")
async def disconnect_x(request: Request):
    """Disconnect X account."""
    user_id = get_current_user_id(request)
    
    try:
        admin = get_supabase(admin=True)
        admin.table("x_tokens").delete().eq("user_id", user_id).execute()
        
        return {"success": True, "message": "X account disconnected"}
    except Exception as e:
        logger.error(f"Failed to disconnect X: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect")
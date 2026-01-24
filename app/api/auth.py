"""
Authentication routes using Supabase Auth.
"""

import os
import logging
import traceback
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.utils.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    user_id: Optional[str] = None
    email: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class GoogleAuthResponse(BaseModel):
    url: str


def _upsert_profile(user_id: str, email: Optional[str]) -> None:
    """Create/update public.profiles row for this user (server-side)."""
    if not user_id:
        return
    try:
        admin = get_supabase(admin=True)  # must be service-role
        admin.table("profiles").upsert(
            {"id": user_id, "email": (email or "").strip().lower()},
            on_conflict="id",
        ).execute()
    except Exception as e:
        logger.error(f"Profile upsert failed for user_id={user_id}: {e}\n{traceback.format_exc()}")


@router.post("/signup", response_model=AuthResponse)
async def signup(req: SignupRequest):
    email = (req.email or "").strip().lower()
    password = (req.password or "").strip()

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    try:
        supabase = get_supabase(admin=False)
        result = supabase.auth.sign_up({"email": email, "password": password})

        if not result.user:
            raise HTTPException(status_code=400, detail="Signup failed")

        _upsert_profile(result.user.id, result.user.email)

        return AuthResponse(
            success=True,
            message="Signup successful. If email confirmation is enabled, confirm your email before logging in.",
            user_id=result.user.id,
            email=result.user.email,
            access_token=result.session.access_token if result.session else None,
            refresh_token=result.session.refresh_token if result.session else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Signup failed")


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    email = (req.email or "").strip().lower()
    password = (req.password or "").strip()

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    try:
        supabase = get_supabase(admin=False)
        result = supabase.auth.sign_in_with_password({"email": email, "password": password})

        if not result.user or not result.session:
            raise HTTPException(status_code=401, detail="Invalid login credentials")

        _upsert_profile(result.user.id, result.user.email)

        return AuthResponse(
            success=True,
            message="Login successful",
            user_id=result.user.id,
            email=result.user.email,
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=401, detail="Invalid login credentials")


@router.get("/google", response_model=GoogleAuthResponse)
async def google_auth(_: Request):
    try:
        supabase_url = os.environ.get("SUPABASE_URL", "").strip()
        redirect_to = os.environ.get("AUTH_REDIRECT_URL", "http://localhost:8000/web/callback.html").strip()

        if not supabase_url:
            raise HTTPException(status_code=500, detail="SUPABASE_URL not configured")

        url = f"{supabase_url}/auth/v1/authorize?provider=google&redirect_to={quote(redirect_to, safe='')}"
        return GoogleAuthResponse(url=url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google auth error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to get google auth url")


@router.get("/me")
async def me(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = auth_header.replace("Bearer ", "").strip()

    try:
        supabase = get_supabase(admin=False)
        result = supabase.auth.get_user(token)

        if not result.user:
            raise HTTPException(status_code=401, detail="Invalid token")

        # This is the key for Google sign-in: callback.html calls /me after OAuth.
        _upsert_profile(result.user.id, result.user.email)

        return {"user_id": result.user.id, "email": result.user.email}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"/me error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=401, detail="Invalid token")
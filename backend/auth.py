"""DRIFTIQ — Email + password auth with JWT (pilot scope, no SSO).
Exposes /api/auth/register, /api/auth/login, /api/auth/me and the
get_current_user dependency that protected endpoints use.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
import db
import models

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


# ---------- Passwords ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


# ---------- Tokens ----------

def create_token(user: models.User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(minutes=config.JWT_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    session: AsyncSession = Depends(db.get_session),
) -> models.User:
    """Resolve the Bearer token to a User or raise 401."""
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, config.JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await session.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


# ---------- Schemas ----------

class LoginBody(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("invalid email address")
        return v


class RegisterBody(LoginBody):
    name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


def _user_out(user: models.User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name}


# ---------- Endpoints ----------

@router.post("/register")
async def register(body: RegisterBody, session: AsyncSession = Depends(db.get_session)):
    existing = (
        await session.execute(select(models.User).where(models.User.email == body.email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = models.User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=(body.name or "").strip() or None,
    )
    session.add(user)
    await session.commit()
    return {"ok": True, "token": create_token(user), "user": _user_out(user)}


@router.post("/login")
async def login(body: LoginBody, session: AsyncSession = Depends(db.get_session)):
    user = (
        await session.execute(select(models.User).where(models.User.email == body.email))
    ).scalar_one_or_none()
    # Placeholder/pre-auth users have no password_hash and cannot log in.
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"ok": True, "token": create_token(user), "user": _user_out(user)}


@router.get("/me")
async def me(user: models.User = Depends(get_current_user)):
    return {"ok": True, "user": _user_out(user)}

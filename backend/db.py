"""DRIFTIQ — Database engine and session management.
Async SQLAlchemy engine driven by DATABASE_URL (see config.py).
Postgres (asyncpg) in production; falls back to local SQLite (aiosqlite)
so local dev works without a Postgres instance.
"""
from __future__ import annotations
from typing import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import config


def _asyncpg_query(url: str) -> str:
    """Neon/Supabase connection strings carry libpq params that asyncpg
    doesn't understand: sslmode becomes ssl, channel_binding is dropped."""
    parts = urlsplit(url)
    q = dict(parse_qsl(parts.query))
    if "sslmode" in q:
        q["ssl"] = q.pop("sslmode")
    q.pop("channel_binding", None)
    return urlunsplit(parts._replace(query=urlencode(q)))


def to_async_url(url: str) -> str:
    """Normalize a DATABASE_URL to its async-driver equivalent."""
    if url.startswith("postgres://"):  # Heroku/Railway style
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return _asyncpg_query("postgresql+asyncpg://" + url[len("postgresql://"):])
    if url.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + url[len("sqlite://"):]
    return url


def to_sync_url(url: str) -> str:
    """Normalize a DATABASE_URL to its sync-driver equivalent (used by Alembic)."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


engine = create_async_engine(to_async_url(config.DATABASE_URL), echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one AsyncSession per request."""
    async with SessionLocal() as session:
        yield session

# backend/app/db.py
from __future__ import annotations

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def _to_psycopg_v3_url(url: str) -> str:
    # Normalize to SQLAlchemy psycopg v3 driver
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _to_psycopg_v3_url(os.environ["DATABASE_URL"])

# Small, robust pool for Render Free tier + Supabase pooler
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,   # drop dead/stale connections
    pool_recycle=1800,    # refresh every 30 minutes
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping() -> None:
    # simple DB ping; raises if unreachable
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

# backend/app/db.py
import os
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base


def _to_psycopg_v3_url(url: str) -> str:
    # Force SQLAlchemy to use psycopg v3 dialect
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

def _ensure_sslmode_require(url: str) -> str:
    # Append sslmode=require if missing (Supabase needs SSL)
    parsed = urlparse(url)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "sslmode" not in q:
        q["sslmode"] = "require"
    return urlunparse(parsed._replace(query=urlencode(q)))

DATABASE_URL = os.environ["DATABASE_URL"]
DATABASE_URL = _ensure_sslmode_require(_to_psycopg_v3_url(DATABASE_URL))

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # validates connections before use
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

def ping() -> None:
    # Raises if DB is unreachable
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

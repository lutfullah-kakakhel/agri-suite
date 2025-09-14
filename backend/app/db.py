# backend/app/db.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base


def _to_psycopg_v3_url(url: str) -> str:
    """Force SQLAlchemy to use the psycopg v3 dialect."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _to_psycopg_v3_url(os.environ["DATABASE_URL"])

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def ping() -> None:
    """Simple connectivity check. Raises if the DB is unreachable."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

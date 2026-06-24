"""
database.py — SQLAlchemy engine, session lifecycle, and declarative base.

All ORM models import Base from here. FastAPI route handlers receive a
database session via the get_db() dependency injector.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ── DATABASE CONFIGURATION ────────────────────────────────────────────────────
# PostgreSQL local connection configured with the password: 123456
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:123456@localhost:5432/crypto_db"

# ── ENGINE CREATION ───────────────────────────────────────────────────────────
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,       # Reconnect silently after idle-connection drops
    pool_size=10,
    max_overflow=20,
    echo=False                # Set True to log every SQL query during development
)

# ── SESSION FACTORY ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── DECLARATIVE BASE ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Parent class for all ORM models."""
    pass


# ── FASTAPI DEPENDENCY INJECTION ──────────────────────────────────────────────
def get_db():
    """
    Yield a database session and guarantee it is closed after the request,
    even if an exception is raised mid-handler.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
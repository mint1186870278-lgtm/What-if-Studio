"""Database configuration and session management.

Supports both SQLite (default) and PostgreSQL via Alembic migrations.
"""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from src.config import settings

# SQLAlchemy ORM base class
Base = declarative_base()

# Resolve database URL (PostgreSQL if configured, else SQLite)
_resolved_url = settings.resolved_database_url

# Engine kwargs per backend
_engine_kwargs: dict = {"echo": settings.debug}
if "sqlite" in _resolved_url:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

# Create engine
engine = create_engine(_resolved_url, **_engine_kwargs)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency injection for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """Run Alembic migrations programmatically."""
    from alembic.config import Config
    from alembic import command
    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", _resolved_url)
    command.upgrade(alembic_cfg, "head")


def init_db() -> None:
    """Initialize database tables.

    Uses Alembic migrations when available; falls back to create_all for
    first-run / development convenience.
    """
    try:
        run_migrations()
    except Exception:
        # Fallback: create tables directly (useful when no migrations exist yet)
        Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """Drop all database tables (for testing/cleanup)."""
    Base.metadata.drop_all(bind=engine)

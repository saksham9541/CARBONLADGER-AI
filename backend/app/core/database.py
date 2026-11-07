"""
CarbonLedger AI — Database Session Management
===============================================
SQLAlchemy engine + session factory.
All models inherit from Base.

The engine is created lazily (on first call to get_engine()) so that
test suites can override DATABASE_URL via os.environ before importing
any module that calls get_db().
"""

from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


_engine = None
_SessionLocal = None


def get_engine():
    """Return the singleton SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {}
        if "sqlite" in settings.database_url:
            connect_args["check_same_thread"] = False
        elif "postgresql" in settings.database_url:
            connect_args["connect_timeout"] = 2
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
            echo=settings.debug,
        )
        logger.info("Database engine created", url=settings.database_url.split("@")[-1])
    return _engine


def get_session_factory():
    """Return the singleton session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency: yields a database session and closes it after the request.

    Test suites override this dependency via app.dependency_overrides[get_db].
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

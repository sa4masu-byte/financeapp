"""
Database connection module
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from contextlib import contextmanager
from typing import Generator

from config import get_settings

settings = get_settings()

# SQLAlchemy engine configuration
# SQLite needs different settings than PostgreSQL
if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},  # Required for SQLite
    )
else:
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Get DB session for FastAPI Dependency
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Get DB session for batch processing (context manager)
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """
    Initialize database (create tables)
    """
    from models import (
        Ticker, DailyPrice, Return, Correlation,
        BacktestResult, DailyTrigger, Setting
    )
    Base.metadata.create_all(bind=engine)

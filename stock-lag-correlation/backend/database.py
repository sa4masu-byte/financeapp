"""
データベース接続モジュール
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from contextlib import contextmanager
from typing import Generator

from config import get_settings

settings = get_settings()

# SQLAlchemy エンジン
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# セッションファクトリ
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ベースクラス
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI Dependency用のDBセッション取得
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    バッチ処理用のDBセッション取得（コンテキストマネージャ）
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
    データベース初期化（テーブル作成）
    """
    from models import (
        Ticker, DailyPrice, Return, Correlation,
        BacktestResult, DailyTrigger, Setting
    )
    Base.metadata.create_all(bind=engine)

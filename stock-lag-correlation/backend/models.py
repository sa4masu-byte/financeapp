"""
SQLAlchemy モデル定義
"""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    Column, String, Integer, BigInteger, Date, DateTime,
    Numeric, ForeignKey, Text, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from database import Base


class Ticker(Base):
    """銘柄マスタ"""
    __tablename__ = "tickers"

    ticker_code = Column(String(10), primary_key=True)
    company_name = Column(String(255))
    sector = Column(String(100))
    market_cap = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # リレーション
    daily_prices = relationship("DailyPrice", back_populates="ticker")
    returns = relationship("Return", back_populates="ticker")
    daily_triggers = relationship("DailyTrigger", back_populates="ticker")


class DailyPrice(Base):
    """日次株価データ"""
    __tablename__ = "daily_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker_code = Column(String(10), ForeignKey("tickers.ticker_code"), nullable=False)
    date = Column(Date, nullable=False)
    adj_close = Column(Numeric(12, 2))
    volume = Column(BigInteger, nullable=True)

    __table_args__ = (
        UniqueConstraint("ticker_code", "date", name="uq_daily_prices_ticker_date"),
        Index("idx_daily_prices_date", "date"),
    )

    ticker = relationship("Ticker", back_populates="daily_prices")


class Return(Base):
    """リターンデータ（TOPIX控除済み）"""
    __tablename__ = "returns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker_code = Column(String(10), ForeignKey("tickers.ticker_code"), nullable=False)
    date = Column(Date, nullable=False)
    timeframe = Column(String(10), nullable=False)
    return_value = Column(Numeric(10, 6))
    topix_adjusted_return = Column(Numeric(10, 6))

    __table_args__ = (
        UniqueConstraint("ticker_code", "date", "timeframe", name="uq_returns_ticker_date_tf"),
        CheckConstraint("timeframe IN ('daily', 'weekly', 'monthly')", name="chk_returns_timeframe"),
        Index("idx_returns_date", "date"),
        Index("idx_returns_ticker_timeframe", "ticker_code", "timeframe"),
    )

    ticker = relationship("Ticker", back_populates="returns")


class Correlation(Base):
    """相関分析結果"""
    __tablename__ = "correlations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker_a = Column(String(10), ForeignKey("tickers.ticker_code"), nullable=False)
    ticker_b = Column(String(10), ForeignKey("tickers.ticker_code"), nullable=False)
    timeframe = Column(String(10), nullable=False)
    lag = Column(Integer, nullable=False)
    correlation = Column(Numeric(6, 4))
    p_value = Column(Numeric(10, 8))
    direction = Column(String(10))
    calculated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("ticker_a", "ticker_b", "timeframe", "lag", name="uq_correlations"),
        CheckConstraint("direction IN ('positive', 'negative')", name="chk_correlations_direction"),
        Index("idx_correlations_ticker_a", "ticker_a"),
        Index("idx_correlations_ticker_b", "ticker_b"),
        Index("idx_correlations_timeframe", "timeframe"),
    )

    ticker_a_rel = relationship("Ticker", foreign_keys=[ticker_a])
    ticker_b_rel = relationship("Ticker", foreign_keys=[ticker_b])


class BacktestResult(Base):
    """バックテスト結果"""
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker_a = Column(String(10), ForeignKey("tickers.ticker_code"), nullable=False)
    ticker_b = Column(String(10), ForeignKey("tickers.ticker_code"), nullable=False)
    timeframe = Column(String(10), nullable=False)
    lag = Column(Integer, nullable=False)
    hit_rate = Column(Numeric(5, 4))
    total_signals = Column(Integer)
    successful_signals = Column(Integer)
    test_period_start = Column(Date)
    test_period_end = Column(Date)

    __table_args__ = (
        UniqueConstraint("ticker_a", "ticker_b", "timeframe", "lag", name="uq_backtest"),
    )

    ticker_a_rel = relationship("Ticker", foreign_keys=[ticker_a])
    ticker_b_rel = relationship("Ticker", foreign_keys=[ticker_b])


class DailyTrigger(Base):
    """トリガー銘柄（日次更新）"""
    __tablename__ = "daily_triggers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker_code = Column(String(10), ForeignKey("tickers.ticker_code"), nullable=False)
    date = Column(Date, nullable=False)
    timeframe = Column(String(10), nullable=False)
    return_value = Column(Numeric(10, 6))
    volume_ratio = Column(Numeric(6, 2))

    __table_args__ = (
        UniqueConstraint("ticker_code", "date", "timeframe", name="uq_daily_triggers"),
        Index("idx_daily_triggers_date", "date"),
    )

    ticker = relationship("Ticker", back_populates="daily_triggers")


class Setting(Base):
    """設定管理"""
    __tablename__ = "settings"

    key = Column(String(50), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

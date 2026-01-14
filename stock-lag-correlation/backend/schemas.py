"""
Pydantic スキーマ定義
"""
from datetime import date, datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# === リクエストスキーマ ===

class SettingsUpdate(BaseModel):
    """設定更新リクエスト"""
    return_threshold: Optional[float] = Field(None, ge=0, le=1)
    volume_threshold: Optional[float] = Field(None, ge=1)
    min_correlation: Optional[float] = Field(None, ge=0, le=1)
    significance_level: Optional[float] = Field(None, ge=0, le=1)
    max_lag_daily: Optional[int] = Field(None, ge=1, le=30)
    max_lag_weekly: Optional[int] = Field(None, ge=1, le=12)
    max_lag_monthly: Optional[int] = Field(None, ge=1, le=6)


# === レスポンススキーマ ===

class TriggerResponse(BaseModel):
    """トリガー銘柄レスポンス"""
    ticker: str
    company_name: str
    return_value: float = Field(..., alias="return")
    volume_ratio: float
    candidate_count: int

    class Config:
        populate_by_name = True


class CandidateResponse(BaseModel):
    """候補銘柄レスポンス"""
    ticker_b: str
    company_name: str
    lag: int
    correlation: float
    p_value: float
    hit_rate: Optional[float]
    direction: Literal["positive", "negative"]
    score: float


class TimeseriesData(BaseModel):
    """時系列データ"""
    dates: List[str]
    returns_a: List[float]
    returns_b_shifted: List[float]


class RecentSignal(BaseModel):
    """過去のシグナル"""
    date: str
    return_a: float
    return_b: float
    success: bool


class CorrelationDetail(BaseModel):
    """相関詳細レスポンス"""
    ticker_a: str
    ticker_b: str
    ticker_a_name: str
    ticker_b_name: str
    lag: int
    correlation: float
    p_value: float
    hit_rate: Optional[float]
    direction: Literal["positive", "negative"]
    timeseries: TimeseriesData
    recent_signals: List[RecentSignal]


class SettingsResponse(BaseModel):
    """設定レスポンス"""
    return_threshold: float
    volume_threshold: float
    min_correlation: float
    significance_level: float
    max_lag_daily: int
    max_lag_weekly: int
    max_lag_monthly: int


class BatchStatusResponse(BaseModel):
    """バッチ実行ステータス"""
    status: Literal["running", "completed", "failed"]
    message: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# === 内部データ構造 ===

class TickerInfo(BaseModel):
    """銘柄情報"""
    ticker_code: str
    company_name: str
    sector: Optional[str] = None
    market_cap: Optional[int] = None


class CorrelationResult(BaseModel):
    """相関計算結果"""
    ticker_a: str
    ticker_b: str
    timeframe: str
    lag: int
    correlation: float
    p_value: float
    direction: Literal["positive", "negative"]


class BacktestResultSchema(BaseModel):
    """バックテスト結果"""
    ticker_a: str
    ticker_b: str
    timeframe: str
    lag: int
    hit_rate: float
    total_signals: int
    successful_signals: int
    test_period_start: date
    test_period_end: date

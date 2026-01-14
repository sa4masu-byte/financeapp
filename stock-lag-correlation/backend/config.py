"""
設定管理モジュール
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """アプリケーション設定"""

    # Database (SQLite for local dev, PostgreSQL for production)
    database_url: str = "sqlite:///./stock_correlation.db"

    # アプリケーション
    app_name: str = "Stock Lag Correlation"
    debug: bool = False

    # タイムゾーン
    timezone: str = "Asia/Tokyo"

    # キャッシュ
    cache_dir: Path = Path("./cache")
    candidate_cache_maxsize: int = 1000
    candidate_cache_ttl: int = 3600  # 1時間

    # デフォルト分析パラメータ
    default_return_threshold: float = 0.02
    default_volume_threshold: float = 1.5
    default_min_correlation: float = 0.30
    default_significance_level: float = 0.05
    default_max_lag_daily: int = 10
    default_max_lag_weekly: int = 6
    default_max_lag_monthly: int = 3

    # Stooq設定
    stooq_request_delay: float = 0.5  # リクエスト間隔（秒）
    stooq_retry_delays: list = [0.5, 1, 2, 4, 8]  # exponential backoff
    stooq_batch_size: int = 50  # バッチサイズ

    # ログ設定
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """設定のシングルトンインスタンスを取得"""
    return Settings()


# 定数
TIMEFRAMES = ["daily", "weekly", "monthly"]
DIRECTIONS = ["positive", "negative"]

# 銘柄コード変換
def to_stooq_ticker(ticker_code: str) -> str:
    """DBの銘柄コードをStooq形式に変換"""
    return f"{ticker_code}.JP"

def from_stooq_ticker(stooq_ticker: str) -> str:
    """Stooq形式をDB形式に変換"""
    return stooq_ticker.replace(".JP", "")

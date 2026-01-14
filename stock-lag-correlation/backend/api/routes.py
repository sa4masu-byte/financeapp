"""
APIエンドポイント定義
"""
import logging
from datetime import date, datetime
from typing import List, Optional
import asyncio

from fastapi import APIRouter, Query, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

import sys
sys.path.append('..')
from database import get_db
from schemas import (
    TriggerResponse, CandidateResponse, CorrelationDetail,
    SettingsResponse, SettingsUpdate, BatchStatusResponse,
    TimeseriesData, RecentSignal
)
from models import Setting, Ticker, Correlation, Return
from analysis import TriggerDetector, BacktestEngine, CorrelationEngine
from data import ReturnCalculator, CacheManager
from data.cache import get_cache_manager
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

# バッチ実行状態
batch_status = {
    'status': 'idle',
    'message': '',
    'started_at': None,
    'completed_at': None
}


def get_setting_value(db: Session, key: str, default: str) -> str:
    """設定値を取得"""
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else default


def get_all_settings(db: Session) -> dict:
    """全設定を取得"""
    return {
        'return_threshold': float(get_setting_value(db, 'return_threshold', '0.02')),
        'volume_threshold': float(get_setting_value(db, 'volume_threshold', '1.5')),
        'min_correlation': float(get_setting_value(db, 'min_correlation', '0.30')),
        'significance_level': float(get_setting_value(db, 'significance_level', '0.05')),
        'max_lag_daily': int(get_setting_value(db, 'max_lag_daily', '10')),
        'max_lag_weekly': int(get_setting_value(db, 'max_lag_weekly', '6')),
        'max_lag_monthly': int(get_setting_value(db, 'max_lag_monthly', '3')),
    }


@router.get("/triggers/today", response_model=List[TriggerResponse])
async def get_today_triggers(
    timeframe: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    db: Session = Depends(get_db)
):
    """
    今日のトリガー銘柄リストを取得
    """
    detector = TriggerDetector(db)

    # 最新のトリガー日付を取得
    latest_date = detector.get_latest_trigger_date(timeframe)

    if latest_date is None:
        return []

    # キャッシュチェック
    cache_manager = get_cache_manager()
    date_str = latest_date.strftime('%Y-%m-%d')
    cached = cache_manager.get_triggers(date_str, timeframe)

    if cached is not None:
        triggers_df = cached
    else:
        triggers_df = detector.get_triggers_from_db(latest_date, timeframe)
        if not triggers_df.empty:
            cache_manager.set_triggers(date_str, timeframe, triggers_df)

    if triggers_df.empty:
        return []

    return [
        TriggerResponse(
            ticker=row['ticker'],
            company_name=row['company_name'],
            **{'return': row['return']},
            volume_ratio=row['volume_ratio'],
            candidate_count=row['candidate_count']
        )
        for _, row in triggers_df.iterrows()
    ]


@router.get("/triggers/date/{target_date}", response_model=List[TriggerResponse])
async def get_triggers_by_date(
    target_date: str,
    timeframe: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    db: Session = Depends(get_db)
):
    """
    指定日のトリガー銘柄リストを取得
    """
    try:
        date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    detector = TriggerDetector(db)
    triggers_df = detector.get_triggers_from_db(date_obj, timeframe)

    if triggers_df.empty:
        return []

    return [
        TriggerResponse(
            ticker=row['ticker'],
            company_name=row['company_name'],
            **{'return': row['return']},
            volume_ratio=row['volume_ratio'],
            candidate_count=row['candidate_count']
        )
        for _, row in triggers_df.iterrows()
    ]


@router.get("/candidates/{ticker}", response_model=List[CandidateResponse])
async def get_candidates(
    ticker: str,
    timeframe: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    top_n: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    指定銘柄の候補銘柄Bリストを取得
    """
    # キャッシュチェック
    cache_manager = get_cache_manager()
    cached = cache_manager.get_candidates(ticker, timeframe, top_n)

    if cached is not None:
        candidates_df = cached
    else:
        detector = TriggerDetector(db)
        candidates_df = detector.find_candidate_pairs_from_db(ticker, timeframe, top_n)

        if not candidates_df.empty:
            cache_manager.set_candidates(ticker, timeframe, top_n, candidates_df)

    if candidates_df.empty:
        return []

    return [
        CandidateResponse(
            ticker_b=row['ticker_b'],
            company_name=row['company_name'],
            lag=row['lag'],
            correlation=row['correlation'],
            p_value=row['p_value'],
            hit_rate=row['hit_rate'],
            direction=row['direction'],
            score=row['score']
        )
        for _, row in candidates_df.iterrows()
    ]


@router.get("/correlation/{ticker_a}/{ticker_b}", response_model=CorrelationDetail)
async def get_correlation_detail(
    ticker_a: str,
    ticker_b: str,
    timeframe: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    period: int = Query(90, description="過去何日分のデータを返すか"),
    db: Session = Depends(get_db)
):
    """
    ペア詳細（時系列グラフ用データ）
    """
    # 銘柄情報を取得
    ticker_a_info = db.query(Ticker).filter(Ticker.ticker_code == ticker_a).first()
    ticker_b_info = db.query(Ticker).filter(Ticker.ticker_code == ticker_b).first()

    if not ticker_a_info or not ticker_b_info:
        raise HTTPException(status_code=404, detail="Ticker not found")

    # 相関情報を取得
    correlation = db.query(Correlation).filter(
        Correlation.ticker_a == ticker_a,
        Correlation.ticker_b == ticker_b,
        Correlation.timeframe == timeframe
    ).first()

    if not correlation:
        raise HTTPException(status_code=404, detail="Correlation not found")

    lag = correlation.lag

    # リターンデータを取得
    calculator = ReturnCalculator(db)
    returns_df = calculator.load_returns_from_db(timeframe)

    if returns_df.empty or ticker_a not in returns_df.columns or ticker_b not in returns_df.columns:
        raise HTTPException(status_code=404, detail="Return data not found")

    # 直近period日分に絞る
    returns_df = returns_df.tail(period + lag)

    # 時系列データを構築
    dates = [d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
             for d in returns_df.index]
    returns_a = returns_df[ticker_a].fillna(0).tolist()

    # B銘柄はlag分シフト
    returns_b_shifted = returns_df[ticker_b].shift(-lag).fillna(0).tolist()

    # 過去のシグナルを取得
    backtest_engine = BacktestEngine(db)
    recent_signals = backtest_engine.get_recent_signals(
        returns_df=returns_df,
        ticker_a=ticker_a,
        ticker_b=ticker_b,
        lag=lag,
        direction=correlation.direction,
        n_signals=10
    )

    # ヒット率を取得
    from models import BacktestResult
    bt_result = db.query(BacktestResult).filter(
        BacktestResult.ticker_a == ticker_a,
        BacktestResult.ticker_b == ticker_b,
        BacktestResult.timeframe == timeframe,
        BacktestResult.lag == lag
    ).first()

    hit_rate = float(bt_result.hit_rate) if bt_result else None

    return CorrelationDetail(
        ticker_a=ticker_a,
        ticker_b=ticker_b,
        ticker_a_name=ticker_a_info.company_name,
        ticker_b_name=ticker_b_info.company_name,
        lag=lag,
        correlation=float(correlation.correlation),
        p_value=float(correlation.p_value),
        hit_rate=hit_rate,
        direction=correlation.direction,
        timeseries=TimeseriesData(
            dates=dates,
            returns_a=returns_a,
            returns_b_shifted=returns_b_shifted
        ),
        recent_signals=[
            RecentSignal(**signal)
            for signal in recent_signals
        ]
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings_endpoint(db: Session = Depends(get_db)):
    """
    現在の設定を取得
    """
    settings_dict = get_all_settings(db)
    return SettingsResponse(**settings_dict)


@router.post("/settings", response_model=SettingsResponse)
async def update_settings(
    settings_update: SettingsUpdate,
    db: Session = Depends(get_db)
):
    """
    設定を更新
    """
    update_dict = settings_update.model_dump(exclude_none=True)

    for key, value in update_dict.items():
        setting = db.query(Setting).filter(Setting.key == key).first()
        if setting:
            setting.value = str(value)
            setting.updated_at = datetime.now()
        else:
            db.add(Setting(key=key, value=str(value)))

    db.commit()

    # キャッシュを無効化
    cache_manager = get_cache_manager()
    cache_manager.invalidate_on_settings_change()

    return await get_settings_endpoint(db)


@router.post("/batch/run", response_model=BatchStatusResponse)
async def trigger_batch(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    手動バッチ実行トリガー
    """
    global batch_status

    if batch_status['status'] == 'running':
        return BatchStatusResponse(**batch_status)

    batch_status = {
        'status': 'running',
        'message': 'Daily batch started',
        'started_at': datetime.now(),
        'completed_at': None
    }

    # バックグラウンドでバッチ実行
    background_tasks.add_task(run_daily_batch)

    return BatchStatusResponse(**batch_status)


@router.get("/batch/status", response_model=BatchStatusResponse)
async def get_batch_status():
    """
    バッチ実行状態を取得
    """
    return BatchStatusResponse(**batch_status)


@router.get("/cache/info")
async def get_cache_info():
    """
    キャッシュ情報を取得
    """
    cache_manager = get_cache_manager()
    return cache_manager.get_cache_info()


@router.post("/cache/clear")
async def clear_cache():
    """
    キャッシュをクリア
    """
    cache_manager = get_cache_manager()
    cache_manager.invalidate_all()
    return {"status": "success", "message": "Cache cleared"}


async def run_daily_batch():
    """
    日次バッチ実行（非同期）
    """
    global batch_status

    try:
        from batch.daily_update import daily_batch_job
        daily_batch_job()

        batch_status['status'] = 'completed'
        batch_status['message'] = 'Daily batch completed successfully'
        batch_status['completed_at'] = datetime.now()

    except Exception as e:
        logger.error(f"Batch failed: {e}")
        batch_status['status'] = 'failed'
        batch_status['message'] = f'Batch failed: {str(e)}'
        batch_status['completed_at'] = datetime.now()

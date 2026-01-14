"""
トリガー検出モジュール
- 「今日動いた銘柄」の検出
- 候補銘柄Bのランキング
- スコア計算
"""
import logging
from datetime import date, datetime
from typing import Optional, List
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import and_, func

import sys
sys.path.append('..')
from config import get_settings
from models import DailyTrigger, Correlation, BacktestResult, Ticker

logger = logging.getLogger(__name__)
settings = get_settings()


class TriggerDetector:
    """トリガー検出クラス"""

    def __init__(self, db_session: Optional[Session] = None):
        self.session = db_session

    def detect_triggers(
        self,
        latest_returns: pd.Series,
        volume_data: pd.DataFrame,
        return_threshold: float = None,
        volume_threshold: float = None
    ) -> pd.DataFrame:
        """
        今日のトリガー銘柄を検出

        条件:
        - 条件1: |リターン| >= return_threshold (デフォルト2%)
        - 条件2: 出来高 >= 過去20日平均 × volume_threshold (デフォルト1.5倍)

        Args:
            latest_returns: 本日のリターン (Series, index=ticker_code)
            volume_data: 出来高データ (DataFrame, index=ticker_code)
            return_threshold: リターン閾値
            volume_threshold: 出来高倍率閾値

        Returns:
            DataFrame with columns: [ticker, return, volume_ratio]
        """
        return_threshold = return_threshold or settings.default_return_threshold
        volume_threshold = volume_threshold or settings.default_volume_threshold

        triggered = []

        for ticker in latest_returns.index:
            ret = latest_returns[ticker]

            if pd.isna(ret):
                continue

            # リターン閾値チェック
            if abs(ret) < return_threshold:
                continue

            # 出来高チェック（データがある場合）
            vol_ratio = 1.0
            if ticker in volume_data.index:
                today_vol = volume_data.loc[ticker, 'today_volume']
                avg_vol = volume_data.loc[ticker, 'avg_20d_volume']

                if avg_vol > 0:
                    vol_ratio = today_vol / avg_vol

                    # 出来高閾値チェック
                    if vol_ratio < volume_threshold:
                        continue

            triggered.append({
                'ticker': ticker,
                'return': float(ret),
                'volume_ratio': float(vol_ratio)
            })

        return pd.DataFrame(triggered)

    def find_candidate_pairs(
        self,
        trigger_ticker: str,
        correlations_df: pd.DataFrame,
        backtest_df: pd.DataFrame,
        top_n: int = 10
    ) -> pd.DataFrame:
        """
        トリガー銘柄に対する候補銘柄Bをランキング

        スコア計算:
        score = 0.4 * |correlation| + 0.4 * hit_rate + 0.2 * (1 - p_value_normalized)

        Args:
            trigger_ticker: トリガーとなった銘柄コード
            correlations_df: 相関分析結果
            backtest_df: バックテスト結果
            top_n: 上位何件返すか

        Returns:
            DataFrame with columns: [ticker_b, lag, correlation, p_value, hit_rate, direction, score]
        """
        # ticker_a == trigger_ticker のレコードを抽出
        candidates = correlations_df[
            correlations_df['ticker_a'] == trigger_ticker
        ].copy()

        if candidates.empty:
            return pd.DataFrame()

        # バックテスト結果をマージ
        if not backtest_df.empty:
            candidates = candidates.merge(
                backtest_df[['ticker_a', 'ticker_b', 'timeframe', 'lag', 'hit_rate']],
                on=['ticker_a', 'ticker_b', 'timeframe', 'lag'],
                how='left'
            )
        else:
            candidates['hit_rate'] = 0.5  # デフォルト値

        # 欠損値を補完
        candidates['hit_rate'] = candidates['hit_rate'].fillna(0.5)

        # p_valueの正規化（0-1スケール、小さいほど良い）
        max_pval = candidates['p_value'].max()
        if max_pval > 0:
            candidates['p_value_norm'] = 1 - (candidates['p_value'] / max_pval)
        else:
            candidates['p_value_norm'] = 0.5

        # スコア計算
        candidates['score'] = (
            0.4 * candidates['correlation'].abs() +
            0.4 * candidates['hit_rate'] +
            0.2 * candidates['p_value_norm']
        )

        # 上位top_n件を返す
        result = candidates.nlargest(top_n, 'score')[[
            'ticker_b', 'lag', 'correlation', 'p_value', 'hit_rate', 'direction', 'score'
        ]]

        return result

    def find_candidate_pairs_from_db(
        self,
        trigger_ticker: str,
        timeframe: str,
        top_n: int = 10
    ) -> pd.DataFrame:
        """
        DBから候補銘柄を検索

        Returns:
            DataFrame with columns including company_name
        """
        if self.session is None:
            raise ValueError("DB session is required")

        # 相関データを取得
        correlations = self.session.query(
            Correlation.ticker_b,
            Correlation.lag,
            Correlation.correlation,
            Correlation.p_value,
            Correlation.direction,
            Ticker.company_name
        ).join(
            Ticker, Correlation.ticker_b == Ticker.ticker_code
        ).filter(
            and_(
                Correlation.ticker_a == trigger_ticker,
                Correlation.timeframe == timeframe
            )
        ).all()

        if not correlations:
            return pd.DataFrame()

        corr_df = pd.DataFrame([{
            'ticker_b': c.ticker_b,
            'company_name': c.company_name,
            'lag': c.lag,
            'correlation': float(c.correlation),
            'p_value': float(c.p_value),
            'direction': c.direction
        } for c in correlations])

        # バックテスト結果を取得
        backtests = self.session.query(
            BacktestResult.ticker_b,
            BacktestResult.lag,
            BacktestResult.hit_rate
        ).filter(
            and_(
                BacktestResult.ticker_a == trigger_ticker,
                BacktestResult.timeframe == timeframe
            )
        ).all()

        if backtests:
            bt_df = pd.DataFrame([{
                'ticker_b': b.ticker_b,
                'lag': b.lag,
                'hit_rate': float(b.hit_rate) if b.hit_rate else 0.5
            } for b in backtests])

            corr_df = corr_df.merge(
                bt_df,
                on=['ticker_b', 'lag'],
                how='left'
            )
        else:
            corr_df['hit_rate'] = 0.5

        corr_df['hit_rate'] = corr_df['hit_rate'].fillna(0.5)

        # スコア計算
        max_pval = corr_df['p_value'].max()
        if max_pval > 0:
            corr_df['p_value_norm'] = 1 - (corr_df['p_value'] / max_pval)
        else:
            corr_df['p_value_norm'] = 0.5

        corr_df['score'] = (
            0.4 * corr_df['correlation'].abs() +
            0.4 * corr_df['hit_rate'] +
            0.2 * corr_df['p_value_norm']
        )

        return corr_df.nlargest(top_n, 'score')[[
            'ticker_b', 'company_name', 'lag', 'correlation',
            'p_value', 'hit_rate', 'direction', 'score'
        ]]

    def save_triggers_to_db(
        self,
        triggers_df: pd.DataFrame,
        trigger_date: date,
        timeframe: str
    ):
        """
        トリガー銘柄をDBに保存
        """
        if self.session is None:
            raise ValueError("DB session is required")

        for _, row in triggers_df.iterrows():
            stmt = insert(DailyTrigger).values(
                ticker_code=row['ticker'],
                date=trigger_date,
                timeframe=timeframe,
                return_value=float(row['return']),
                volume_ratio=float(row['volume_ratio'])
            ).on_conflict_do_update(
                index_elements=['ticker_code', 'date', 'timeframe'],
                set_={
                    'return_value': float(row['return']),
                    'volume_ratio': float(row['volume_ratio'])
                }
            )
            self.session.execute(stmt)

        self.session.commit()
        logger.info(f"{len(triggers_df)}件のトリガーをDBに保存しました")

    def get_triggers_from_db(
        self,
        trigger_date: date,
        timeframe: str
    ) -> pd.DataFrame:
        """
        DBからトリガー銘柄を取得
        """
        if self.session is None:
            raise ValueError("DB session is required")

        results = self.session.query(
            DailyTrigger.ticker_code,
            DailyTrigger.return_value,
            DailyTrigger.volume_ratio,
            Ticker.company_name
        ).join(
            Ticker, DailyTrigger.ticker_code == Ticker.ticker_code
        ).filter(
            and_(
                DailyTrigger.date == trigger_date,
                DailyTrigger.timeframe == timeframe
            )
        ).all()

        if not results:
            return pd.DataFrame()

        # 候補数を集計
        candidate_counts = {}
        for r in results:
            count = self.session.query(func.count(Correlation.id)).filter(
                and_(
                    Correlation.ticker_a == r.ticker_code,
                    Correlation.timeframe == timeframe
                )
            ).scalar()
            candidate_counts[r.ticker_code] = count

        data = [{
            'ticker': r.ticker_code,
            'company_name': r.company_name,
            'return': float(r.return_value),
            'volume_ratio': float(r.volume_ratio),
            'candidate_count': candidate_counts.get(r.ticker_code, 0)
        } for r in results]

        return pd.DataFrame(data)

    def get_latest_trigger_date(self, timeframe: str) -> Optional[date]:
        """
        最新のトリガー日付を取得
        """
        if self.session is None:
            raise ValueError("DB session is required")

        result = self.session.query(func.max(DailyTrigger.date)).filter(
            DailyTrigger.timeframe == timeframe
        ).scalar()

        return result

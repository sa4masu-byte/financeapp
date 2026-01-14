"""
バックテストモジュール
- ヒット率計算
- トリガー閾値の適用
- 負の相関対応（逆方向ヒット判定）
"""
import logging
from datetime import date
from typing import Dict, Optional, List
import numpy as np
import pandas as pd
from tqdm import tqdm
from sqlalchemy.orm import Session
from sqlalchemy import and_

import sys
sys.path.append('..')
from config import get_settings
from models import BacktestResult

logger = logging.getLogger(__name__)
settings = get_settings()


class BacktestEngine:
    """バックテストエンジン"""

    def __init__(self, db_session: Optional[Session] = None):
        self.session = db_session

    def calculate_hit_rate(
        self,
        returns_df: pd.DataFrame,
        ticker_a: str,
        ticker_b: str,
        lag: int,
        direction: str,
        trigger_threshold: float = None,
        response_threshold: float = None
    ) -> Dict[str, any]:
        """
        ヒット率計算

        定義:
        1. ticker_Aが±trigger_threshold以上動いた日を「トリガー」
        2. 正の相関: lag日後にticker_Bが同方向に動いたら「ヒット」
        3. 負の相関: lag日後にticker_Bが逆方向に動いたら「ヒット」
        4. ヒット率 = ヒット数 / トリガー数

        Args:
            returns_df: リターンデータ
            ticker_a: トリガー銘柄
            ticker_b: レスポンス銘柄
            lag: タイムラグ
            direction: 'positive' or 'negative'
            trigger_threshold: トリガー閾値
            response_threshold: レスポンス閾値

        Returns:
            {
                'hit_rate': 0.65,
                'total_signals': 120,
                'successful_signals': 78,
                'test_period_start': '2020-01-01',
                'test_period_end': '2025-12-31'
            }
        """
        trigger_threshold = trigger_threshold or settings.default_return_threshold
        response_threshold = response_threshold or settings.default_return_threshold

        if ticker_a not in returns_df.columns or ticker_b not in returns_df.columns:
            return {
                'hit_rate': 0.0,
                'total_signals': 0,
                'successful_signals': 0,
                'test_period_start': None,
                'test_period_end': None
            }

        a_returns = returns_df[ticker_a]
        b_returns = returns_df[ticker_b]

        # トリガー検出（閾値超えの日）
        trigger_mask = a_returns.abs() >= trigger_threshold
        trigger_dates = a_returns[trigger_mask].index.tolist()

        hits = 0
        total = 0

        # 日付インデックスをリストに変換
        all_dates = returns_df.index.tolist()

        for trigger_date in trigger_dates:
            # トリガー日のインデックスを取得
            try:
                trigger_idx = all_dates.index(trigger_date)
            except ValueError:
                continue

            # lag日後のインデックス
            future_idx = trigger_idx + lag
            if future_idx >= len(all_dates):
                continue

            future_date = all_dates[future_idx]

            # リターン取得
            a_return = a_returns[trigger_date]
            b_return = b_returns.get(future_date)

            if b_return is None or pd.isna(b_return):
                continue

            total += 1

            # ヒット判定
            a_direction = np.sign(a_return)

            if direction == 'positive':
                # 正の相関: 同方向に動くことを期待
                if (np.sign(b_return) == a_direction and
                    abs(b_return) >= response_threshold):
                    hits += 1
            else:
                # 負の相関: 逆方向に動くことを期待
                if (np.sign(b_return) == -a_direction and
                    abs(b_return) >= response_threshold):
                    hits += 1

        hit_rate = hits / total if total > 0 else 0.0

        # 期間情報
        valid_dates = returns_df.index.dropna()
        start_date = valid_dates.min() if len(valid_dates) > 0 else None
        end_date = valid_dates.max() if len(valid_dates) > 0 else None

        return {
            'hit_rate': hit_rate,
            'total_signals': total,
            'successful_signals': hits,
            'test_period_start': start_date,
            'test_period_end': end_date
        }

    def backtest_all_correlations(
        self,
        correlations_df: pd.DataFrame,
        returns_df: pd.DataFrame,
        trigger_threshold: float = None,
        response_threshold: float = None
    ) -> pd.DataFrame:
        """
        全相関ペアに対してバックテスト実行

        Args:
            correlations_df: 相関分析結果
            returns_df: リターンデータ
            trigger_threshold: トリガー閾値
            response_threshold: レスポンス閾値

        Returns:
            DataFrame with backtest results
        """
        results = []

        for _, row in tqdm(correlations_df.iterrows(), total=len(correlations_df), desc="バックテスト"):
            bt_result = self.calculate_hit_rate(
                returns_df=returns_df,
                ticker_a=row['ticker_a'],
                ticker_b=row['ticker_b'],
                lag=row['lag'],
                direction=row['direction'],
                trigger_threshold=trigger_threshold,
                response_threshold=response_threshold
            )

            if bt_result['total_signals'] > 0:
                results.append({
                    'ticker_a': row['ticker_a'],
                    'ticker_b': row['ticker_b'],
                    'timeframe': row['timeframe'],
                    'lag': row['lag'],
                    'hit_rate': bt_result['hit_rate'],
                    'total_signals': bt_result['total_signals'],
                    'successful_signals': bt_result['successful_signals'],
                    'test_period_start': bt_result['test_period_start'],
                    'test_period_end': bt_result['test_period_end']
                })

        logger.info(f"バックテスト完了: {len(results)}ペア")
        return pd.DataFrame(results)

    def get_recent_signals(
        self,
        returns_df: pd.DataFrame,
        ticker_a: str,
        ticker_b: str,
        lag: int,
        direction: str,
        n_signals: int = 10,
        trigger_threshold: float = None,
        response_threshold: float = None
    ) -> List[Dict]:
        """
        直近のシグナル履歴を取得

        Returns:
            List of {date, return_a, return_b, success}
        """
        trigger_threshold = trigger_threshold or settings.default_return_threshold
        response_threshold = response_threshold or settings.default_return_threshold

        if ticker_a not in returns_df.columns or ticker_b not in returns_df.columns:
            return []

        a_returns = returns_df[ticker_a]
        b_returns = returns_df[ticker_b]

        # トリガー検出
        trigger_mask = a_returns.abs() >= trigger_threshold
        trigger_dates = a_returns[trigger_mask].index.tolist()

        signals = []
        all_dates = returns_df.index.tolist()

        # 新しい順に処理
        for trigger_date in reversed(trigger_dates):
            if len(signals) >= n_signals:
                break

            try:
                trigger_idx = all_dates.index(trigger_date)
            except ValueError:
                continue

            future_idx = trigger_idx + lag
            if future_idx >= len(all_dates):
                continue

            future_date = all_dates[future_idx]

            a_return = a_returns[trigger_date]
            b_return = b_returns.get(future_date)

            if b_return is None or pd.isna(b_return):
                continue

            # ヒット判定
            a_direction = np.sign(a_return)
            if direction == 'positive':
                success = (np.sign(b_return) == a_direction and
                          abs(b_return) >= response_threshold)
            else:
                success = (np.sign(b_return) == -a_direction and
                          abs(b_return) >= response_threshold)

            # 日付を文字列に変換
            if hasattr(trigger_date, 'strftime'):
                date_str = trigger_date.strftime('%Y-%m-%d')
            else:
                date_str = str(trigger_date)

            signals.append({
                'date': date_str,
                'return_a': float(a_return),
                'return_b': float(b_return),
                'success': success
            })

        return signals

    def save_to_db(self, backtest_df: pd.DataFrame):
        """
        Save backtest results to DB (upsert)
        """
        if self.session is None:
            raise ValueError("DB session is required")

        count = 0
        for _, row in tqdm(backtest_df.iterrows(), total=len(backtest_df), desc="Saving backtest"):
            # Convert dates
            start_date = row['test_period_start']
            end_date = row['test_period_end']

            if hasattr(start_date, 'date'):
                start_date = start_date.date()
            if hasattr(end_date, 'date'):
                end_date = end_date.date()

            existing = self.session.query(BacktestResult).filter(
                and_(
                    BacktestResult.ticker_a == row['ticker_a'],
                    BacktestResult.ticker_b == row['ticker_b'],
                    BacktestResult.timeframe == row['timeframe'],
                    BacktestResult.lag == int(row['lag'])
                )
            ).first()

            if existing:
                existing.hit_rate = float(row['hit_rate'])
                existing.total_signals = int(row['total_signals'])
                existing.successful_signals = int(row['successful_signals'])
                existing.test_period_start = start_date
                existing.test_period_end = end_date
            else:
                self.session.add(BacktestResult(
                    ticker_a=row['ticker_a'],
                    ticker_b=row['ticker_b'],
                    timeframe=row['timeframe'],
                    lag=int(row['lag']),
                    hit_rate=float(row['hit_rate']),
                    total_signals=int(row['total_signals']),
                    successful_signals=int(row['successful_signals']),
                    test_period_start=start_date,
                    test_period_end=end_date
                ))
            count += 1

            if count % 1000 == 0:
                self.session.commit()

        self.session.commit()
        logger.info(f"{count} backtest records saved to DB")

    def load_from_db(
        self,
        timeframe: str,
        ticker_a: Optional[str] = None
    ) -> pd.DataFrame:
        """
        DBからバックテスト結果を読み込み
        """
        if self.session is None:
            raise ValueError("DB session is required")

        query = self.session.query(BacktestResult).filter(
            BacktestResult.timeframe == timeframe
        )

        if ticker_a:
            query = query.filter(BacktestResult.ticker_a == ticker_a)

        results = query.all()

        if not results:
            return pd.DataFrame()

        data = [{
            'ticker_a': r.ticker_a,
            'ticker_b': r.ticker_b,
            'timeframe': r.timeframe,
            'lag': r.lag,
            'hit_rate': float(r.hit_rate) if r.hit_rate else 0.0,
            'total_signals': r.total_signals,
            'successful_signals': r.successful_signals,
            'test_period_start': r.test_period_start,
            'test_period_end': r.test_period_end
        } for r in results]

        return pd.DataFrame(data)

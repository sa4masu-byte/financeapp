"""
リターン計算モジュール
- 対数リターン計算
- TOPIX控除（市場要因除去）
- 日足→週足・月足への変換
"""
import logging
from datetime import date
from typing import Dict, Optional
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import and_

import sys
sys.path.append('..')
from models import Return, DailyPrice

logger = logging.getLogger(__name__)


class ReturnCalculator:
    """リターン計算クラス"""

    def __init__(self, db_session: Optional[Session] = None):
        self.session = db_session

    @staticmethod
    def calculate_log_returns(prices: pd.Series) -> pd.Series:
        """
        対数リターン: ln(P_t / P_{t-1})

        Args:
            prices: 調整後終値の時系列

        Returns:
            対数リターン系列（最初の値はNaN）
        """
        return np.log(prices / prices.shift(1))

    @staticmethod
    def subtract_market_return(
        individual_returns: pd.DataFrame,
        topix_returns: pd.Series
    ) -> pd.DataFrame:
        """
        TOPIX控除: 個別株リターン - 市場リターン

        Args:
            individual_returns: 各銘柄のリターン (columns: ticker_code)
            topix_returns: TOPIXのリターン系列

        Returns:
            TOPIX控除済みリターン（超過リターン）
        """
        # 日付を揃える
        common_dates = individual_returns.index.intersection(topix_returns.index)
        individual_returns = individual_returns.loc[common_dates]
        topix_returns = topix_returns.loc[common_dates]

        # 各銘柄から市場リターンを引く
        adjusted = individual_returns.sub(topix_returns, axis=0)
        return adjusted

    @staticmethod
    def resample_to_weekly(daily_returns: pd.DataFrame) -> pd.DataFrame:
        """
        週足リターン: 金曜日基準でリサンプリング

        Returns:
            週次リターン（各週の累積リターン）
        """
        # インデックスをdatetimeに変換
        daily_returns.index = pd.to_datetime(daily_returns.index)
        return daily_returns.resample('W-FRI').sum()

    @staticmethod
    def resample_to_monthly(daily_returns: pd.DataFrame) -> pd.DataFrame:
        """
        月足リターン: 月末基準でリサンプリング
        """
        daily_returns.index = pd.to_datetime(daily_returns.index)
        return daily_returns.resample('M').sum()

    def calculate_all_returns(
        self,
        price_data: Dict[str, pd.DataFrame],
        topix_prices: pd.Series
    ) -> Dict[str, pd.DataFrame]:
        """
        全銘柄・全タイムフレームのリターンを計算

        Args:
            price_data: {ticker_code: DataFrame with adj_close}
            topix_prices: TOPIX価格系列

        Returns:
            {
                'daily': DataFrame (columns: ticker_codes, index: dates),
                'weekly': DataFrame,
                'monthly': DataFrame
            }
        """
        # 各銘柄の価格をDataFrameに統合
        prices_df = pd.DataFrame({
            ticker: df['adj_close']
            for ticker, df in price_data.items()
        })

        # 対数リターン計算
        individual_returns = prices_df.apply(self.calculate_log_returns)

        # TOPIXリターン
        topix_returns = self.calculate_log_returns(topix_prices)

        # TOPIX控除
        adjusted_daily = self.subtract_market_return(individual_returns, topix_returns)

        # NaN除去（最初の1日）
        adjusted_daily = adjusted_daily.dropna(how='all')

        # 週足・月足へ変換
        adjusted_weekly = self.resample_to_weekly(adjusted_daily.copy())
        adjusted_monthly = self.resample_to_monthly(adjusted_daily.copy())

        return {
            'daily': adjusted_daily,
            'weekly': adjusted_weekly,
            'monthly': adjusted_monthly
        }

    def calculate_raw_returns(
        self,
        price_data: Dict[str, pd.DataFrame]
    ) -> Dict[str, pd.DataFrame]:
        """
        TOPIX控除なしの生リターンを計算

        Returns:
            {
                'daily': DataFrame,
                'weekly': DataFrame,
                'monthly': DataFrame
            }
        """
        # 各銘柄の価格をDataFrameに統合
        prices_df = pd.DataFrame({
            ticker: df['adj_close']
            for ticker, df in price_data.items()
        })

        # 対数リターン計算
        raw_daily = prices_df.apply(self.calculate_log_returns)
        raw_daily = raw_daily.dropna(how='all')

        raw_weekly = self.resample_to_weekly(raw_daily.copy())
        raw_monthly = self.resample_to_monthly(raw_daily.copy())

        return {
            'daily': raw_daily,
            'weekly': raw_weekly,
            'monthly': raw_monthly
        }

    def save_returns_to_db(
        self,
        adjusted_returns: pd.DataFrame,
        raw_returns: pd.DataFrame,
        timeframe: str
    ):
        """
        Save return data to DB (upsert)

        Args:
            adjusted_returns: TOPIX-adjusted returns
            raw_returns: Raw returns
            timeframe: 'daily', 'weekly', 'monthly'
        """
        if self.session is None:
            raise ValueError("DB session is required")

        count = 0
        for date_val in adjusted_returns.index:
            for ticker in adjusted_returns.columns:
                adj_ret = adjusted_returns.loc[date_val, ticker]
                raw_ret = raw_returns.loc[date_val, ticker] if date_val in raw_returns.index else None

                if pd.isna(adj_ret):
                    continue

                # Convert to date object
                if hasattr(date_val, 'date'):
                    date_obj = date_val.date()
                else:
                    date_obj = date_val

                return_value = float(raw_ret) if raw_ret is not None and not pd.isna(raw_ret) else None
                adj_return_value = float(adj_ret)

                existing = self.session.query(Return).filter(
                    and_(
                        Return.ticker_code == ticker,
                        Return.date == date_obj,
                        Return.timeframe == timeframe
                    )
                ).first()

                if existing:
                    existing.return_value = return_value
                    existing.topix_adjusted_return = adj_return_value
                else:
                    self.session.add(Return(
                        ticker_code=ticker,
                        date=date_obj,
                        timeframe=timeframe,
                        return_value=return_value,
                        topix_adjusted_return=adj_return_value
                    ))
                count += 1

                # Batch commit
                if count % 10000 == 0:
                    self.session.commit()
                    logger.info(f"{timeframe}: {count} records saved...")

        self.session.commit()
        logger.info(f"{timeframe}: Total {count} records saved")

    def load_returns_from_db(
        self,
        timeframe: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> pd.DataFrame:
        """
        DBからリターンデータを読み込み

        Args:
            timeframe: 'daily', 'weekly', 'monthly'
            start_date: 開始日
            end_date: 終了日

        Returns:
            DataFrame (columns: ticker_codes, index: dates)
        """
        if self.session is None:
            raise ValueError("DB session is required")

        query = self.session.query(
            Return.ticker_code,
            Return.date,
            Return.topix_adjusted_return
        ).filter(Return.timeframe == timeframe)

        if start_date:
            query = query.filter(Return.date >= start_date)
        if end_date:
            query = query.filter(Return.date <= end_date)

        results = query.all()

        if not results:
            return pd.DataFrame()

        # DataFrameに変換
        df = pd.DataFrame(results, columns=['ticker_code', 'date', 'return'])
        df_pivot = df.pivot(index='date', columns='ticker_code', values='return')
        df_pivot.index = pd.to_datetime(df_pivot.index)

        return df_pivot

    def get_latest_returns(
        self,
        timeframe: str,
        n_days: int = 1
    ) -> pd.DataFrame:
        """
        最新のリターンデータを取得

        Args:
            timeframe: 'daily', 'weekly', 'monthly'
            n_days: 取得する期間数

        Returns:
            DataFrame (columns: ticker_codes, index: dates)
        """
        if self.session is None:
            raise ValueError("DB session is required")

        # 最新日付を取得
        latest_date = self.session.query(Return.date).filter(
            Return.timeframe == timeframe
        ).order_by(Return.date.desc()).first()

        if not latest_date:
            return pd.DataFrame()

        latest_date = latest_date[0]

        # 最新n期間分を取得
        query = self.session.query(
            Return.ticker_code,
            Return.date,
            Return.topix_adjusted_return,
            Return.return_value
        ).filter(
            Return.timeframe == timeframe
        ).order_by(Return.date.desc())

        results = query.all()

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results, columns=['ticker_code', 'date', 'adjusted_return', 'raw_return'])

        # 最新n期間の日付を取得
        unique_dates = sorted(df['date'].unique(), reverse=True)[:n_days]

        # フィルタリング
        df = df[df['date'].isin(unique_dates)]

        return df

    def get_volume_data(
        self,
        tickers: list,
        lookback_days: int = 20
    ) -> pd.DataFrame:
        """
        出来高データを取得（トリガー検出用）

        Returns:
            DataFrame with columns: [ticker_code, today_volume, avg_20d_volume]
        """
        if self.session is None:
            raise ValueError("DB session is required")

        results = []

        for ticker in tickers:
            # 最新の出来高データを取得
            prices = self.session.query(
                DailyPrice.date,
                DailyPrice.volume
            ).filter(
                DailyPrice.ticker_code == ticker
            ).order_by(DailyPrice.date.desc()).limit(lookback_days + 1).all()

            if len(prices) < 2:
                continue

            today_volume = prices[0][1] or 0
            past_volumes = [p[1] for p in prices[1:] if p[1] is not None]

            if past_volumes:
                avg_volume = sum(past_volumes) / len(past_volumes)
                results.append({
                    'ticker_code': ticker,
                    'today_volume': today_volume,
                    'avg_20d_volume': avg_volume
                })

        return pd.DataFrame(results).set_index('ticker_code')

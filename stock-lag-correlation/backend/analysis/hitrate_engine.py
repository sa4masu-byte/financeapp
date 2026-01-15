"""
ヒット率重視の相関分析エンジン
- 大きく動いた日のみに着目
- 実際の勝率（ヒット率）を計算
"""
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import numpy as np
import pandas as pd
from tqdm import tqdm
from sqlalchemy.orm import Session

import sys
sys.path.append('..')
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class HitRateEngine:
    """ヒット率重視の分析エンジン"""

    def __init__(
        self,
        move_threshold: float = 0.02,  # 2%以上の動きをトリガーとする
        min_hit_rate: float = 0.55,    # 最低ヒット率55%
        min_samples: int = 30,          # 最低サンプル数
        db_session: Optional[Session] = None
    ):
        self.move_threshold = move_threshold
        self.min_hit_rate = min_hit_rate
        self.min_samples = min_samples
        self.session = db_session

    def analyze_pair(
        self,
        returns_a: pd.Series,
        returns_b: pd.Series,
        lag: int
    ) -> Dict:
        """
        ペアのヒット率を計算

        Args:
            returns_a: A銘柄のリターン系列
            returns_b: B銘柄のリターン系列
            lag: ラグ日数

        Returns:
            {
                'hit_rate': float,
                'total_signals': int,
                'hits': int,
                'avg_return': float,  # ヒット時の平均リターン
                'direction': str      # 'positive' or 'negative'
            }
        """
        # A銘柄が大きく動いた日を特定
        big_moves_up = returns_a > self.move_threshold
        big_moves_down = returns_a < -self.move_threshold

        results = {'positive': None, 'negative': None}

        # 正の相関（Aが上がったらBも上がる）
        pos_hits = 0
        pos_total = 0
        pos_returns = []

        for i in range(len(returns_a) - lag):
            if big_moves_up.iloc[i]:
                pos_total += 1
                b_return = returns_b.iloc[i + lag]
                if not np.isnan(b_return):
                    if b_return > 0:
                        pos_hits += 1
                        pos_returns.append(b_return)
                    elif b_return < 0:
                        pos_returns.append(b_return)

            elif big_moves_down.iloc[i]:
                pos_total += 1
                b_return = returns_b.iloc[i + lag]
                if not np.isnan(b_return):
                    if b_return < 0:
                        pos_hits += 1
                        pos_returns.append(abs(b_return))
                    elif b_return > 0:
                        pos_returns.append(-b_return)

        if pos_total >= self.min_samples:
            results['positive'] = {
                'hit_rate': pos_hits / pos_total,
                'total_signals': pos_total,
                'hits': pos_hits,
                'avg_return': np.mean(pos_returns) if pos_returns else 0,
                'direction': 'positive'
            }

        # 負の相関（Aが上がったらBは下がる）
        neg_hits = 0
        neg_total = 0
        neg_returns = []

        for i in range(len(returns_a) - lag):
            if big_moves_up.iloc[i]:
                neg_total += 1
                b_return = returns_b.iloc[i + lag]
                if not np.isnan(b_return):
                    if b_return < 0:
                        neg_hits += 1
                        neg_returns.append(abs(b_return))
                    elif b_return > 0:
                        neg_returns.append(-b_return)

            elif big_moves_down.iloc[i]:
                neg_total += 1
                b_return = returns_b.iloc[i + lag]
                if not np.isnan(b_return):
                    if b_return > 0:
                        neg_hits += 1
                        neg_returns.append(b_return)
                    elif b_return < 0:
                        neg_returns.append(-abs(b_return))

        if neg_total >= self.min_samples:
            results['negative'] = {
                'hit_rate': neg_hits / neg_total,
                'total_signals': neg_total,
                'hits': neg_hits,
                'avg_return': np.mean(neg_returns) if neg_returns else 0,
                'direction': 'negative'
            }

        return results

    def analyze_all_pairs(
        self,
        returns_df: pd.DataFrame,
        timeframe: str,
        max_lag: int
    ) -> pd.DataFrame:
        """
        全ペアのヒット率分析

        Args:
            returns_df: リターンデータ (columns: ticker_codes)
            timeframe: 'daily', 'weekly', 'monthly'
            max_lag: 最大ラグ

        Returns:
            DataFrame with high hit-rate pairs
        """
        tickers = returns_df.columns.tolist()
        n_tickers = len(tickers)

        logger.info(f"ヒット率分析開始: {n_tickers}銘柄, {timeframe}, max_lag={max_lag}")
        logger.info(f"閾値: 動き{self.move_threshold*100:.1f}%以上, ヒット率{self.min_hit_rate*100:.0f}%以上")

        results = []

        total_pairs = n_tickers * (n_tickers - 1) * max_lag
        with tqdm(total=total_pairs, desc="ヒット率計算") as pbar:
            for i, ticker_a in enumerate(tickers):
                for j, ticker_b in enumerate(tickers):
                    if i == j:
                        pbar.update(max_lag)
                        continue

                    returns_a = returns_df[ticker_a].dropna()
                    returns_b = returns_df[ticker_b].dropna()

                    # 共通の日付のみ
                    common_idx = returns_a.index.intersection(returns_b.index)
                    if len(common_idx) < self.min_samples + max_lag:
                        pbar.update(max_lag)
                        continue

                    returns_a = returns_a.loc[common_idx]
                    returns_b = returns_b.loc[common_idx]

                    for lag in range(1, max_lag + 1):
                        pair_results = self.analyze_pair(returns_a, returns_b, lag)

                        for direction in ['positive', 'negative']:
                            if pair_results[direction] is not None:
                                r = pair_results[direction]
                                if r['hit_rate'] >= self.min_hit_rate:
                                    results.append({
                                        'ticker_a': ticker_a,
                                        'ticker_b': ticker_b,
                                        'timeframe': timeframe,
                                        'lag': lag,
                                        'hit_rate': r['hit_rate'],
                                        'total_signals': r['total_signals'],
                                        'hits': r['hits'],
                                        'avg_return': r['avg_return'],
                                        'direction': direction
                                    })

                        pbar.update(1)

        df = pd.DataFrame(results)

        if not df.empty:
            # ヒット率でソート
            df = df.sort_values('hit_rate', ascending=False)
            logger.info(f"ヒット率{self.min_hit_rate*100:.0f}%以上のペア: {len(df)}件")
        else:
            logger.info("条件を満たすペアが見つかりませんでした")

        return df

    def get_top_pairs(
        self,
        results_df: pd.DataFrame,
        top_n: int = 50
    ) -> pd.DataFrame:
        """
        上位N件のペアを取得
        """
        if results_df.empty:
            return results_df

        return results_df.head(top_n)

    def print_summary(self, results_df: pd.DataFrame):
        """
        結果サマリーを表示
        """
        if results_df.empty:
            print("結果がありません")
            return

        print("\n" + "=" * 70)
        print("ヒット率分析結果サマリー")
        print("=" * 70)

        print(f"\n総ペア数: {len(results_df)}")
        print(f"平均ヒット率: {results_df['hit_rate'].mean()*100:.1f}%")
        print(f"最高ヒット率: {results_df['hit_rate'].max()*100:.1f}%")

        print("\n【トップ20ペア】")
        print("-" * 70)
        for idx, row in results_df.head(20).iterrows():
            direction_jp = "順" if row['direction'] == 'positive' else "逆"
            print(f"{row['ticker_a']} → {row['ticker_b']} "
                  f"(lag={row['lag']}日, {direction_jp}相関) "
                  f"ヒット率: {row['hit_rate']*100:.1f}% "
                  f"({row['hits']}/{row['total_signals']}回)")

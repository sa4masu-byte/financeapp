"""
タイムラグ相関分析エンジン
- Numba JIT最適化
- 統計的有意性検定（p-value）
- 多重検定補正（Bonferroni）
"""
import logging
from typing import List, Tuple, Optional
from datetime import datetime
import numpy as np
import pandas as pd
from scipy import stats
from numba import jit, prange
from tqdm import tqdm
from sqlalchemy.orm import Session
from sqlalchemy import and_

import sys
sys.path.append('..')
from config import get_settings
from models import Correlation

logger = logging.getLogger(__name__)
settings = get_settings()


@jit(nopython=True, cache=True)
def _calculate_correlation_numba(a: np.ndarray, b: np.ndarray) -> float:
    """
    Numba最適化版相関係数計算

    Args:
        a: 配列A
        b: 配列B（同じ長さ）

    Returns:
        相関係数
    """
    n = len(a)
    if n == 0:
        return 0.0

    mean_a = np.mean(a)
    mean_b = np.mean(b)

    # 共分散
    cov = 0.0
    var_a = 0.0
    var_b = 0.0

    for i in range(n):
        diff_a = a[i] - mean_a
        diff_b = b[i] - mean_b
        cov += diff_a * diff_b
        var_a += diff_a * diff_a
        var_b += diff_b * diff_b

    if var_a == 0.0 or var_b == 0.0:
        return 0.0

    return cov / np.sqrt(var_a * var_b)


@jit(nopython=True, parallel=True, cache=True)
def _calculate_all_lagged_correlations(
    data_matrix: np.ndarray,
    max_lag: int
) -> np.ndarray:
    """
    全ペアのラグ相関を並列計算（Numba最適化）

    Args:
        data_matrix: (n_dates, n_tickers) の行列
        max_lag: 最大ラグ

    Returns:
        (n_tickers, n_tickers, max_lag) の相関係数行列
    """
    n_tickers = data_matrix.shape[1]
    result = np.zeros((n_tickers, n_tickers, max_lag))

    for i in prange(n_tickers):
        for j in range(n_tickers):
            if i == j:
                continue

            series_a = data_matrix[:, i]
            series_b = data_matrix[:, j]

            for lag in range(1, max_lag + 1):
                # A[:-lag] vs B[lag:]
                a_lagged = series_a[:-lag]
                b_shifted = series_b[lag:]

                # NaNチェック（Numbaでは限定的）
                valid_mask = np.isfinite(a_lagged) & np.isfinite(b_shifted)
                valid_count = np.sum(valid_mask)

                if valid_count < 30:  # 最低30データポイント
                    result[i, j, lag - 1] = 0.0
                    continue

                # 有効なデータのみ抽出
                a_valid = a_lagged[valid_mask]
                b_valid = b_shifted[valid_mask]

                corr = _calculate_correlation_numba(a_valid, b_valid)
                result[i, j, lag - 1] = corr

    return result


class CorrelationEngine:
    """相関分析エンジン"""

    def __init__(
        self,
        min_correlation: float = None,
        alpha: float = None,
        db_session: Optional[Session] = None
    ):
        self.min_correlation = min_correlation or settings.default_min_correlation
        self.alpha = alpha or settings.default_significance_level
        self.session = db_session

    def analyze_all_pairs(
        self,
        returns_df: pd.DataFrame,
        timeframe: str,
        max_lag: int,
        use_bonferroni: bool = True
    ) -> pd.DataFrame:
        """
        全ペア組み合わせでタイムラグ相関を計算

        Args:
            returns_df: TOPIX控除済みリターン (columns: ticker_code, index: dates)
            timeframe: "daily" | "weekly" | "monthly"
            max_lag: 最大ラグ
            use_bonferroni: Bonferroni補正を使用するか

        Returns:
            DataFrame with columns: [ticker_a, ticker_b, lag, correlation, p_value, direction]
        """
        tickers = returns_df.columns.tolist()
        n_tickers = len(tickers)

        logger.info(f"相関分析開始: {n_tickers}銘柄, {timeframe}, max_lag={max_lag}")

        # Bonferroni補正
        n_tests = n_tickers * (n_tickers - 1) * max_lag
        alpha_corrected = self.alpha / n_tests if use_bonferroni else self.alpha

        logger.info(f"有意水準: {self.alpha} -> {alpha_corrected:.2e} (Bonferroni補正)")

        # データを行列に変換（Numba用）
        data_matrix = returns_df.values.astype(np.float64)

        logger.info("Numba並列計算を実行中...")
        # 初回はコンパイルに時間がかかる
        correlation_matrix = _calculate_all_lagged_correlations(data_matrix, max_lag)

        # 結果を抽出
        results = []
        logger.info("有意な相関を抽出中...")

        for i in tqdm(range(n_tickers), desc="相関抽出"):
            ticker_a = tickers[i]

            for j in range(n_tickers):
                if i == j:
                    continue

                ticker_b = tickers[j]

                for lag_idx in range(max_lag):
                    lag = lag_idx + 1
                    corr = correlation_matrix[i, j, lag_idx]

                    # 相関閾値チェック
                    if abs(corr) < self.min_correlation:
                        continue

                    # p-value計算（SciPy使用）
                    p_value = self._calculate_p_value(
                        returns_df[ticker_a].values,
                        returns_df[ticker_b].values,
                        lag
                    )

                    # 有意性チェック
                    if p_value >= alpha_corrected:
                        continue

                    results.append({
                        'ticker_a': ticker_a,
                        'ticker_b': ticker_b,
                        'timeframe': timeframe,
                        'lag': lag,
                        'correlation': float(corr),
                        'p_value': float(p_value),
                        'direction': 'positive' if corr > 0 else 'negative'
                    })

        logger.info(f"有意な相関ペア: {len(results)}件")
        return pd.DataFrame(results)

    def _calculate_p_value(
        self,
        a: np.ndarray,
        b: np.ndarray,
        lag: int
    ) -> float:
        """
        p-value計算（scipy.stats.pearsonr使用）

        Returns:
            p-value (0-1)
        """
        a_lagged = a[:-lag]
        b_shifted = b[lag:]

        # NaN除去
        valid_mask = ~(np.isnan(a_lagged) | np.isnan(b_shifted))
        a_valid = a_lagged[valid_mask]
        b_valid = b_shifted[valid_mask]

        if len(a_valid) < 30:
            return 1.0  # データ不足

        try:
            _, p_val = stats.pearsonr(a_valid, b_valid)
            return p_val
        except Exception:
            return 1.0

    def calculate_single_pair(
        self,
        returns_df: pd.DataFrame,
        ticker_a: str,
        ticker_b: str,
        max_lag: int
    ) -> List[dict]:
        """
        単一ペアのラグ相関を計算

        Returns:
            List of {lag, correlation, p_value, direction}
        """
        if ticker_a not in returns_df.columns or ticker_b not in returns_df.columns:
            return []

        a_values = returns_df[ticker_a].values
        b_values = returns_df[ticker_b].values

        results = []

        for lag in range(1, max_lag + 1):
            a_lagged = a_values[:-lag]
            b_shifted = b_values[lag:]

            # NaN除去
            valid_mask = ~(np.isnan(a_lagged) | np.isnan(b_shifted))
            a_valid = a_lagged[valid_mask]
            b_valid = b_shifted[valid_mask]

            if len(a_valid) < 30:
                continue

            corr = _calculate_correlation_numba(a_valid, b_valid)

            try:
                _, p_val = stats.pearsonr(a_valid, b_valid)
            except Exception:
                p_val = 1.0

            results.append({
                'lag': lag,
                'correlation': float(corr),
                'p_value': float(p_val),
                'direction': 'positive' if corr > 0 else 'negative'
            })

        return results

    def detect_circular_correlations(
        self,
        correlations_df: pd.DataFrame,
        min_correlation: float = 0.3
    ) -> pd.DataFrame:
        """
        循環相関検出: A→B と B→A が両方強い場合

        Returns:
            DataFrame with columns: [ticker_a, ticker_b, lag_ab, lag_ba, corr_ab, corr_ba]
        """
        # ペアをキーにした辞書を作成
        pair_dict = {}

        for _, row in correlations_df.iterrows():
            key = (row['ticker_a'], row['ticker_b'])
            if key not in pair_dict or abs(row['correlation']) > abs(pair_dict[key]['correlation']):
                pair_dict[key] = row

        # 循環ペアを検出
        circular = []

        for (a, b), row_ab in pair_dict.items():
            reverse_key = (b, a)
            if reverse_key in pair_dict:
                row_ba = pair_dict[reverse_key]

                if (abs(row_ab['correlation']) >= min_correlation and
                    abs(row_ba['correlation']) >= min_correlation):
                    circular.append({
                        'ticker_a': a,
                        'ticker_b': b,
                        'lag_ab': row_ab['lag'],
                        'lag_ba': row_ba['lag'],
                        'corr_ab': row_ab['correlation'],
                        'corr_ba': row_ba['correlation']
                    })

        return pd.DataFrame(circular)

    def save_to_db(self, correlations_df: pd.DataFrame):
        """
        Save correlation results to DB (upsert)
        """
        if self.session is None:
            raise ValueError("DB session is required")

        count = 0
        for _, row in tqdm(correlations_df.iterrows(), total=len(correlations_df), desc="Saving to DB"):
            existing = self.session.query(Correlation).filter(
                and_(
                    Correlation.ticker_a == row['ticker_a'],
                    Correlation.ticker_b == row['ticker_b'],
                    Correlation.timeframe == row['timeframe'],
                    Correlation.lag == int(row['lag'])
                )
            ).first()

            if existing:
                existing.correlation = float(row['correlation'])
                existing.p_value = float(row['p_value'])
                existing.direction = row['direction']
                existing.calculated_at = datetime.now()
            else:
                self.session.add(Correlation(
                    ticker_a=row['ticker_a'],
                    ticker_b=row['ticker_b'],
                    timeframe=row['timeframe'],
                    lag=int(row['lag']),
                    correlation=float(row['correlation']),
                    p_value=float(row['p_value']),
                    direction=row['direction'],
                    calculated_at=datetime.now()
                ))
            count += 1

            if count % 1000 == 0:
                self.session.commit()

        self.session.commit()
        logger.info(f"{count} correlation records saved to DB")

    def load_from_db(
        self,
        timeframe: str,
        ticker_a: Optional[str] = None
    ) -> pd.DataFrame:
        """
        DBから相関データを読み込み
        """
        if self.session is None:
            raise ValueError("DB session is required")

        query = self.session.query(Correlation).filter(
            Correlation.timeframe == timeframe
        )

        if ticker_a:
            query = query.filter(Correlation.ticker_a == ticker_a)

        results = query.all()

        if not results:
            return pd.DataFrame()

        data = [{
            'ticker_a': r.ticker_a,
            'ticker_b': r.ticker_b,
            'timeframe': r.timeframe,
            'lag': r.lag,
            'correlation': float(r.correlation),
            'p_value': float(r.p_value),
            'direction': r.direction
        } for r in results]

        return pd.DataFrame(data)

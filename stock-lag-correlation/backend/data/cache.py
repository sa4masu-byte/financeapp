"""
キャッシュ管理モジュール
- 相関分析結果のファイルキャッシュ
- 候補銘柄のメモリキャッシュ（LRU + TTL）
- トリガー銘柄のメモリキャッシュ
"""
import logging
import pickle
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from functools import lru_cache
import threading
import pandas as pd

import sys
sys.path.append('..')
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TTLCache:
    """TTL付きキャッシュ"""

    def __init__(self, maxsize: int = 1000, ttl_seconds: int = 3600):
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """キャッシュから取得"""
        with self._lock:
            if key not in self._cache:
                return None

            value, timestamp = self._cache[key]

            # TTLチェック
            if datetime.now() - timestamp > timedelta(seconds=self.ttl_seconds):
                del self._cache[key]
                return None

            return value

    def set(self, key: str, value: Any):
        """キャッシュに保存"""
        with self._lock:
            # サイズ制限チェック
            if len(self._cache) >= self.maxsize:
                self._evict_oldest()

            self._cache[key] = (value, datetime.now())

    def _evict_oldest(self):
        """最も古いエントリを削除"""
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k][1]
        )
        del self._cache[oldest_key]

    def clear(self):
        """キャッシュをクリア"""
        with self._lock:
            self._cache.clear()

    def invalidate(self, key: str):
        """特定のキーを無効化"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]


class CacheManager:
    """統合キャッシュマネージャー"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # メモリキャッシュ
        self.candidate_cache = TTLCache(
            maxsize=settings.candidate_cache_maxsize,
            ttl_seconds=settings.candidate_cache_ttl
        )
        self.trigger_cache = TTLCache(
            maxsize=100,
            ttl_seconds=86400  # 24時間
        )

        # 相関結果キャッシュ（メモリ上）
        self._correlation_cache: Optional[pd.DataFrame] = None
        self._backtest_cache: Optional[pd.DataFrame] = None
        self._cache_loaded = False

    # === ファイルキャッシュ（相関結果）===

    def _get_correlation_cache_path(self, timeframe: str) -> Path:
        """相関キャッシュファイルパス"""
        return self.cache_dir / f"correlations_{timeframe}.pkl"

    def _get_backtest_cache_path(self, timeframe: str) -> Path:
        """バックテストキャッシュファイルパス"""
        return self.cache_dir / f"backtest_{timeframe}.pkl"

    def save_correlations(self, df: pd.DataFrame, timeframe: str):
        """相関結果をファイルに保存"""
        path = self._get_correlation_cache_path(timeframe)
        try:
            with open(path, 'wb') as f:
                pickle.dump({
                    'data': df,
                    'timestamp': datetime.now()
                }, f)
            logger.info(f"相関キャッシュを保存: {path}")
        except Exception as e:
            logger.error(f"相関キャッシュ保存失敗: {e}")

    def load_correlations(self, timeframe: str) -> Optional[pd.DataFrame]:
        """相関結果をファイルから読み込み"""
        path = self._get_correlation_cache_path(timeframe)
        if not path.exists():
            return None

        try:
            with open(path, 'rb') as f:
                cache_data = pickle.load(f)

            logger.info(f"相関キャッシュを読み込み: {path} (作成: {cache_data['timestamp']})")
            return cache_data['data']
        except Exception as e:
            logger.error(f"相関キャッシュ読み込み失敗: {e}")
            return None

    def save_backtest_results(self, df: pd.DataFrame, timeframe: str):
        """バックテスト結果をファイルに保存"""
        path = self._get_backtest_cache_path(timeframe)
        try:
            with open(path, 'wb') as f:
                pickle.dump({
                    'data': df,
                    'timestamp': datetime.now()
                }, f)
            logger.info(f"バックテストキャッシュを保存: {path}")
        except Exception as e:
            logger.error(f"バックテストキャッシュ保存失敗: {e}")

    def load_backtest_results(self, timeframe: str) -> Optional[pd.DataFrame]:
        """バックテスト結果をファイルから読み込み"""
        path = self._get_backtest_cache_path(timeframe)
        if not path.exists():
            return None

        try:
            with open(path, 'rb') as f:
                cache_data = pickle.load(f)

            logger.info(f"バックテストキャッシュを読み込み: {path}")
            return cache_data['data']
        except Exception as e:
            logger.error(f"バックテストキャッシュ読み込み失敗: {e}")
            return None

    # === メモリキャッシュ（候補銘柄）===

    def _make_candidate_key(
        self,
        trigger_ticker: str,
        timeframe: str,
        top_n: int
    ) -> str:
        """候補銘柄キャッシュのキー生成"""
        return f"candidate:{trigger_ticker}:{timeframe}:{top_n}"

    def get_candidates(
        self,
        trigger_ticker: str,
        timeframe: str,
        top_n: int
    ) -> Optional[pd.DataFrame]:
        """候補銘柄をキャッシュから取得"""
        key = self._make_candidate_key(trigger_ticker, timeframe, top_n)
        return self.candidate_cache.get(key)

    def set_candidates(
        self,
        trigger_ticker: str,
        timeframe: str,
        top_n: int,
        candidates: pd.DataFrame
    ):
        """候補銘柄をキャッシュに保存"""
        key = self._make_candidate_key(trigger_ticker, timeframe, top_n)
        self.candidate_cache.set(key, candidates)

    # === メモリキャッシュ（トリガー銘柄）===

    def _make_trigger_key(self, date_str: str, timeframe: str) -> str:
        """トリガーキャッシュのキー生成"""
        return f"trigger:{date_str}:{timeframe}"

    def get_triggers(self, date_str: str, timeframe: str) -> Optional[pd.DataFrame]:
        """トリガー銘柄をキャッシュから取得"""
        key = self._make_trigger_key(date_str, timeframe)
        return self.trigger_cache.get(key)

    def set_triggers(self, date_str: str, timeframe: str, triggers: pd.DataFrame):
        """トリガー銘柄をキャッシュに保存"""
        key = self._make_trigger_key(date_str, timeframe)
        self.trigger_cache.set(key, triggers)

    # === キャッシュ無効化 ===

    def invalidate_all(self):
        """全キャッシュを無効化"""
        self.candidate_cache.clear()
        self.trigger_cache.clear()
        self._correlation_cache = None
        self._backtest_cache = None
        logger.info("全キャッシュをクリアしました")

    def invalidate_on_settings_change(self):
        """設定変更時のキャッシュ無効化"""
        # 候補銘柄キャッシュをクリア（スコア計算に影響）
        self.candidate_cache.clear()
        logger.info("設定変更により候補キャッシュをクリアしました")

    def invalidate_correlations(self, timeframe: Optional[str] = None):
        """相関キャッシュを無効化"""
        if timeframe:
            path = self._get_correlation_cache_path(timeframe)
            if path.exists():
                path.unlink()
                logger.info(f"相関キャッシュを削除: {timeframe}")
        else:
            for tf in ['daily', 'weekly', 'monthly']:
                path = self._get_correlation_cache_path(tf)
                if path.exists():
                    path.unlink()
            logger.info("全相関キャッシュを削除しました")

        self.candidate_cache.clear()

    # === キャッシュ情報 ===

    def get_cache_info(self) -> Dict[str, Any]:
        """キャッシュ状態を取得"""
        info = {
            'candidate_cache_size': len(self.candidate_cache._cache),
            'trigger_cache_size': len(self.trigger_cache._cache),
            'correlation_cache_files': {},
            'backtest_cache_files': {}
        }

        for tf in ['daily', 'weekly', 'monthly']:
            corr_path = self._get_correlation_cache_path(tf)
            bt_path = self._get_backtest_cache_path(tf)

            if corr_path.exists():
                info['correlation_cache_files'][tf] = {
                    'exists': True,
                    'size_mb': corr_path.stat().st_size / (1024 * 1024)
                }
            else:
                info['correlation_cache_files'][tf] = {'exists': False}

            if bt_path.exists():
                info['backtest_cache_files'][tf] = {
                    'exists': True,
                    'size_mb': bt_path.stat().st_size / (1024 * 1024)
                }
            else:
                info['backtest_cache_files'][tf] = {'exists': False}

        return info


# シングルトンインスタンス
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """キャッシュマネージャーのシングルトンを取得"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager

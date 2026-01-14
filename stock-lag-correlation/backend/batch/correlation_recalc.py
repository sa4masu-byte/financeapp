"""
相関再計算バッチ処理（月次）

実行タイミング: 毎月1日
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# パス設定
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db_session
from data import ReturnCalculator, CacheManager
from data.cache import get_cache_manager
from analysis import CorrelationEngine, BacktestEngine
from models import Setting

logger = logging.getLogger(__name__)


def get_setting_value(session, key: str, default: str) -> str:
    """設定値を取得"""
    setting = session.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else default


def monthly_recalculation_job():
    """
    月次相関再計算ジョブ

    1. 全タイムフレームのリターンデータを読み込み
    2. 相関分析を再実行
    3. バックテストを再実行
    4. キャッシュを更新
    """
    logger.info("=" * 50)
    logger.info("月次相関再計算バッチ開始")
    logger.info("=" * 50)

    start_time = datetime.now()

    with get_db_session() as session:
        try:
            # 設定値を取得
            min_correlation = float(get_setting_value(session, 'min_correlation', '0.30'))
            significance_level = float(get_setting_value(session, 'significance_level', '0.05'))
            max_lag_daily = int(get_setting_value(session, 'max_lag_daily', '10'))
            max_lag_weekly = int(get_setting_value(session, 'max_lag_weekly', '6'))
            max_lag_monthly = int(get_setting_value(session, 'max_lag_monthly', '3'))

            # キャッシュマネージャー
            cache_manager = get_cache_manager()

            # リターン計算機
            calculator = ReturnCalculator(session)

            # 相関エンジン
            correlation_engine = CorrelationEngine(
                min_correlation=min_correlation,
                alpha=significance_level,
                db_session=session
            )

            # バックテストエンジン
            backtest_engine = BacktestEngine(session)

            # タイムフレームごとに処理
            timeframe_configs = [
                ('daily', max_lag_daily),
                ('weekly', max_lag_weekly),
                ('monthly', max_lag_monthly),
            ]

            for timeframe, max_lag in timeframe_configs:
                logger.info(f"\n{'='*30}")
                logger.info(f"{timeframe.upper()} 相関分析")
                logger.info(f"{'='*30}")

                # 1. リターンデータ読み込み
                logger.info("Step 1: リターンデータ読み込み...")
                returns_df = calculator.load_returns_from_db(timeframe)

                if returns_df.empty:
                    logger.warning(f"{timeframe}: リターンデータがありません")
                    continue

                logger.info(f"  期間: {returns_df.index.min()} ~ {returns_df.index.max()}")
                logger.info(f"  銘柄数: {len(returns_df.columns)}")
                logger.info(f"  データ数: {len(returns_df)}")

                # 2. 相関分析
                logger.info("Step 2: 相関分析実行...")
                correlations_df = correlation_engine.analyze_all_pairs(
                    returns_df=returns_df,
                    timeframe=timeframe,
                    max_lag=max_lag
                )

                if correlations_df.empty:
                    logger.warning(f"{timeframe}: 有意な相関が見つかりませんでした")
                    continue

                logger.info(f"  有意な相関ペア: {len(correlations_df)}件")

                # DBに保存
                logger.info("  DBに保存中...")
                correlation_engine.save_to_db(correlations_df)

                # キャッシュに保存
                cache_manager.save_correlations(correlations_df, timeframe)

                # 3. バックテスト
                logger.info("Step 3: バックテスト実行...")
                backtest_df = backtest_engine.backtest_all_correlations(
                    correlations_df=correlations_df,
                    returns_df=returns_df
                )

                if not backtest_df.empty:
                    logger.info(f"  バックテスト結果: {len(backtest_df)}件")

                    # DBに保存
                    backtest_engine.save_to_db(backtest_df)

                    # キャッシュに保存
                    cache_manager.save_backtest_results(backtest_df, timeframe)
                else:
                    logger.warning(f"{timeframe}: バックテスト結果がありません")

            # キャッシュをクリア（候補銘柄キャッシュ）
            logger.info("\nキャッシュをクリア中...")
            cache_manager.candidate_cache.clear()

            # 完了
            elapsed = datetime.now() - start_time
            logger.info("=" * 50)
            logger.info(f"月次相関再計算バッチ完了 (所要時間: {elapsed})")
            logger.info("=" * 50)

        except Exception as e:
            logger.error(f"バッチ処理エラー: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    # ログ設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    monthly_recalculation_job()

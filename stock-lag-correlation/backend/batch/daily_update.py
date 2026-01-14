"""
日次更新バッチ処理

実行タイミング: 日本時間16:00（市場引け後）、月〜金
"""
import logging
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

# パス設定
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db_session
from data import DataFetcher, ReturnCalculator
from analysis import TriggerDetector
from models import Setting

logger = logging.getLogger(__name__)


def get_last_business_day() -> date:
    """
    前営業日を取得（土日祝を考慮）
    """
    today = datetime.now().date()

    # 今日が土曜なら金曜、日曜なら金曜
    if today.weekday() == 5:  # 土曜
        return today - timedelta(days=1)
    elif today.weekday() == 6:  # 日曜
        return today - timedelta(days=2)
    elif today.weekday() == 0:  # 月曜
        return today - timedelta(days=3)
    else:
        return today - timedelta(days=1)


def get_setting_value(session, key: str, default: str) -> str:
    """設定値を取得"""
    setting = session.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else default


def daily_batch_job():
    """
    日次バッチジョブ

    1. 前営業日の株価データ取得
    2. リターン計算（TOPIX控除）
    3. トリガー銘柄検出
    4. DBへ保存
    """
    logger.info("=" * 50)
    logger.info("日次バッチ開始")
    logger.info("=" * 50)

    start_time = datetime.now()

    with get_db_session() as session:
        try:
            # 設定値を取得
            return_threshold = float(get_setting_value(session, 'return_threshold', '0.02'))
            volume_threshold = float(get_setting_value(session, 'volume_threshold', '1.5'))

            # 1. データ取得
            logger.info("Step 1: データ取得")
            fetcher = DataFetcher(session)
            tickers = fetcher.get_tickers_from_db()

            if not tickers:
                logger.warning("銘柄データがありません。初期セットアップを実行してください。")
                return

            logger.info(f"対象銘柄数: {len(tickers)}")

            # 前営業日の日付
            last_business_day = get_last_business_day()
            logger.info(f"対象日: {last_business_day}")

            # 各銘柄の最新データを取得（5日分を取得してフィルタ）
            success_count = 0
            fail_count = 0

            for ticker in tickers:
                try:
                    data = fetcher.download_ticker_data(ticker, period="5d")
                    if data is not None and not data.empty:
                        fetcher.save_prices_to_db(ticker, data)
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    logger.error(f"{ticker} の取得失敗: {e}")
                    fail_count += 1

            logger.info(f"データ取得完了: 成功={success_count}, 失敗={fail_count}")

            # TOPIX取得
            topix_data = fetcher.download_topix(period="5d")

            if topix_data is None:
                logger.error("TOPIXデータの取得に失敗しました")
                return

            # 2. リターン計算
            logger.info("Step 2: リターン計算")
            calculator = ReturnCalculator(session)

            # 最新のリターンを計算するために必要なデータを取得
            # （既存データと新規データを結合）
            returns_df = calculator.load_returns_from_db('daily')

            # 3. トリガー検出
            logger.info("Step 3: トリガー検出")
            detector = TriggerDetector(session)

            # 出来高データ取得
            volume_data = calculator.get_volume_data(tickers)

            # 各タイムフレームでトリガー検出
            for timeframe in ['daily', 'weekly', 'monthly']:
                logger.info(f"  {timeframe} トリガー検出...")

                # 最新リターンを取得
                latest_returns_df = calculator.get_latest_returns(timeframe, n_days=1)

                if latest_returns_df.empty:
                    logger.warning(f"  {timeframe}: リターンデータがありません")
                    continue

                # Series形式に変換
                latest_date = latest_returns_df['date'].max()
                latest_returns = latest_returns_df[
                    latest_returns_df['date'] == latest_date
                ].set_index('ticker_code')['adjusted_return']

                # トリガー検出
                triggers = detector.detect_triggers(
                    latest_returns=latest_returns,
                    volume_data=volume_data,
                    return_threshold=return_threshold,
                    volume_threshold=volume_threshold
                )

                if not triggers.empty:
                    detector.save_triggers_to_db(triggers, latest_date, timeframe)
                    logger.info(f"  {timeframe}: {len(triggers)}件のトリガーを検出")
                else:
                    logger.info(f"  {timeframe}: トリガーなし")

            # 完了
            elapsed = datetime.now() - start_time
            logger.info("=" * 50)
            logger.info(f"日次バッチ完了 (所要時間: {elapsed})")
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

    daily_batch_job()

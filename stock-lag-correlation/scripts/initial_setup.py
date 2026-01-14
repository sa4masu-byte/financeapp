"""
初回セットアップスクリプト

全データをダウンロード・分析する
実行時間: 数時間（300銘柄 × 10年分）
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# パス設定
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from database import get_db_session, init_db
from data import DataFetcher, ReturnCalculator, CacheManager
from data.cache import get_cache_manager
from analysis import CorrelationEngine, BacktestEngine
from models import Setting
from config import get_settings

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
settings = get_settings()


def insert_default_settings(session):
    """デフォルト設定を挿入"""
    default_settings = [
        ('return_threshold', '0.02'),
        ('volume_threshold', '1.5'),
        ('min_correlation', '0.30'),
        ('significance_level', '0.05'),
        ('max_lag_daily', '10'),
        ('max_lag_weekly', '6'),
        ('max_lag_monthly', '3'),
    ]

    for key, value in default_settings:
        existing = session.query(Setting).filter(Setting.key == key).first()
        if not existing:
            session.add(Setting(key=key, value=value))

    session.commit()
    logger.info("デフォルト設定を挿入しました")


def initial_setup():
    """
    初回セットアップ

    1. データベース初期化
    2. 東証プライム300銘柄リスト取得
    3. 全銘柄の10年分データダウンロード
    4. TOPIX取得
    5. 日足/週足/月足リターン計算
    6. 全ペア相関分析
    7. バックテスト実行
    8. DB・キャッシュ保存
    """
    print("=" * 60)
    print("日本株タイムラグ相関分析システム - 初回セットアップ")
    print("=" * 60)

    start_time = datetime.now()

    # 1. データベース初期化
    print("\n[Step 1] データベース初期化...")
    init_db()
    print("  完了")

    with get_db_session() as session:
        # デフォルト設定を挿入
        insert_default_settings(session)

        # 2. 銘柄リスト取得
        print("\n[Step 2] 東証プライム銘柄リスト取得...")
        fetcher = DataFetcher(session)
        tickers_info = fetcher.get_prime_300_tickers()
        ticker_codes = [t['ticker_code'] for t in tickers_info]

        print(f"  対象銘柄数: {len(ticker_codes)}")

        # 銘柄マスタをDBに保存
        fetcher.save_tickers_to_db(tickers_info)

        # 3. 株価データダウンロード
        print("\n[Step 3] 株価データダウンロード (10年分)...")
        print("  ※ 数時間かかる場合があります")

        all_data = fetcher.download_all_tickers(ticker_codes, years=10)

        # DBに保存
        print("\n  株価データをDBに保存中...")
        for ticker, df in all_data.items():
            fetcher.save_prices_to_db(ticker, df)
        print(f"  {len(all_data)}銘柄のデータを保存しました")

        # 4. TOPIX取得
        print("\n[Step 4] TOPIXデータ取得...")
        topix_prices = fetcher.download_topix(years=10)

        if topix_prices is None:
            print("  エラー: TOPIXデータの取得に失敗しました")
            return

        print(f"  期間: {topix_prices.index[0]} ~ {topix_prices.index[-1]}")

        # 5. リターン計算
        print("\n[Step 5] リターン計算...")
        calculator = ReturnCalculator(session)

        # 全タイムフレームのリターンを計算
        all_returns = calculator.calculate_all_returns(all_data, topix_prices)
        raw_returns = calculator.calculate_raw_returns(all_data)

        for timeframe in ['daily', 'weekly', 'monthly']:
            print(f"  {timeframe} リターンをDBに保存中...")
            calculator.save_returns_to_db(
                all_returns[timeframe],
                raw_returns[timeframe],
                timeframe
            )

        # キャッシュマネージャー
        cache_manager = get_cache_manager()

        # 6. 相関分析
        print("\n[Step 6] 相関分析 (※ 数時間かかる場合があります)...")

        correlation_engine = CorrelationEngine(
            min_correlation=0.30,
            alpha=0.05,
            db_session=session
        )

        timeframe_configs = [
            ('daily', 10),
            ('weekly', 6),
            ('monthly', 3),
        ]

        correlations_dict = {}

        for timeframe, max_lag in timeframe_configs:
            print(f"\n  {timeframe} 相関分析...")
            correlations_df = correlation_engine.analyze_all_pairs(
                all_returns[timeframe],
                timeframe,
                max_lag
            )

            if not correlations_df.empty:
                correlation_engine.save_to_db(correlations_df)
                cache_manager.save_correlations(correlations_df, timeframe)
                correlations_dict[timeframe] = correlations_df
                print(f"    有意な相関ペア: {len(correlations_df)}件")
            else:
                print(f"    有意な相関が見つかりませんでした")

        # 7. バックテスト
        print("\n[Step 7] バックテスト実行...")

        backtest_engine = BacktestEngine(session)

        for timeframe, max_lag in timeframe_configs:
            if timeframe not in correlations_dict:
                continue

            print(f"\n  {timeframe} バックテスト...")
            backtest_df = backtest_engine.backtest_all_correlations(
                correlations_dict[timeframe],
                all_returns[timeframe]
            )

            if not backtest_df.empty:
                backtest_engine.save_to_db(backtest_df)
                cache_manager.save_backtest_results(backtest_df, timeframe)
                print(f"    バックテスト結果: {len(backtest_df)}件")

    # 完了
    elapsed = datetime.now() - start_time
    print("\n" + "=" * 60)
    print("初回セットアップ完了!")
    print(f"所要時間: {elapsed}")
    print("=" * 60)
    print("\n次のステップ:")
    print("  1. uvicorn backend.main:app --reload でAPIサーバーを起動")
    print("  2. cd frontend && npm run dev でフロントエンドを起動")
    print("  3. http://localhost:5173 でアクセス")


if __name__ == "__main__":
    initial_setup()

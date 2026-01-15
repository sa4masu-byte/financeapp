"""
相関分析のみ実行するスクリプト
（既存のDBデータを使用）
"""
import logging
import sys
from pathlib import Path

# パス設定
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from database import get_db_session, init_db
from data import ReturnCalculator
from data.cache import get_cache_manager
from analysis import CorrelationEngine, BacktestEngine
from models import DailyPrice, Ticker
import pandas as pd

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_correlation_analysis():
    """相関分析のみ実行"""
    print("=" * 60)
    print("相関分析のみ実行")
    print("=" * 60)

    with get_db_session() as session:
        # 1. DBから株価データを取得
        print("\n[Step 1] DBから株価データを読み込み中...")

        tickers = session.query(Ticker.ticker_code).all()
        ticker_codes = [t[0] for t in tickers]
        print(f"  銘柄数: {len(ticker_codes)}")

        # 各銘柄の価格データを取得
        all_data = {}
        for ticker_code in ticker_codes:
            prices = session.query(DailyPrice).filter(
                DailyPrice.ticker_code == ticker_code
            ).order_by(DailyPrice.date).all()

            if prices:
                df = pd.DataFrame([
                    {'date': p.date, 'adj_close': p.adj_close, 'volume': p.volume}
                    for p in prices
                ])
                df.set_index('date', inplace=True)
                all_data[ticker_code] = df

        print(f"  読み込んだ銘柄数: {len(all_data)}")

        # 2. TOPIXデータを取得（1306 ETFを代用）
        print("\n[Step 2] TOPIX代替データを読み込み中...")
        topix_prices = session.query(DailyPrice).filter(
            DailyPrice.ticker_code == '1306'
        ).order_by(DailyPrice.date).all()

        if not topix_prices:
            # TOPIXがなければ最初の銘柄で代用（簡易的）
            first_ticker = list(all_data.keys())[0]
            topix_series = all_data[first_ticker]['adj_close']
            print(f"  TOPIX代替: {first_ticker}のデータを使用")
        else:
            topix_series = pd.Series(
                {p.date: p.adj_close for p in topix_prices}
            )
            print(f"  TOPIX代替データ: {len(topix_series)}日分")

        # 3. リターン計算
        print("\n[Step 3] リターン計算中...")
        calculator = ReturnCalculator(session)
        all_returns = calculator.calculate_all_returns(all_data, topix_series)

        for tf, df in all_returns.items():
            print(f"  {tf}: {len(df)}日 x {len(df.columns)}銘柄")

        # キャッシュマネージャー
        cache_manager = get_cache_manager()

        # 4. 相関分析
        print("\n[Step 4] 相関分析...")

        correlation_engine = CorrelationEngine(
            min_correlation=0.25,
            alpha=0.01,
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
                max_lag,
                use_bonferroni=False
            )

            if not correlations_df.empty:
                correlation_engine.save_to_db(correlations_df)
                cache_manager.save_correlations(correlations_df, timeframe)
                correlations_dict[timeframe] = correlations_df
                print(f"    有意な相関ペア: {len(correlations_df)}件")
            else:
                print(f"    有意な相関が見つかりませんでした")

        # 5. バックテスト
        print("\n[Step 5] バックテスト実行...")

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

    print("\n" + "=" * 60)
    print("相関分析完了!")
    print("=" * 60)


if __name__ == "__main__":
    run_correlation_analysis()

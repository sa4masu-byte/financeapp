"""
ヒット率重視の相関分析を実行
- 大きく動いた日（2%以上）のみに着目
- 実際の勝率55%以上のペアを抽出
"""
import logging
import sys
from pathlib import Path

# パス設定
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from database import get_db_session
from data import ReturnCalculator
from analysis.hitrate_engine import HitRateEngine
from models import DailyPrice, Ticker
import pandas as pd

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_hitrate_analysis():
    """ヒット率分析を実行"""
    print("=" * 60)
    print("ヒット率重視の相関分析")
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
                    {'adj_close': float(p.adj_close), 'volume': p.volume or 0}
                    for p in prices
                ], index=[p.date for p in prices])
                all_data[ticker_code] = df

        print(f"  読み込んだ銘柄数: {len(all_data)}")

        # 2. TOPIXデータを取得
        print("\n[Step 2] TOPIX代替データを読み込み中...")
        topix_prices = session.query(DailyPrice).filter(
            DailyPrice.ticker_code == '1306'
        ).order_by(DailyPrice.date).all()

        if not topix_prices:
            first_ticker = list(all_data.keys())[0]
            topix_series = pd.Series(all_data[first_ticker]['adj_close'])
            print(f"  TOPIX代替: {first_ticker}のデータを使用")
        else:
            topix_series = pd.Series(
                {p.date: float(p.adj_close) for p in topix_prices}
            )
            print(f"  TOPIX代替データ: {len(topix_series)}日分")

        # 3. リターン計算
        print("\n[Step 3] リターン計算中...")
        calculator = ReturnCalculator(session)
        all_returns = calculator.calculate_all_returns(all_data, topix_series)

        for tf, df in all_returns.items():
            print(f"  {tf}: {len(df)}日 x {len(df.columns)}銘柄")

        # 4. ヒット率分析
        print("\n[Step 4] ヒット率分析...")

        # 分析パラメータ
        engine = HitRateEngine(
            move_threshold=0.02,   # 2%以上の動き
            min_hit_rate=0.55,     # 55%以上のヒット率
            min_samples=30,         # 最低30サンプル
            db_session=session
        )

        all_results = {}

        # 日足のみまず実行（時間短縮のため）
        timeframe_configs = [
            ('daily', 5),  # 日足は5日まで
            # ('weekly', 4),
            # ('monthly', 2),
        ]

        for timeframe, max_lag in timeframe_configs:
            print(f"\n  {timeframe} ヒット率分析...")
            results_df = engine.analyze_all_pairs(
                all_returns[timeframe],
                timeframe,
                max_lag
            )

            if not results_df.empty:
                all_results[timeframe] = results_df
                engine.print_summary(results_df)

                # CSVに保存
                output_path = Path(__file__).parent.parent / f'hitrate_results_{timeframe}.csv'
                results_df.to_csv(output_path, index=False, encoding='utf-8-sig')
                print(f"\n  結果を保存: {output_path}")

    print("\n" + "=" * 60)
    print("分析完了!")
    print("=" * 60)

    return all_results


if __name__ == "__main__":
    run_hitrate_analysis()

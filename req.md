日本株タイムラグ相関分析システム 要求仕様書
1. プロジェクト概要
1.1 目的
日本株の個別銘柄間におけるタイムラグ相関を分析し、「銘柄Aが動いた後、X日後に銘柄Bが動く」というパターンを統計的に抽出。日々の値動きから将来注目すべき銘柄を提示するWebアプリケーション。
1.2 主要機能

東証プライム時価総額上位300銘柄の株価データ取得（10年分）
TOPIX控除後のリターン系列によるタイムラグ相関分析
日足/週足/月足の切替対応
統計的有意性（相関係数、p-value）の評価
バックテストによるヒット率計算
「今日動いた銘柄」の自動検出と候補銘柄の提示
Web UIによる可視化


2. 技術スタック
2.1 バックエンド

言語: Python 3.10+
Webフレームワーク: FastAPI
データ分析: pandas, numpy, scipy, statsmodels
最適化: numba (JITコンパイル)
データ取得: yfinance
DB: PostgreSQL

2.2 フロントエンド

フレームワーク: React 18+ with TypeScript
スタイリング: TailwindCSS
グラフ: Plotly.js
HTTPクライアント: Axios

2.3 インフラ

ホスティング: Render
バッチ処理: Render Cron Jobs
DB: Render PostgreSQL


3. プロジェクト構造
stock-lag-correlation/
├── backend/
│   ├── main.py                      # FastAPI エントリポイント
│   ├── config.py                    # 設定管理
│   ├── database.py                  # DB接続
│   ├── models.py                    # SQLAlchemy models
│   ├── schemas.py                   # Pydantic schemas
│   ├── requirements.txt
│   │
│   ├── data/
│   │   ├── fetcher.py              # yfinance データ取得
│   │   ├── return_calculator.py   # リターン計算・TOPIX控除
│   │   └── cache.py                # データキャッシュ管理
│   │
│   ├── analysis/
│   │   ├── correlation_engine.py  # タイムラグ相関計算
│   │   ├── backtest.py            # ヒット率計算
│   │   └── trigger_detector.py    # トリガー銘柄検出
│   │
│   ├── api/
│   │   └── routes.py               # APIエンドポイント
│   │
│   └── batch/
│       ├── daily_update.py         # 日次更新バッチ
│       └── correlation_recalc.py   # 相関再計算バッチ
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── CandidateList.tsx
│   │   │   ├── CorrelationChart.tsx
│   │   │   └── SettingsPanel.tsx
│   │   ├── api/
│   │   │   └── client.ts
│   │   ├── types/
│   │   │   └── index.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── tsconfig.json
│
├── scripts/
│   ├── initial_setup.py            # 初回データ取得
│   └── migration.sql               # DB初期化SQL
│
└── README.md

4. データベーススキーマ
4.1 テーブル定義
sql-- 銘柄マスタ
CREATE TABLE tickers (
    ticker_code VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255),
    sector VARCHAR(100),
    market_cap BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 日次株価データ
CREATE TABLE daily_prices (
    id SERIAL PRIMARY KEY,
    ticker_code VARCHAR(10) REFERENCES tickers(ticker_code),
    date DATE NOT NULL,
    adj_close DECIMAL(12, 2),
    volume BIGINT,
    UNIQUE(ticker_code, date)
);

-- リターンデータ（TOPIX控除済み）
CREATE TABLE returns (
    id SERIAL PRIMARY KEY,
    ticker_code VARCHAR(10) REFERENCES tickers(ticker_code),
    date DATE NOT NULL,
    timeframe VARCHAR(10) CHECK (timeframe IN ('daily', 'weekly', 'monthly')),
    return_value DECIMAL(10, 6),
    topix_adjusted_return DECIMAL(10, 6),
    UNIQUE(ticker_code, date, timeframe)
);

-- 相関分析結果
CREATE TABLE correlations (
    id SERIAL PRIMARY KEY,
    ticker_a VARCHAR(10) REFERENCES tickers(ticker_code),
    ticker_b VARCHAR(10) REFERENCES tickers(ticker_code),
    timeframe VARCHAR(10),
    lag INTEGER,
    correlation DECIMAL(6, 4),
    p_value DECIMAL(10, 8),
    direction VARCHAR(10) CHECK (direction IN ('positive', 'negative')),
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker_a, ticker_b, timeframe, lag)
);

-- バックテスト結果
CREATE TABLE backtest_results (
    id SERIAL PRIMARY KEY,
    ticker_a VARCHAR(10) REFERENCES tickers(ticker_code),
    ticker_b VARCHAR(10) REFERENCES tickers(ticker_code),
    timeframe VARCHAR(10),
    lag INTEGER,
    hit_rate DECIMAL(5, 4),
    total_signals INTEGER,
    successful_signals INTEGER,
    test_period_start DATE,
    test_period_end DATE,
    UNIQUE(ticker_a, ticker_b, timeframe, lag)
);

-- トリガー銘柄（日次更新）
CREATE TABLE daily_triggers (
    id SERIAL PRIMARY KEY,
    ticker_code VARCHAR(10) REFERENCES tickers(ticker_code),
    date DATE NOT NULL,
    timeframe VARCHAR(10),
    return_value DECIMAL(10, 6),
    volume_ratio DECIMAL(6, 2),
    UNIQUE(ticker_code, date, timeframe)
);

-- 設定管理
CREATE TABLE settings (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
4.2 初期設定データ
sqlINSERT INTO settings (key, value) VALUES
    ('return_threshold', '0.02'),
    ('volume_threshold', '1.5'),
    ('min_correlation', '0.30'),
    ('significance_level', '0.05'),
    ('max_lag_daily', '10'),
    ('max_lag_weekly', '6'),
    ('max_lag_monthly', '3');

5. バックエンド詳細仕様
5.1 データ取得モジュール (data/fetcher.py)
python"""
必須機能:
1. 東証プライム時価総額上位300銘柄リスト取得
2. yfinanceで10年分の日次株価データダウンロード
3. レート制限対策（exponential backoff, sleep）
4. エラーハンドリングと再試行
5. 進捗表示（tqdm）
"""

class DataFetcher:
    def __init__(self, db_session):
        self.session = db_session
        self.retry_delays = [0.5, 1, 2, 4, 8]  # exponential backoff
    
    def get_prime_300_tickers(self) -> List[str]:
        """
        東証プライム時価総額上位300銘柄を取得
        
        実装方法:
        - Option 1: JPXのWebサイトからスクレイピング
        - Option 2: 手動CSV（./data/prime_300.csv）から読込
        
        Return: ["7203", "9984", "6758", ...]
        """
        pass
    
    def download_ticker_data(self, ticker: str, period: str = "10y") -> pd.DataFrame:
        """
        単一銘柄のデータ取得（リトライ機能付き）
        
        Args:
            ticker: 銘柄コード（例: "7203"）
            period: 取得期間（デフォルト: "10y"）
        
        Return:
            DataFrame with columns: [Date, Adj Close, Volume]
        
        エラー処理:
        - 404/500エラー: exponential backoffで最大5回リトライ
        - 各リクエスト間に0.5秒sleep
        - 失敗した場合はログ記録してNone返却
        """
        pass
    
    def download_all_tickers(self, tickers: List[str]) -> Dict[str, pd.DataFrame]:
        """
        全銘柄一括ダウンロード
        
        - tqdmで進捗バー表示
        - 各銘柄間に0.5秒sleep
        - 失敗銘柄はスキップして続行
        - 最後に成功/失敗サマリー表示
        """
        pass
    
    def download_topix(self, period: str = "10y") -> pd.Series:
        """
        TOPIXデータ取得（ticker: "^TOPIX"）
        """
        pass
    
    def save_to_db(self, ticker: str, df: pd.DataFrame):
        """
        daily_prices テーブルへ保存
        """
        pass

5.2 リターン計算モジュール (data/return_calculator.py)
python"""
必須機能:
1. 対数リターン計算
2. TOPIX控除（市場要因除去）
3. 日足→週足・月足への変換
"""

class ReturnCalculator:
    @staticmethod
    def calculate_log_returns(prices: pd.Series) -> pd.Series:
        """
        対数リターン: ln(P_t / P_{t-1})
        
        Args:
            prices: 調整後終値の時系列
        
        Return:
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
        
        Return:
            TOPIX控除済みリターン（超過リターン）
        
        重要: 日付インデックスを揃えてから計算
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
        
        Return:
            週次リターン（各週の累積リターン）
        """
        return daily_returns.resample('W-FRI').sum()
    
    @staticmethod
    def resample_to_monthly(daily_returns: pd.DataFrame) -> pd.DataFrame:
        """
        月足リターン: 月末基準でリサンプリング
        """
        return daily_returns.resample('M').sum()
    
    def save_returns_to_db(
        self, 
        returns: pd.DataFrame, 
        timeframe: str,
        db_session
    ):
        """
        returns テーブルへ保存
        """
        pass

5.3 相関分析エンジン (analysis/correlation_engine.py)
python"""
必須機能:
1. タイムラグ相関計算（Numba最適化）
2. 統計的有意性検定（p-value）
3. 多重検定補正（Bonferroni）
4. 循環相関検出
"""

from numba import jit
from scipy import stats

class CorrelationEngine:
    def __init__(self, min_correlation: float = 0.3, alpha: float = 0.05):
        self.min_correlation = min_correlation
        self.alpha = alpha
    
    def analyze_all_pairs(
        self,
        returns_df: pd.DataFrame,
        timeframe: str,
        max_lag: int
    ) -> pd.DataFrame:
        """
        全ペア組み合わせでタイムラグ相関を計算
        
        Args:
            returns_df: TOPIX控除済みリターン (columns: ticker_code)
            timeframe: "daily" | "weekly" | "monthly"
            max_lag: 最大ラグ日数/週数/月数
        
        Return:
            DataFrame with columns: [ticker_a, ticker_b, lag, correlation, p_value, direction]
        
        実装詳細:
        - 300銘柄 × 299 × max_lag = 約90万回の計算
        - Numba JITで高速化（後述の関数使用）
        - 相関係数 >= min_correlation かつ p_value < alpha のみ保存
        - A→B のみ計算（B→A は別途）
        """
        tickers = returns_df.columns.tolist()
        results = []
        
        # Bonferroni補正
        n_tests = len(tickers) * (len(tickers) - 1) * max_lag
        alpha_corrected = self.alpha / n_tests
        
        for i, ticker_a in enumerate(tickers):
            for ticker_b in tickers:
                if ticker_a == ticker_b:
                    continue
                
                # データ抽出
                series_a = returns_df[ticker_a].dropna()
                series_b = returns_df[ticker_b].dropna()
                
                # 共通期間
                common_idx = series_a.index.intersection(series_b.index)
                a_values = series_a.loc[common_idx].values
                b_values = series_b.loc[common_idx].values
                
                # ラグ相関計算
                for lag in range(1, max_lag + 1):
                    if len(a_values) <= lag:
                        continue
                    
                    corr, p_val = self._calculate_lagged_correlation(
                        a_values, b_values, lag
                    )
                    
                    if abs(corr) >= self.min_correlation and p_val < alpha_corrected:
                        results.append({
                            'ticker_a': ticker_a,
                            'ticker_b': ticker_b,
                            'timeframe': timeframe,
                            'lag': lag,
                            'correlation': corr,
                            'p_value': p_val,
                            'direction': 'positive' if corr > 0 else 'negative'
                        })
        
        return pd.DataFrame(results)
    
    @staticmethod
    @jit(nopython=True)
    def _calculate_lagged_correlation(
        a: np.ndarray, 
        b: np.ndarray, 
        lag: int
    ) -> Tuple[float, float]:
        """
        Numba最適化版ラグ相関計算
        
        相関: corr(A[0:T-lag], B[lag:T])
        
        Return: (correlation, p_value)
        
        注意: numbaではscipy.statsが使えないため、
        p-valueは通常のPython関数で計算する別実装も必要
        """
        # A[:-lag] vs B[lag:] の相関
        a_lagged = a[:-lag]
        b_shifted = b[lag:]
        
        # 相関係数計算
        corr = np.corrcoef(a_lagged, b_shifted)[0, 1]
        return corr
    
    def calculate_p_value(
        self, 
        a: np.ndarray, 
        b: np.ndarray, 
        lag: int
    ) -> float:
        """
        p-value計算（scipy使用）
        """
        corr, p_val = stats.pearsonr(a[:-lag], b[lag:])
        return p_val
    
    def detect_circular_correlations(
        self, 
        correlations_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        循環相関検出: A→B と B→A が両方強い場合
        
        Return:
            DataFrame with columns: [ticker_a, ticker_b, lag_ab, lag_ba, corr_ab, corr_ba]
        """
        pass
    
    def save_to_db(self, correlations_df: pd.DataFrame, db_session):
        """
        correlations テーブルへ保存
        """
        pass

5.4 バックテストモジュール (analysis/backtest.py)
python"""
必須機能:
1. ヒット率計算
2. トリガー閾値の適用
3. レスポンス閾値の適用
4. 統計サマリー生成
"""

class BacktestEngine:
    def calculate_hit_rate(
        self,
        returns_df: pd.DataFrame,
        ticker_a: str,
        ticker_b: str,
        lag: int,
        trigger_threshold: float = 0.02,
        response_threshold: float = 0.02
    ) -> Dict[str, float]:
        """
        ヒット率計算
        
        定義:
        1. ticker_Aが±trigger_threshold以上動いた日を「トリガー」
        2. lag日後にticker_Bが同方向に±response_threshold以上動いたら「ヒット」
        3. ヒット率 = ヒット数 / トリガー数
        
        Args:
            returns_df: リターンデータ
            ticker_a: トリガー銘柄
            ticker_b: レスポンス銘柄
            lag: タイムラグ
            trigger_threshold: トリガー閾値（例: 0.02 = 2%）
            response_threshold: レスポンス閾値
        
        Return:
            {
                'hit_rate': 0.65,
                'total_signals': 120,
                'successful_signals': 78,
                'test_period_start': '2020-01-01',
                'test_period_end': '2025-12-31'
            }
        """
        a_returns = returns_df[ticker_a]
        b_returns = returns_df[ticker_b]
        
        # トリガー検出
        trigger_mask = a_returns.abs() >= trigger_threshold
        trigger_dates = a_returns[trigger_mask].index
        
        hits = 0
        total = 0
        
        for date in trigger_dates:
            # lag日後の日付
            future_dates = returns_df.index[returns_df.index > date]
            if len(future_dates) < lag:
                continue
            
            future_date = future_dates[lag - 1]
            
            if future_date not in b_returns.index:
                continue
            
            a_direction = np.sign(a_returns[date])
            b_response = b_returns[future_date]
            
            total += 1
            
            # 同方向かつ閾値超え
            if (np.sign(b_response) == a_direction and 
                abs(b_response) >= response_threshold):
                hits += 1
        
        hit_rate = hits / total if total > 0 else 0.0
        
        return {
            'hit_rate': hit_rate,
            'total_signals': total,
            'successful_signals': hits,
            'test_period_start': str(returns_df.index.min().date()),
            'test_period_end': str(returns_df.index.max().date())
        }
    
    def backtest_all_correlations(
        self,
        correlations_df: pd.DataFrame,
        returns_df: pd.DataFrame,
        db_session
    ):
        """
        全相関ペアに対してバックテスト実行
        
        - correlations_df の各行について calculate_hit_rate を実行
        - 結果を backtest_results テーブルへ保存
        """
        pass

5.5 トリガー検出モジュール (analysis/trigger_detector.py)
python"""
必須機能:
1. 「今日動いた銘柄」の検出
2. 候補銘柄Bのランキング
3. スコア計算
"""

class TriggerDetector:
    def detect_triggers(
        self,
        latest_returns: pd.Series,
        volume_data: pd.DataFrame,
        return_threshold: float = 0.02,
        volume_threshold: float = 1.5
    ) -> pd.DataFrame:
        """
        今日のトリガー銘柄を検出
        
        条件:
        - 条件1: |リターン| >= return_threshold (デフォルト2%)
        - 条件2: 出来高 >= 過去20日平均 × volume_threshold (デフォルト1.5倍)
        
        Args:
            latest_returns: 本日のリターン (Series, index=ticker_code)
            volume_data: 出来高データ (columns: [today_volume, avg_20d_volume])
            return_threshold: リターン閾値
            volume_threshold: 出来高倍率閾値
        
        Return:
            DataFrame with columns: [ticker, return, volume_ratio]
        """
        triggered = []
        
        for ticker in latest_returns.index:
            ret = latest_returns[ticker]
            
            if pd.isna(ret):
                continue
            
            today_vol = volume_data.loc[ticker, 'today_volume']
            avg_vol = volume_data.loc[ticker, 'avg_20d_volume']
            vol_ratio = today_vol / avg_vol
            
            if abs(ret) >= return_threshold and vol_ratio >= volume_threshold:
                triggered.append({
                    'ticker': ticker,
                    'return': ret,
                    'volume_ratio': vol_ratio
                })
        
        return pd.DataFrame(triggered)
    
    def find_candidate_pairs(
        self,
        trigger_ticker: str,
        correlations_df: pd.DataFrame,
        backtest_df: pd.DataFrame,
        top_n: int = 10
    ) -> pd.DataFrame:
        """
        トリガー銘柄に対する候補銘柄Bをランキング
        
        スコア計算:
        score = 0.4 * |correlation| + 0.4 * hit_rate + 0.2 * (1 / p_value_normalized)
        
        Args:
            trigger_ticker: トリガーとなった銘柄コード
            correlations_df: 相関分析結果
            backtest_df: バックテスト結果
            top_n: 上位何件返すか
        
        Return:
            DataFrame with columns: [ticker_b, lag, correlation, p_value, hit_rate, score]
            上位top_n件、scoreの降順
        """
        # ticker_a == trigger_ticker のレコードを抽出
        candidates = correlations_df[
            correlations_df['ticker_a'] == trigger_ticker
        ].copy()
        
        # バックテスト結果をマージ
        candidates = candidates.merge(
            backtest_df[['ticker_a', 'ticker_b', 'lag', 'hit_rate']],
            on=['ticker_a', 'ticker_b', 'lag'],
            how='left'
        )
        
        # p_valueの正規化（0-1スケール）
        max_pval = candidates['p_value'].max()
        candidates['p_value_norm'] = 1 - (candidates['p_value'] / max_pval)
        
        # スコア計算
        candidates['score'] = (
            0.4 * candidates['correlation'].abs() +
            0.4 * candidates['hit_rate'].fillna(0) +
            0.2 * candidates['p_value_norm']
        )
        
        # 上位top_n件を返す
        return candidates.nlargest(top_n, 'score')
    
    def save_triggers_to_db(
        self,
        triggers_df: pd.DataFrame,
        date: str,
        timeframe: str,
        db_session
    ):
        """
        daily_triggers テーブルへ保存
        """
        pass

5.6 FastAPI エンドポイント (api/routes.py)
python"""
APIエンドポイント定義
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List
from schemas import TriggerResponse, CandidateResponse, CorrelationDetail

router = APIRouter()

@router.get("/triggers/today", response_model=List[TriggerResponse])
async def get_today_triggers(
    timeframe: str = Query("daily", enum=["daily", "weekly", "monthly"])
):
    """
    今日のトリガー銘柄リストを取得
    
    Query Parameters:
        timeframe: 日足/週足/月足の選択
    
    Response:
        [
            {
                "ticker": "7203",
                "company_name": "トヨタ自動車",
                "return": 0.025,
                "volume_ratio": 1.8,
                "candidate_count": 8
            },
            ...
        ]
    """
    # DBから最新のトリガーを取得
    # candidate_count は correlations テーブルから集計
    pass

@router.get("/candidates/{ticker}", response_model=List[CandidateResponse])
async def get_candidates(
    ticker: str,
    timeframe: str = Query("daily", enum=["daily", "weekly", "monthly"]),
    top_n: int = Query(10, ge=1, le=50)
):
    """
    指定銘柄の候補銘柄Bリストを取得
    
    Path Parameters:
        ticker: トリガー銘柄コード
    
    Query Parameters:
        timeframe: 日足/週足/月足
        top_n: 上位何件取得するか
    
    Response:
        [
            {
                "ticker_b": "7201",
                "company_name": "日産自動車",
                "lag": 3,
                "correlation": 0.65,
                "p_value": 0.0001,
                "hit_rate": 0.68,
                "direction": "positive",
                "score": 0.85
            },
            ...
        ]
    """
    # TriggerDetector.find_candidate_pairs() を使用
    pass

@router.get("/correlation/{ticker_a}/{ticker_b}", response_model=CorrelationDetail)
async def get_correlation_detail(
    ticker_a: str,
    ticker_b: str,
    timeframe: str = Query("daily"),
    period: int = Query(90, description="過去何日分のデータを返すか")
):
    """
    ペア詳細（時系列グラフ用データ）
    
    Response:
        {
            "ticker_a": "7203",
            "ticker_b": "7201",
            "lag": 3,
            "correlation": 0.65,
            "timeseries": {
                "dates": ["2025-10-01", "2025-10-02", ...],
                "returns_a": [0.01, -0.02, ...],
                "returns_b_shifted": [0.015, -0.018, ...]  # lag分シフト
            },
            "recent_signals": [
                {
                    "date": "2026-01-07",
                    "return_a": 0.021,
                    "return_b": 0.018,
                    "success": true
                },
                ...
            ]
        }
    """
    pass

@router.post("/settings")
async def update_settings(settings: dict):
    """
    閾値・パラメータ更新
    
    Request Body:
        {
            "return_threshold": 0.02,
            "volume_threshold": 1.5,
            "min_correlation": 0.30,
            ...
        }
    """
    # settings テーブルを更新
    pass

@router.post("/batch/run")
async def trigger_batch():
    """
    手動バッチ実行トリガー（開発用）
    """
    # batch/daily_update.py を非同期実行
    pass

5.7 日次バッチスクリプト (batch/daily_update.py)
python"""
日次更新バッチ処理

実行タイミング: 日本時間16:00（市場引け後）、月〜金
"""

def daily_batch_job():
    """
    1. 前営業日の株価データ取得（yfinance）
    2. リターン計算（TOPIX控除）
    3. トリガー銘柄検出
    4. 候補銘柄抽出
    5. PostgreSQLへ保存
    
    エラーハンドリング:
    - データ取得失敗時はログ記録してSlack/メール通知
    - 部分的な失敗でも処理続行
    """
    logger.info("Daily batch started")
    
    # 1. データ取得
    fetcher = DataFetcher(db_session)
    tickers = fetcher.get_prime_300_tickers()
    
    # 前営業日の日付を計算
    last_business_day = get_last_business_day()
    
    # 各銘柄の最新データを取得（1日分のみ）
    for ticker in tickers:
        try:
            data = fetcher.download_ticker_data(ticker, period="5d")  # 余裕を持って5日分
            latest = data[data.index == last_business_day]
            fetcher.save_to_db(ticker, latest)
        except Exception as e:
            logger.error(f"Failed to fetch {ticker}: {e}")
    
    # TOPIX取得
    topix_data = fetcher.download_topix(period="5d")
    
    # 2. リターン計算
    calculator = ReturnCalculator()
    # ... (省略)
    
    # 3. トリガー検出
    detector = TriggerDetector()
    # ... (省略)
    
    # 4. 候補銘柄抽出
    # ... (省略)
    
    logger.info("Daily batch completed")

if __name__ == "__main__":
    daily_batch_job()

6. フロントエンド仕様
6.1 画面構成
画面1: トリガー銘柄ダッシュボード (Dashboard.tsx)
typescriptinterface TriggerItem {
  ticker: string;
  companyName: string;
  return: number;
  volumeRatio: number;
  candidateCount: number;
}

// 表示内容:
// - 日付表示（「今日のトリガー銘柄 (2026-01-14)」）
// - 日足/週足/月足切替タブ
// - トリガー銘柄一覧テーブル
//   - 列: 銘柄コード、銘柄名、変動率、出来高比、候補数
//   - 行クリックで候補銘柄詳細へ遷移
画面2: 候補銘柄詳細 (CandidateList.tsx)
typescriptinterface Candidate {
  tickerB: string;
  companyName: string;
  lag: number;
  correlation: number;
  pValue: number;
  hitRate: number;
  direction: 'positive' | 'negative';
  score: number;
}

// 表示内容:
// - トリガー銘柄情報（「7203 トヨタ自動車 (+2.5%)」）
// - 候補銘柄ランキングテーブル
//   - 列: 順位、銘柄、ラグ、相関、p値、ヒット率、方向
//   - 行クリックで相関グラフ表示
// - 相関グラフ（Plotly）
// - 過去の成功例リスト
画面3: 相関グラフ (CorrelationChart.tsx)
typescript// Plotly.js を使用したインタラクティブグラフ
// - 2軸グラフ: ticker_A のリターン（青）、ticker_B のリターン（赤、lag日シフト）
// - X軸: 日付
// - Y軸: リターン (%)
// - ホバーで詳細表示
画面4: 設定画面 (SettingsPanel.tsx)
typescriptinterface Settings {
  returnThreshold: number;
  volumeThreshold: number;
  minCorrelation: number;
  significanceLevel: number;
  maxLagDaily: number;
  maxLagWeekly: number;
  maxLagMonthly: number;
}

// 表示内容:
// - 各種閾値の入力フォーム
// - 保存ボタン
// - デフォルトに戻すボタン

6.2 API クライアント (api/client.ts)
typescriptimport axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const api = {
  // トリガー銘柄取得
  getTodayTriggers: (timeframe: string) =>
    apiClient.get(`/triggers/today?timeframe=${timeframe}`),
  
  // 候補銘柄取得
  getCandidates: (ticker: string, timeframe: string, topN: number = 10) =>
    apiClient.get(`/candidates/${ticker}?timeframe=${timeframe}&top_n=${topN}`),
  
  // 相関詳細取得
  getCorrelationDetail: (tickerA: string, tickerB: string, timeframe: string) =>
    apiClient.get(`/correlation/${tickerA}/${tickerB}?timeframe=${timeframe}`),
  
  // 設定更新
  updateSettings: (settings: Settings) =>
    apiClient.post('/settings', settings),
};

7. 初回セットアップスクリプト (scripts/initial_setup.py)
python"""
初回実行時に全データをダウンロード・分析

実行時間: 数時間（300銘柄 × 10年分）
"""

def initial_setup():
    """
    1. 東証プライム300銘柄リスト取得
    2. 全銘柄の10年分データダウンロード
    3. TOPIX取得
    4. 日足/週足/月足リターン計算
    5. 全ペア相関分析
    6. バックテスト実行
    7. DB保存
    """
    print("=== 初回セットアップ開始 ===")
    
    # DB接続
    db = get_db_connection()
    
    # 1. 銘柄リスト取得
    fetcher = DataFetcher(db)
    tickers = fetcher.get_prime_300_tickers()
    print(f"対象銘柄数: {len(tickers)}")
    
    # 2. データダウンロード
    print("株価データダウンロード中...")
    all_data = fetcher.download_all_tickers(tickers)
    topix = fetcher.download_topix()
    
    # 3. リターン計算
    print("リターン計算中...")
    calculator = ReturnCalculator()
    # ... (省略)
    
    # 4. 相関分析
    print("相関分析中（数時間かかります）...")
    engine = CorrelationEngine()
    
    for timeframe, max_lag in [('daily', 10), ('weekly', 6), ('monthly', 3)]:
        print(f"  {timeframe} 相関分析...")
        correlations = engine.analyze_all_pairs(returns_dict[timeframe], timeframe, max_lag)
        engine.save_to_db(correlations, db)
    
    # 5. バックテスト
    print("バックテスト実行中...")
    backtest_engine = BacktestEngine()
    # ... (省略)
    
    print("=== セットアップ完了 ===")

if __name__ == "__main__":
    initial_setup()
```

---

## 8. requirements.txt
```
# バックエンド
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
pydantic==2.5.0

# データ分析
pandas==2.1.3
numpy==1.26.2
scipy==1.11.4
statsmodels==0.14.0
yfinance==0.2.32
numba==0.58.1

# ユーティリティ
python-dotenv==1.0.0
tqdm==4.66.1
python-dateutil==2.8.2

# テスト
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2
```

---

## 9. 実装優先順位

### Phase 1: データ基盤（Week 1-2）
1. `data/fetcher.py` - データ取得
2. `data/return_calculator.py` - リターン計算
3. `scripts/initial_setup.py` - 初回セットアップ
4. DB構築

### Phase 2: 分析エンジン（Week 3-4）
5. `analysis/correlation_engine.py` - 相関分析
6. `analysis/backtest.py` - バックテスト
7. `analysis/trigger_detector.py` - トリガー検出

### Phase 3: API（Week 5）
8. `main.py` + `api/routes.py` - FastAPI
9. `batch/daily_update.py` - 日次バッチ

### Phase 4: フロントエンド（Week 6-7）
10. React基本構造
11. 各コンポーネント実装
12. Plotly グラフ統合

### Phase 5: デプロイ（Week 8）
13. Render設定
14. 環境変数設定
15. 動作確認

---

## 10. テスト要件

### 10.1 ユニットテスト
- 各モジュールの主要関数をテスト
- `tests/test_correlation_engine.py`
- `tests/test_backtest.py`
- `tests/test_trigger_detector.py`

### 10.2 統合テスト
- API エンドポイントの動作確認
- `tests/test_api.py`

### 10.3 データ整合性テスト
- DBに保存されたデータの妥当性チェック
- 相関係数が-1〜1の範囲内
- p-valueが0〜1の範囲内

---

## 11. デプロイ設定

### 11.1 Render 環境変数
```
DATABASE_URL=postgresql://...
PYTHONUNBUFFERED=1
TZ=Asia/Tokyo
11.2 render.yaml
yamlservices:
  # Webサービス（FastAPI）
  - type: web
    name: stock-correlation-api
    env: python
    buildCommand: pip install -r backend/requirements.txt
    startCommand: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: stock-correlation-db
          property: connectionString
  
  # 日次バッチ
  - type: cron
    name: daily-batch
    env: python
    schedule: "0 7 * * 1-5"  # 日本時間16:00（UTC 7:00）
    buildCommand: pip install -r backend/requirements.txt
    startCommand: python backend/batch/daily_update.py
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: stock-correlation-db
          property: connectionString

databases:
  - name: stock-correlation-db
    databaseName: stock_correlation
    plan: starter

12. 重要な実装上の注意点
12.1 yfinance レート制限対策

必須: 各リクエスト間に0.5秒sleep
必須: exponential backoff でリトライ
推奨: 初回ダウンロード時はバッチサイズを50銘柄ずつに分割

12.2 Numba 最適化

相関計算の内側ループを @jit(nopython=True) でデコレート
NumPy配列のみ使用（pandasは使えない）
並列化: @jit(nopython=True, parallel=True) + prange

12.3 TOPIX控除の重要性

市場全体の上げ下げを除去することで真の銘柄間相関を抽出
必ず日付を揃えてから計算

12.4 多重検定補正

Bonferroni法: alpha_corrected = alpha / n_tests
n_tests = 銘柄数 × (銘柄数-1) × max_lag

12.5 データベースインデックス
sqlCREATE INDEX idx_correlations_ticker_a ON correlations(ticker_a);
CREATE INDEX idx_correlations_ticker_b ON correlations(ticker_b);
CREATE INDEX idx_returns_date ON returns(date);
CREATE INDEX idx_daily_triggers_date ON daily_triggers(date);

13. 将来の拡張機能（Phase 2）

セクター分析

セクター間相関パターンの可視化
セクターローテーション検出


通知機能

LINE/Slack webhook
高ヒット率ペアのトリガー時に自動通知


CSV エクスポート

分析結果のダウンロード
バックテストレポート生成


ネットワーク図

銘柄間相関をグラフ理論で可視化
影響力の大きい「ハブ銘柄」の特定


リアルタイム更新

WebSocket で最新データをプッシュ




14. 成果物チェックリスト
バックエンド

 data/fetcher.py 実装完了
 data/return_calculator.py 実装完了
 analysis/correlation_engine.py 実装完了
 analysis/backtest.py 実装完了
 analysis/trigger_detector.py 実装完了
 api/routes.py 実装完了
 batch/daily_update.py 実装完了
 scripts/initial_setup.py 実装完了
 PostgreSQL マイグレーション完了

フロントエンド

 Dashboard.tsx 実装完了
 CandidateList.tsx 実装完了
 CorrelationChart.tsx 実装完了
 SettingsPanel.tsx 実装完了
 API client 実装完了

テスト

 ユニットテスト実装
 統合テスト実装
 データ整合性確認

デプロイ

 Render設定完了
 環境変数設定
 日次バッチ動作確認
 本番環境動作確認


15. 質問・不明点の解消プロセス
実装中に不明点があれば、以下の手順で解決：

技術的質問: 該当モジュールのdocstringを確認
仕様確認: この要求仕様書を参照
それでも不明: 私（仕様書作成者）に質問



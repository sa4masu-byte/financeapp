-- 日本株タイムラグ相関分析システム
-- データベースマイグレーションSQL

-- 銘柄マスタ
CREATE TABLE IF NOT EXISTS tickers (
    ticker_code VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255),
    sector VARCHAR(100),
    market_cap BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 日次株価データ
CREATE TABLE IF NOT EXISTS daily_prices (
    id SERIAL PRIMARY KEY,
    ticker_code VARCHAR(10) REFERENCES tickers(ticker_code),
    date DATE NOT NULL,
    adj_close DECIMAL(12, 2),
    volume BIGINT,
    UNIQUE(ticker_code, date)
);

-- リターンデータ（TOPIX控除済み）
CREATE TABLE IF NOT EXISTS returns (
    id SERIAL PRIMARY KEY,
    ticker_code VARCHAR(10) REFERENCES tickers(ticker_code),
    date DATE NOT NULL,
    timeframe VARCHAR(10) CHECK (timeframe IN ('daily', 'weekly', 'monthly')),
    return_value DECIMAL(10, 6),
    topix_adjusted_return DECIMAL(10, 6),
    UNIQUE(ticker_code, date, timeframe)
);

-- 相関分析結果
CREATE TABLE IF NOT EXISTS correlations (
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
CREATE TABLE IF NOT EXISTS backtest_results (
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
CREATE TABLE IF NOT EXISTS daily_triggers (
    id SERIAL PRIMARY KEY,
    ticker_code VARCHAR(10) REFERENCES tickers(ticker_code),
    date DATE NOT NULL,
    timeframe VARCHAR(10),
    return_value DECIMAL(10, 6),
    volume_ratio DECIMAL(6, 2),
    UNIQUE(ticker_code, date, timeframe)
);

-- 設定管理
CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_daily_prices_date ON daily_prices(date);
CREATE INDEX IF NOT EXISTS idx_returns_date ON returns(date);
CREATE INDEX IF NOT EXISTS idx_returns_ticker_timeframe ON returns(ticker_code, timeframe);
CREATE INDEX IF NOT EXISTS idx_correlations_ticker_a ON correlations(ticker_a);
CREATE INDEX IF NOT EXISTS idx_correlations_ticker_b ON correlations(ticker_b);
CREATE INDEX IF NOT EXISTS idx_correlations_timeframe ON correlations(timeframe);
CREATE INDEX IF NOT EXISTS idx_daily_triggers_date ON daily_triggers(date);

-- 初期設定データ
INSERT INTO settings (key, value) VALUES
    ('return_threshold', '0.02'),
    ('volume_threshold', '1.5'),
    ('min_correlation', '0.30'),
    ('significance_level', '0.05'),
    ('max_lag_daily', '10'),
    ('max_lag_weekly', '6'),
    ('max_lag_monthly', '3')
ON CONFLICT (key) DO NOTHING;

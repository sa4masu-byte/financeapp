/**
 * 型定義
 */

// タイムフレーム
export type Timeframe = 'daily' | 'weekly' | 'monthly';

// 方向
export type Direction = 'positive' | 'negative';

// トリガー銘柄
export interface TriggerItem {
  ticker: string;
  companyName: string;
  return: number;
  volumeRatio: number;
  candidateCount: number;
}

// 候補銘柄
export interface Candidate {
  tickerB: string;
  companyName: string;
  lag: number;
  correlation: number;
  pValue: number;
  hitRate: number | null;
  direction: Direction;
  score: number;
}

// 時系列データ
export interface TimeseriesData {
  dates: string[];
  returnsA: number[];
  returnsBShifted: number[];
}

// 過去のシグナル
export interface RecentSignal {
  date: string;
  returnA: number;
  returnB: number;
  success: boolean;
}

// 相関詳細
export interface CorrelationDetail {
  tickerA: string;
  tickerB: string;
  tickerAName: string;
  tickerBName: string;
  lag: number;
  correlation: number;
  pValue: number;
  hitRate: number | null;
  direction: Direction;
  timeseries: TimeseriesData;
  recentSignals: RecentSignal[];
}

// 設定
export interface Settings {
  returnThreshold: number;
  volumeThreshold: number;
  minCorrelation: number;
  significanceLevel: number;
  maxLagDaily: number;
  maxLagWeekly: number;
  maxLagMonthly: number;
}

// バッチステータス
export interface BatchStatus {
  status: 'idle' | 'running' | 'completed' | 'failed';
  message: string;
  startedAt: string | null;
  completedAt: string | null;
}

// APIレスポンス型（スネークケース）
export interface TriggerResponseRaw {
  ticker: string;
  company_name: string;
  return: number;
  volume_ratio: number;
  candidate_count: number;
}

export interface CandidateResponseRaw {
  ticker_b: string;
  company_name: string;
  lag: number;
  correlation: number;
  p_value: number;
  hit_rate: number | null;
  direction: Direction;
  score: number;
}

export interface CorrelationDetailRaw {
  ticker_a: string;
  ticker_b: string;
  ticker_a_name: string;
  ticker_b_name: string;
  lag: number;
  correlation: number;
  p_value: number;
  hit_rate: number | null;
  direction: Direction;
  timeseries: {
    dates: string[];
    returns_a: number[];
    returns_b_shifted: number[];
  };
  recent_signals: {
    date: string;
    return_a: number;
    return_b: number;
    success: boolean;
  }[];
}

export interface SettingsResponseRaw {
  return_threshold: number;
  volume_threshold: number;
  min_correlation: number;
  significance_level: number;
  max_lag_daily: number;
  max_lag_weekly: number;
  max_lag_monthly: number;
}

export interface BatchStatusResponseRaw {
  status: 'idle' | 'running' | 'completed' | 'failed';
  message: string;
  started_at: string | null;
  completed_at: string | null;
}

// 変換関数
export function transformTrigger(raw: TriggerResponseRaw): TriggerItem {
  return {
    ticker: raw.ticker,
    companyName: raw.company_name,
    return: raw.return,
    volumeRatio: raw.volume_ratio,
    candidateCount: raw.candidate_count,
  };
}

export function transformCandidate(raw: CandidateResponseRaw): Candidate {
  return {
    tickerB: raw.ticker_b,
    companyName: raw.company_name,
    lag: raw.lag,
    correlation: raw.correlation,
    pValue: raw.p_value,
    hitRate: raw.hit_rate,
    direction: raw.direction,
    score: raw.score,
  };
}

export function transformCorrelationDetail(raw: CorrelationDetailRaw): CorrelationDetail {
  return {
    tickerA: raw.ticker_a,
    tickerB: raw.ticker_b,
    tickerAName: raw.ticker_a_name,
    tickerBName: raw.ticker_b_name,
    lag: raw.lag,
    correlation: raw.correlation,
    pValue: raw.p_value,
    hitRate: raw.hit_rate,
    direction: raw.direction,
    timeseries: {
      dates: raw.timeseries.dates,
      returnsA: raw.timeseries.returns_a,
      returnsBShifted: raw.timeseries.returns_b_shifted,
    },
    recentSignals: raw.recent_signals.map(s => ({
      date: s.date,
      returnA: s.return_a,
      returnB: s.return_b,
      success: s.success,
    })),
  };
}

export function transformSettings(raw: SettingsResponseRaw): Settings {
  return {
    returnThreshold: raw.return_threshold,
    volumeThreshold: raw.volume_threshold,
    minCorrelation: raw.min_correlation,
    significanceLevel: raw.significance_level,
    maxLagDaily: raw.max_lag_daily,
    maxLagWeekly: raw.max_lag_weekly,
    maxLagMonthly: raw.max_lag_monthly,
  };
}

export function transformBatchStatus(raw: BatchStatusResponseRaw): BatchStatus {
  return {
    status: raw.status,
    message: raw.message,
    startedAt: raw.started_at,
    completedAt: raw.completed_at,
  };
}

/**
 * APIクライアント
 */
import axios from 'axios';
import {
  Timeframe,
  TriggerItem,
  Candidate,
  CorrelationDetail,
  Settings,
  BatchStatus,
  TriggerResponseRaw,
  CandidateResponseRaw,
  CorrelationDetailRaw,
  SettingsResponseRaw,
  BatchStatusResponseRaw,
  transformTrigger,
  transformCandidate,
  transformCorrelationDetail,
  transformSettings,
  transformBatchStatus,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const api = {
  /**
   * 今日のトリガー銘柄を取得
   */
  getTodayTriggers: async (timeframe: Timeframe): Promise<TriggerItem[]> => {
    const response = await apiClient.get<TriggerResponseRaw[]>(
      `/triggers/today?timeframe=${timeframe}`
    );
    return response.data.map(transformTrigger);
  },

  /**
   * 指定日のトリガー銘柄を取得
   */
  getTriggersByDate: async (date: string, timeframe: Timeframe): Promise<TriggerItem[]> => {
    const response = await apiClient.get<TriggerResponseRaw[]>(
      `/triggers/date/${date}?timeframe=${timeframe}`
    );
    return response.data.map(transformTrigger);
  },

  /**
   * 候補銘柄を取得
   */
  getCandidates: async (
    ticker: string,
    timeframe: Timeframe,
    topN: number = 10
  ): Promise<Candidate[]> => {
    const response = await apiClient.get<CandidateResponseRaw[]>(
      `/candidates/${ticker}?timeframe=${timeframe}&top_n=${topN}`
    );
    return response.data.map(transformCandidate);
  },

  /**
   * 相関詳細を取得
   */
  getCorrelationDetail: async (
    tickerA: string,
    tickerB: string,
    timeframe: Timeframe,
    period: number = 90
  ): Promise<CorrelationDetail> => {
    const response = await apiClient.get<CorrelationDetailRaw>(
      `/correlation/${tickerA}/${tickerB}?timeframe=${timeframe}&period=${period}`
    );
    return transformCorrelationDetail(response.data);
  },

  /**
   * 設定を取得
   */
  getSettings: async (): Promise<Settings> => {
    const response = await apiClient.get<SettingsResponseRaw>('/settings');
    return transformSettings(response.data);
  },

  /**
   * 設定を更新
   */
  updateSettings: async (settings: Partial<Settings>): Promise<Settings> => {
    // キャメルケースをスネークケースに変換
    const payload: Record<string, number> = {};
    if (settings.returnThreshold !== undefined) {
      payload.return_threshold = settings.returnThreshold;
    }
    if (settings.volumeThreshold !== undefined) {
      payload.volume_threshold = settings.volumeThreshold;
    }
    if (settings.minCorrelation !== undefined) {
      payload.min_correlation = settings.minCorrelation;
    }
    if (settings.significanceLevel !== undefined) {
      payload.significance_level = settings.significanceLevel;
    }
    if (settings.maxLagDaily !== undefined) {
      payload.max_lag_daily = settings.maxLagDaily;
    }
    if (settings.maxLagWeekly !== undefined) {
      payload.max_lag_weekly = settings.maxLagWeekly;
    }
    if (settings.maxLagMonthly !== undefined) {
      payload.max_lag_monthly = settings.maxLagMonthly;
    }

    const response = await apiClient.post<SettingsResponseRaw>('/settings', payload);
    return transformSettings(response.data);
  },

  /**
   * バッチ実行をトリガー
   */
  triggerBatch: async (): Promise<BatchStatus> => {
    const response = await apiClient.post<BatchStatusResponseRaw>('/batch/run');
    return transformBatchStatus(response.data);
  },

  /**
   * バッチステータスを取得
   */
  getBatchStatus: async (): Promise<BatchStatus> => {
    const response = await apiClient.get<BatchStatusResponseRaw>('/batch/status');
    return transformBatchStatus(response.data);
  },

  /**
   * キャッシュ情報を取得
   */
  getCacheInfo: async (): Promise<Record<string, unknown>> => {
    const response = await apiClient.get('/cache/info');
    return response.data;
  },

  /**
   * キャッシュをクリア
   */
  clearCache: async (): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post('/cache/clear');
    return response.data;
  },
};

export default api;

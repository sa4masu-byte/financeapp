import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { Settings, BatchStatus } from '../types';

function SettingsPanel() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [editedSettings, setEditedSettings] = useState<Settings | null>(null);
  const [batchStatus, setBatchStatus] = useState<BatchStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // 設定を取得
  useEffect(() => {
    const fetchSettings = async () => {
      setLoading(true);
      try {
        const [settingsData, statusData] = await Promise.all([
          api.getSettings(),
          api.getBatchStatus(),
        ]);
        setSettings(settingsData);
        setEditedSettings(settingsData);
        setBatchStatus(statusData);
      } catch (err) {
        setError('設定の取得に失敗しました');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchSettings();
  }, []);

  // 設定を保存
  const handleSave = async () => {
    if (!editedSettings) return;

    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const updatedSettings = await api.updateSettings(editedSettings);
      setSettings(updatedSettings);
      setEditedSettings(updatedSettings);
      setSuccessMessage('設定を保存しました');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('設定の保存に失敗しました');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  // デフォルトにリセット
  const handleReset = () => {
    const defaultSettings: Settings = {
      returnThreshold: 0.02,
      volumeThreshold: 1.5,
      minCorrelation: 0.30,
      significanceLevel: 0.05,
      maxLagDaily: 10,
      maxLagWeekly: 6,
      maxLagMonthly: 3,
    };
    setEditedSettings(defaultSettings);
  };

  // バッチ実行
  const handleRunBatch = async () => {
    try {
      const status = await api.triggerBatch();
      setBatchStatus(status);

      // ステータスをポーリング
      const pollStatus = setInterval(async () => {
        const currentStatus = await api.getBatchStatus();
        setBatchStatus(currentStatus);
        if (currentStatus.status !== 'running') {
          clearInterval(pollStatus);
        }
      }, 5000);
    } catch (err) {
      setError('バッチの実行に失敗しました');
      console.error(err);
    }
  };

  // キャッシュクリア
  const handleClearCache = async () => {
    try {
      await api.clearCache();
      setSuccessMessage('キャッシュをクリアしました');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err) {
      setError('キャッシュのクリアに失敗しました');
      console.error(err);
    }
  };

  const handleInputChange = (key: keyof Settings, value: string) => {
    if (!editedSettings) return;

    const numValue = parseFloat(value);
    if (isNaN(numValue)) return;

    setEditedSettings({
      ...editedSettings,
      [key]: numValue,
    });
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="loading-spinner w-8 h-8"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">設定</h2>

      {/* メッセージ */}
      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}
      {successMessage && (
        <div className="bg-green-50 text-green-700 px-4 py-3 rounded-lg">
          {successMessage}
        </div>
      )}

      {/* 分析パラメータ */}
      <div className="card">
        <h3 className="text-lg font-medium text-gray-900 mb-4">分析パラメータ</h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              リターン閾値
            </label>
            <div className="flex items-center">
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={editedSettings?.returnThreshold || 0}
                onChange={(e) => handleInputChange('returnThreshold', e.target.value)}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm px-3 py-2 border"
              />
              <span className="ml-2 text-gray-500">
                ({((editedSettings?.returnThreshold || 0) * 100).toFixed(0)}%)
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              トリガー判定の変動率閾値
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              出来高閾値
            </label>
            <div className="flex items-center">
              <input
                type="number"
                step="0.1"
                min="1"
                value={editedSettings?.volumeThreshold || 0}
                onChange={(e) => handleInputChange('volumeThreshold', e.target.value)}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm px-3 py-2 border"
              />
              <span className="ml-2 text-gray-500">倍</span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              20日平均出来高に対する倍率
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              最小相関係数
            </label>
            <input
              type="number"
              step="0.05"
              min="0"
              max="1"
              value={editedSettings?.minCorrelation || 0}
              onChange={(e) => handleInputChange('minCorrelation', e.target.value)}
              className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm px-3 py-2 border"
            />
            <p className="text-xs text-gray-500 mt-1">
              この値以上の相関を有意とみなす
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              有意水準
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={editedSettings?.significanceLevel || 0}
              onChange={(e) => handleInputChange('significanceLevel', e.target.value)}
              className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm px-3 py-2 border"
            />
            <p className="text-xs text-gray-500 mt-1">
              p値がこの値未満で統計的に有意
            </p>
          </div>
        </div>
      </div>

      {/* タイムラグ設定 */}
      <div className="card">
        <h3 className="text-lg font-medium text-gray-900 mb-4">タイムラグ設定</h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              日足の最大ラグ
            </label>
            <div className="flex items-center">
              <input
                type="number"
                step="1"
                min="1"
                max="30"
                value={editedSettings?.maxLagDaily || 0}
                onChange={(e) => handleInputChange('maxLagDaily', e.target.value)}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm px-3 py-2 border"
              />
              <span className="ml-2 text-gray-500">日</span>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              週足の最大ラグ
            </label>
            <div className="flex items-center">
              <input
                type="number"
                step="1"
                min="1"
                max="12"
                value={editedSettings?.maxLagWeekly || 0}
                onChange={(e) => handleInputChange('maxLagWeekly', e.target.value)}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm px-3 py-2 border"
              />
              <span className="ml-2 text-gray-500">週</span>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              月足の最大ラグ
            </label>
            <div className="flex items-center">
              <input
                type="number"
                step="1"
                min="1"
                max="6"
                value={editedSettings?.maxLagMonthly || 0}
                onChange={(e) => handleInputChange('maxLagMonthly', e.target.value)}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm px-3 py-2 border"
              />
              <span className="ml-2 text-gray-500">ヶ月</span>
            </div>
          </div>
        </div>
      </div>

      {/* ボタン */}
      <div className="flex justify-end space-x-4">
        <button
          onClick={handleReset}
          className="btn btn-secondary"
        >
          デフォルトに戻す
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn btn-primary disabled:opacity-50"
        >
          {saving ? '保存中...' : '設定を保存'}
        </button>
      </div>

      {/* バッチ実行 */}
      <div className="card">
        <h3 className="text-lg font-medium text-gray-900 mb-4">バッチ処理</h3>

        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600">
              日次更新バッチを手動で実行します
            </p>
            {batchStatus && (
              <p className="text-xs text-gray-500 mt-1">
                ステータス:{' '}
                <span className={
                  batchStatus.status === 'running' ? 'text-yellow-600' :
                  batchStatus.status === 'completed' ? 'text-green-600' :
                  batchStatus.status === 'failed' ? 'text-red-600' :
                  'text-gray-600'
                }>
                  {batchStatus.status}
                </span>
                {batchStatus.message && ` - ${batchStatus.message}`}
              </p>
            )}
          </div>
          <button
            onClick={handleRunBatch}
            disabled={batchStatus?.status === 'running'}
            className="btn btn-primary disabled:opacity-50"
          >
            {batchStatus?.status === 'running' ? '実行中...' : 'バッチ実行'}
          </button>
        </div>
      </div>

      {/* キャッシュ管理 */}
      <div className="card">
        <h3 className="text-lg font-medium text-gray-900 mb-4">キャッシュ管理</h3>

        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600">
              キャッシュをクリアして最新のデータを取得します
            </p>
          </div>
          <button
            onClick={handleClearCache}
            className="btn btn-secondary"
          >
            キャッシュクリア
          </button>
        </div>
      </div>
    </div>
  );
}

export default SettingsPanel;

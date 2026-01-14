import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { TriggerItem, Timeframe } from '../types';

const TIMEFRAME_LABELS: Record<Timeframe, string> = {
  daily: '日足',
  weekly: '週足',
  monthly: '月足',
};

function Dashboard() {
  const navigate = useNavigate();
  const [timeframe, setTimeframe] = useState<Timeframe>('daily');
  const [triggers, setTriggers] = useState<TriggerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTriggers = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getTodayTriggers(timeframe);
        setTriggers(data);
      } catch (err) {
        setError('データの取得に失敗しました');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchTriggers();
  }, [timeframe]);

  const formatPercent = (value: number) => {
    const percent = (value * 100).toFixed(2);
    return value >= 0 ? `+${percent}%` : `${percent}%`;
  };

  const formatNumber = (value: number) => {
    return value.toFixed(2);
  };

  const handleRowClick = (ticker: string) => {
    navigate(`/candidates/${ticker}?timeframe=${timeframe}`);
  };

  const today = new Date().toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  return (
    <div className="space-y-6">
      {/* ページタイトル */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            今日のトリガー銘柄
          </h2>
          <p className="text-sm text-gray-500 mt-1">{today}</p>
        </div>
      </div>

      {/* タイムフレーム切替タブ */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {(Object.keys(TIMEFRAME_LABELS) as Timeframe[]).map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`tab ${timeframe === tf ? 'active' : ''}`}
            >
              {TIMEFRAME_LABELS[tf]}
            </button>
          ))}
        </nav>
      </div>

      {/* コンテンツ */}
      <div className="card">
        {loading ? (
          <div className="flex justify-center items-center py-12">
            <div className="loading-spinner w-8 h-8"></div>
          </div>
        ) : error ? (
          <div className="text-center py-12">
            <p className="text-red-600">{error}</p>
            <button
              onClick={() => window.location.reload()}
              className="btn btn-secondary mt-4"
            >
              再試行
            </button>
          </div>
        ) : triggers.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-500">
              本日のトリガー銘柄はありません
            </p>
            <p className="text-sm text-gray-400 mt-2">
              市場が開いていないか、閾値を超える変動がありませんでした
            </p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>銘柄コード</th>
                <th>銘柄名</th>
                <th className="text-right">変動率</th>
                <th className="text-right">出来高比</th>
                <th className="text-right">候補数</th>
              </tr>
            </thead>
            <tbody>
              {triggers.map((trigger) => (
                <tr
                  key={trigger.ticker}
                  onClick={() => handleRowClick(trigger.ticker)}
                  className="cursor-pointer hover:bg-primary-50"
                >
                  <td className="font-mono">{trigger.ticker}</td>
                  <td>{trigger.companyName}</td>
                  <td
                    className={`text-right font-medium ${
                      trigger.return >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    {formatPercent(trigger.return)}
                  </td>
                  <td className="text-right">{formatNumber(trigger.volumeRatio)}x</td>
                  <td className="text-right">
                    <span className="badge badge-neutral">
                      {trigger.candidateCount}件
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 説明 */}
      <div className="bg-blue-50 rounded-lg p-4">
        <h3 className="font-medium text-blue-900 mb-2">トリガー条件</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>- リターンが閾値（デフォルト: 2%）以上の変動</li>
          <li>- 出来高が過去20日平均の閾値倍（デフォルト: 1.5倍）以上</li>
        </ul>
        <p className="text-sm text-blue-700 mt-2">
          銘柄をクリックすると、その銘柄に連動する候補銘柄を確認できます
        </p>
      </div>
    </div>
  );
}

export default Dashboard;

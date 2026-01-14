import { useState, useEffect } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { Candidate, CorrelationDetail, Timeframe } from '../types';
import CorrelationChart from './CorrelationChart';

const TIMEFRAME_LABELS: Record<Timeframe, string> = {
  daily: '日足',
  weekly: '週足',
  monthly: '月足',
};

const TIMEFRAME_LAG_LABELS: Record<Timeframe, string> = {
  daily: '日',
  weekly: '週',
  monthly: 'ヶ月',
};

function CandidateList() {
  const { ticker } = useParams<{ ticker: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const initialTimeframe = (searchParams.get('timeframe') as Timeframe) || 'daily';

  const [timeframe, setTimeframe] = useState<Timeframe>(initialTimeframe);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [correlationDetail, setCorrelationDetail] = useState<CorrelationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 候補銘柄を取得
  useEffect(() => {
    if (!ticker) return;

    const fetchCandidates = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getCandidates(ticker, timeframe, 20);
        setCandidates(data);
        if (data.length > 0) {
          setSelectedCandidate(data[0]);
        }
      } catch (err) {
        setError('データの取得に失敗しました');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchCandidates();
  }, [ticker, timeframe]);

  // 相関詳細を取得
  useEffect(() => {
    if (!ticker || !selectedCandidate) return;

    const fetchDetail = async () => {
      setDetailLoading(true);
      try {
        const data = await api.getCorrelationDetail(
          ticker,
          selectedCandidate.tickerB,
          timeframe
        );
        setCorrelationDetail(data);
      } catch (err) {
        console.error(err);
        setCorrelationDetail(null);
      } finally {
        setDetailLoading(false);
      }
    };

    fetchDetail();
  }, [ticker, selectedCandidate, timeframe]);

  const formatPercent = (value: number) => {
    return (value * 100).toFixed(2) + '%';
  };

  const formatPValue = (value: number) => {
    if (value < 0.0001) return '< 0.0001';
    return value.toFixed(4);
  };

  const formatScore = (value: number) => {
    return (value * 100).toFixed(0);
  };

  if (!ticker) {
    return <div>銘柄が指定されていません</div>;
  }

  return (
    <div className="space-y-6">
      {/* ヘッダー */}
      <div className="flex items-center space-x-4">
        <button
          onClick={() => navigate('/')}
          className="text-gray-500 hover:text-gray-700"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h2 className="text-2xl font-bold text-gray-900">
            候補銘柄リスト
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            トリガー銘柄: {ticker}
          </p>
        </div>
      </div>

      {/* タイムフレーム切替 */}
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

      {loading ? (
        <div className="flex justify-center items-center py-12">
          <div className="loading-spinner w-8 h-8"></div>
        </div>
      ) : error ? (
        <div className="text-center py-12">
          <p className="text-red-600">{error}</p>
        </div>
      ) : candidates.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-gray-500">
            候補銘柄が見つかりませんでした
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 候補銘柄テーブル */}
          <div className="card">
            <h3 className="font-medium text-gray-900 mb-4">候補銘柄ランキング</h3>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>銘柄</th>
                    <th className="text-right">ラグ</th>
                    <th className="text-right">相関</th>
                    <th className="text-right">ヒット率</th>
                    <th className="text-right">スコア</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((candidate, index) => (
                    <tr
                      key={`${candidate.tickerB}-${candidate.lag}`}
                      onClick={() => setSelectedCandidate(candidate)}
                      className={`cursor-pointer ${
                        selectedCandidate?.tickerB === candidate.tickerB &&
                        selectedCandidate?.lag === candidate.lag
                          ? 'bg-primary-50'
                          : 'hover:bg-gray-50'
                      }`}
                    >
                      <td className="text-gray-500">{index + 1}</td>
                      <td>
                        <div className="font-mono text-sm">{candidate.tickerB}</div>
                        <div className="text-xs text-gray-500">{candidate.companyName}</div>
                      </td>
                      <td className="text-right">
                        {candidate.lag}{TIMEFRAME_LAG_LABELS[timeframe]}
                      </td>
                      <td className="text-right">
                        <span className={`badge ${
                          candidate.direction === 'positive'
                            ? 'badge-positive'
                            : 'badge-negative'
                        }`}>
                          {candidate.correlation.toFixed(2)}
                        </span>
                      </td>
                      <td className="text-right">
                        {candidate.hitRate ? formatPercent(candidate.hitRate) : '-'}
                      </td>
                      <td className="text-right font-medium">
                        {formatScore(candidate.score)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* 詳細パネル */}
          <div className="card">
            {selectedCandidate && (
              <>
                <h3 className="font-medium text-gray-900 mb-4">
                  {ticker} → {selectedCandidate.tickerB} の相関詳細
                </h3>

                {/* 統計情報 */}
                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">相関係数</div>
                    <div className={`text-xl font-bold ${
                      selectedCandidate.direction === 'positive'
                        ? 'text-green-600'
                        : 'text-red-600'
                    }`}>
                      {selectedCandidate.correlation.toFixed(3)}
                    </div>
                    <div className="text-xs text-gray-400">
                      {selectedCandidate.direction === 'positive' ? '正の相関' : '負の相関'}
                    </div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">タイムラグ</div>
                    <div className="text-xl font-bold text-gray-900">
                      {selectedCandidate.lag}{TIMEFRAME_LAG_LABELS[timeframe]}
                    </div>
                    <div className="text-xs text-gray-400">
                      {ticker}の動きの後
                    </div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">p値</div>
                    <div className="text-xl font-bold text-gray-900">
                      {formatPValue(selectedCandidate.pValue)}
                    </div>
                    <div className="text-xs text-gray-400">統計的有意性</div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">ヒット率</div>
                    <div className="text-xl font-bold text-gray-900">
                      {selectedCandidate.hitRate
                        ? formatPercent(selectedCandidate.hitRate)
                        : '-'}
                    </div>
                    <div className="text-xs text-gray-400">バックテスト成功率</div>
                  </div>
                </div>

                {/* チャート */}
                {detailLoading ? (
                  <div className="flex justify-center items-center py-12">
                    <div className="loading-spinner w-6 h-6"></div>
                  </div>
                ) : correlationDetail ? (
                  <CorrelationChart detail={correlationDetail} />
                ) : null}

                {/* 過去のシグナル */}
                {correlationDetail && correlationDetail.recentSignals.length > 0 && (
                  <div className="mt-6">
                    <h4 className="text-sm font-medium text-gray-900 mb-2">
                      直近のシグナル履歴
                    </h4>
                    <div className="overflow-x-auto">
                      <table className="data-table text-xs">
                        <thead>
                          <tr>
                            <th>日付</th>
                            <th className="text-right">{ticker}</th>
                            <th className="text-right">{selectedCandidate.tickerB}</th>
                            <th className="text-center">結果</th>
                          </tr>
                        </thead>
                        <tbody>
                          {correlationDetail.recentSignals.slice(0, 5).map((signal, i) => (
                            <tr key={i}>
                              <td>{signal.date}</td>
                              <td className={`text-right ${
                                signal.returnA >= 0 ? 'text-green-600' : 'text-red-600'
                              }`}>
                                {formatPercent(signal.returnA)}
                              </td>
                              <td className={`text-right ${
                                signal.returnB >= 0 ? 'text-green-600' : 'text-red-600'
                              }`}>
                                {formatPercent(signal.returnB)}
                              </td>
                              <td className="text-center">
                                {signal.success ? (
                                  <span className="text-green-600">HIT</span>
                                ) : (
                                  <span className="text-gray-400">MISS</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* 説明 */}
      <div className="bg-yellow-50 rounded-lg p-4">
        <h3 className="font-medium text-yellow-900 mb-2">スコアの計算方法</h3>
        <p className="text-sm text-yellow-800">
          スコア = 0.4 × |相関係数| + 0.4 × ヒット率 + 0.2 × (1 - p値)
        </p>
        <p className="text-sm text-yellow-700 mt-2">
          {selectedCandidate?.direction === 'positive'
            ? '正の相関: トリガー銘柄と同方向への動きを予測'
            : '負の相関: トリガー銘柄と逆方向への動きを予測'}
        </p>
      </div>
    </div>
  );
}

export default CandidateList;

import Plot from 'react-plotly.js';
import { CorrelationDetail } from '../types';

interface Props {
  detail: CorrelationDetail;
}

function CorrelationChart({ detail }: Props) {
  const { timeseries, tickerA, tickerB, tickerAName, tickerBName, lag } = detail;

  // リターンをパーセント表示に変換
  const returnsAPercent = timeseries.returnsA.map((r) => r * 100);
  const returnsBPercent = timeseries.returnsBShifted.map((r) => r * 100);

  const data: Plotly.Data[] = [
    {
      x: timeseries.dates,
      y: returnsAPercent,
      type: 'scatter',
      mode: 'lines',
      name: `${tickerA} (${tickerAName})`,
      line: {
        color: '#3b82f6',
        width: 2,
      },
      hovertemplate: '%{x}<br>%{y:.2f}%<extra></extra>',
    },
    {
      x: timeseries.dates,
      y: returnsBPercent,
      type: 'scatter',
      mode: 'lines',
      name: `${tickerB} (${tickerBName}) [${lag}日後]`,
      line: {
        color: '#ef4444',
        width: 2,
      },
      hovertemplate: '%{x}<br>%{y:.2f}%<extra></extra>',
    },
  ];

  const layout: Partial<Plotly.Layout> = {
    autosize: true,
    height: 300,
    margin: {
      l: 50,
      r: 20,
      t: 30,
      b: 50,
    },
    xaxis: {
      title: '',
      tickangle: -45,
      tickfont: {
        size: 10,
      },
      gridcolor: '#f0f0f0',
    },
    yaxis: {
      title: 'リターン (%)',
      titlefont: {
        size: 12,
      },
      tickfont: {
        size: 10,
      },
      gridcolor: '#f0f0f0',
      zeroline: true,
      zerolinecolor: '#999',
      zerolinewidth: 1,
    },
    legend: {
      orientation: 'h',
      yanchor: 'bottom',
      y: 1.02,
      xanchor: 'right',
      x: 1,
      font: {
        size: 10,
      },
    },
    hovermode: 'x unified',
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
  };

  const config: Partial<Plotly.Config> = {
    responsive: true,
    displayModeBar: false,
  };

  return (
    <div className="w-full">
      <h4 className="text-sm font-medium text-gray-900 mb-2">
        リターン推移（{tickerB}は{lag}日シフト）
      </h4>
      <Plot
        data={data}
        layout={layout}
        config={config}
        style={{ width: '100%' }}
        useResizeHandler
      />
      <p className="text-xs text-gray-500 mt-2">
        青線: {tickerA}のリターン / 赤線: {tickerB}のリターン（{lag}日後にシフトして表示）
      </p>
    </div>
  );
}

export default CorrelationChart;

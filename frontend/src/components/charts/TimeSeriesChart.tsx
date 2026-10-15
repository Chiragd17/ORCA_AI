import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface TimeSeriesChartProps {
  data: Array<{ time: string; value: number }>;
  yLabel?: string;
  unit?: string;
}

export const TimeSeriesChart: React.FC<TimeSeriesChartProps> = ({
  data,
  yLabel = 'Observation',
  unit = '',
}) => {
  if (!data || data.length === 0) {
    return (
      <div className="h-48 w-full rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-xs text-slate-500 italic">
        No time-series data available for the selected interval.
      </div>
    );
  }

  return (
    <div className="h-64 w-full bg-slate-900/60 border border-slate-800 rounded-xl p-4">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
          <YAxis stroke="#64748b" fontSize={11} />
          <Tooltip
            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
            formatter={(value: any) => [`${value} ${unit}`, yLabel]}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#06b6d4"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

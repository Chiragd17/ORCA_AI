import React from 'react';
import { InvestigationPanel } from '../investigations/InvestigationPanel';
import { Activity, Thermometer, LineChart } from 'lucide-react';

export const MarineMonitoringWorkspace: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Activity className="w-6 h-6 text-cyan-400" />
          Marine Environmental Monitoring Workspace
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Analyze sea surface temperatures, chlorophyll indicators, and long-term oceanographic time series.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Thermometer className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Observation Types</div>
            <div className="text-sm font-medium text-slate-100">SST, Wave Spectrum, Chlorophyll</div>
          </div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <LineChart className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Analysis Mode</div>
            <div className="text-sm font-medium text-slate-100">Multi-year Baseline & Anomalies</div>
          </div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Activity className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Assigned Agent</div>
            <div className="text-sm font-medium text-slate-100">Person 1: Ocean Research Agent</div>
          </div>
        </div>
      </div>

      <InvestigationPanel
        workspace="marine_monitoring"
        defaultPrompt="Compare available sea-surface temperature observations off Karnataka across the last five years and explain the seasonal patterns the data supports."
        defaultLat={13.20}
        defaultLon={74.50}
      />
    </div>
  );
};

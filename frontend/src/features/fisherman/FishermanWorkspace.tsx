import React from 'react';
import { InvestigationPanel } from '../investigations/InvestigationPanel';
import { Anchor, Compass, Waves } from 'lucide-react';

export const FishermanWorkspace: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Anchor className="w-6 h-6 text-cyan-400" />
          Fisherman & Marine Operator Workspace
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Inspect offshore wave heights, wind forecasts, SST, and marine hazard warnings for coastal fishing operations.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Waves className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Study Region</div>
            <div className="text-sm font-medium text-slate-100">Karnataka Coast / Arabian Sea</div>
          </div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Compass className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Coordinate Baseline</div>
            <div className="text-sm font-medium text-slate-100">Mangaluru Port (12.87°N, 74.88°E)</div>
          </div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Anchor className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Active Agents</div>
            <div className="text-sm font-medium text-slate-100">Ocean Research + Hazard + Verification</div>
          </div>
        </div>
      </div>

      <InvestigationPanel
        workspace="fisherman"
        defaultPrompt="I am planning to fish offshore near Mangaluru tomorrow morning. Investigate available wave and wind forecasts and any relevant warnings."
        defaultLat={12.87}
        defaultLon={74.88}
      />
    </div>
  );
};

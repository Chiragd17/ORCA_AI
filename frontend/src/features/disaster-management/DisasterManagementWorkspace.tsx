import React from 'react';
import { InvestigationPanel } from '../investigations/InvestigationPanel';
import { AlertTriangle, Radio, History } from 'lucide-react';

export const DisasterManagementWorkspace: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <AlertTriangle className="w-6 h-6 text-amber-400" />
          Disaster Management & Emergency Planning Workspace
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Coordinate cyclone response, track historical storm paths (IBTrACS), inspect live disaster alerts (GDACS), and quantify exposed populations.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <History className="w-8 h-8 text-amber-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Track Playback</div>
            <div className="text-sm font-medium text-slate-100">NOAA IBTrACS Historical Cyclones</div>
          </div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Radio className="w-8 h-8 text-amber-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Real-time Feed</div>
            <div className="text-sm font-medium text-slate-100">GDACS Disaster Alert Footprints</div>
          </div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <AlertTriangle className="w-8 h-8 text-amber-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Key Collaborators</div>
            <div className="text-sm font-medium text-slate-100">Hazard Agent + Coastal Risk Agent</div>
          </div>
        </div>
      </div>

      <InvestigationPanel
        workspace="disaster_management"
        defaultPrompt="Investigate the latest available cyclone information relevant to the Arabian Sea, identify potentially exposed coastal areas using available data, and explain what remains uncertain."
        defaultLat={15.00}
        defaultLon={73.00}
      />
    </div>
  );
};

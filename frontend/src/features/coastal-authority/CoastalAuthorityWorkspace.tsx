import React from 'react';
import { InvestigationPanel } from '../investigations/InvestigationPanel';
import { Building2, Users, Map } from 'lucide-react';

export const CoastalAuthorityWorkspace: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Building2 className="w-6 h-6 text-cyan-400" />
          Coastal Authority & Planning Workspace
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Evaluate coastal infrastructure, population exposure, settlement proximity, and geographic hazard intersections.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Building2 className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Asset Inventory</div>
            <div className="text-sm font-medium text-slate-100">Ports, Hospitals, Critical Facilities</div>
          </div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Users className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Population Layer</div>
            <div className="text-sm font-medium text-slate-100">WorldPop Gridded Estimates</div>
          </div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Map className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Assigned Agent</div>
            <div className="text-sm font-medium text-slate-100">Person 3: Coastal Impact & Risk Agent</div>
          </div>
        </div>
      </div>

      <InvestigationPanel
        workspace="coastal_authority"
        defaultPrompt="Using this hazard boundary and the available population dataset, identify intersecting settlements and estimate potential population exposure."
        defaultLat={13.34}
        defaultLon={74.74}
      />
    </div>
  );
};

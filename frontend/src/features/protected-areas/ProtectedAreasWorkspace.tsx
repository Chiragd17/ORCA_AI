import React from 'react';
import { InvestigationPanel } from '../investigations/InvestigationPanel';
import { Shield, Trees, MapPin } from 'lucide-react';

export const ProtectedAreasWorkspace: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Shield className="w-6 h-6 text-cyan-400" />
          Marine Protected Areas (MPA) Workspace
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Monitor conservation zones, marine sanctuaries, and ecological indicators inside and outside boundary polygons.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Trees className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Boundary Registry</div>
            <div className="text-sm font-medium text-slate-100">WDPA / Coastal Ecology Sanctuaries</div>
          </div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <MapPin className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Spatial Analysis</div>
            <div className="text-sm font-medium text-slate-100">Polygon Intersections & Buffers</div>
          </div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex items-center gap-3">
          <Shield className="w-8 h-8 text-cyan-400/80" />
          <div>
            <div className="text-xs text-slate-400 uppercase font-semibold">Collaborating Agents</div>
            <div className="text-sm font-medium text-slate-100">Coastal Risk + Ocean Research</div>
          </div>
        </div>
      </div>

      <InvestigationPanel
        workspace="protected_areas"
        defaultPrompt="Compare available temperature and chlorophyll observations inside and outside this protected area, and identify any supported environmental differences."
        defaultLat={14.05}
        defaultLon={74.45}
      />
    </div>
  );
};

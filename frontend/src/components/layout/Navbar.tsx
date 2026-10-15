import React from 'react';
import { NavLink } from 'react-router-dom';
import { Anchor, Activity, Shield, Building2, AlertTriangle } from 'lucide-react';

const workspaces = [
  { name: 'Fisherman', path: '/fisherman', icon: Anchor },
  { name: 'Marine Monitoring', path: '/marine-monitoring', icon: Activity },
  { name: 'Protected Areas', path: '/protected-areas', icon: Shield },
  { name: 'Coastal Authority', path: '/coastal-authority', icon: Building2 },
  { name: 'Disaster Management', path: '/disaster-management', icon: AlertTriangle },
];

export const Navbar: React.FC = () => {
  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-cyan-600 flex items-center justify-center font-bold text-white tracking-wider shadow-lg shadow-cyan-900/40">
            Ω
          </div>
          <div>
            <span className="font-bold text-lg tracking-tight text-white">ORCA</span>
            <span className="hidden sm:inline-block ml-2 text-xs text-slate-400 font-medium border-l border-slate-700 pl-2">
              Marine & Coastal Intelligence
            </span>
          </div>
        </div>

        <nav className="flex items-center gap-1 sm:gap-2">
          {workspaces.map((ws) => {
            const Icon = ws.icon;
            return (
              <NavLink
                key={ws.path}
                to={ws.path}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                  }`
                }
              >
                <Icon className="w-3.5 h-3.5" />
                <span className="hidden md:inline">{ws.name}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>
    </header>
  );
};

import React from 'react';
import { MapPin } from 'lucide-react';

interface MapViewerProps {
  latitude?: number;
  longitude?: number;
  className?: string;
}

export const MapViewer: React.FC<MapViewerProps> = ({
  latitude = 12.87,
  longitude = 74.88,
  className = 'h-64',
}) => {
  return (
    <div className={`relative w-full rounded-xl bg-slate-900 border border-slate-800 flex flex-col items-center justify-center text-slate-500 overflow-hidden ${className}`}>
      <div className="absolute inset-0 bg-[radial-gradient(#0e7490_1px,transparent_1px)] [background-size:16px_16px] opacity-20 pointer-events-none" />
      <MapPin className="w-8 h-8 text-cyan-400 mb-2 animate-bounce" />
      <p className="text-xs font-semibold text-slate-300">MapLibre GL Geospatial Viewer</p>
      <p className="text-[11px] text-slate-500">Center: {latitude.toFixed(4)}°N, {longitude.toFixed(4)}°E (WGS84)</p>
    </div>
  );
};

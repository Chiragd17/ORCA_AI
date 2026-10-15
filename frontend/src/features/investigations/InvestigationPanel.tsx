import React, { useState } from 'react';
import { WorkspaceType, InvestigationResponse, ExecutionEvent, EvidenceRecord } from '../../types';
import { apiClient } from '../../lib/api-client';
import { Play, CheckCircle2, AlertCircle, Clock, Database, ShieldCheck } from 'lucide-react';

interface InvestigationPanelProps {
  workspace: WorkspaceType;
  defaultPrompt?: string;
  defaultLat?: number;
  defaultLon?: number;
}

export const InvestigationPanel: React.FC<InvestigationPanelProps> = ({
  workspace,
  defaultPrompt = '',
  defaultLat = 12.87,
  defaultLon = 74.88,
}) => {
  const [prompt, setPrompt] = useState(defaultPrompt);
  const [lat, setLat] = useState(defaultLat);
  const [lon, setLon] = useState(defaultLon);
  const [loading, setLoading] = useState(false);
  const [investigation, setInvestigation] = useState<InvestigationResponse | null>(null);
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const [evidenceList, setEvidenceList] = useState<EvidenceRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  const handleRunInvestigation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    setLoading(true);
    setError(null);
    setInvestigation(null);
    setEvents([]);
    setEvidenceList([]);

    try {
      const inv = await apiClient.createInvestigation({
        workspace,
        prompt,
        latitude: lat,
        longitude: lon,
      });
      setInvestigation(inv);

      // Fetch genuine events and evidence
      const evts = await apiClient.getInvestigationEvents(inv.id);
      setEvents(evts);

      const evs = await apiClient.getInvestigationEvidence(inv.id);
      setEvidenceList(evs);
    } catch (err: any) {
      setError(err.message || 'Failed to complete investigation');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Query Form */}
      <form onSubmit={handleRunInvestigation} className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-4">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Investigation Query ({workspace.replace('_', ' ')})
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            placeholder="Enter question or hypothesis for multi-agent investigation..."
            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition-colors"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Target Latitude (WGS84)</label>
            <input
              type="number"
              step="any"
              value={lat}
              onChange={(e) => setLat(parseFloat(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1">Target Longitude (WGS84)</label>
            <input
              type="number"
              step="any"
              value={lon}
              onChange={(e) => setLon(parseFloat(e.target.value))}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium text-sm transition-colors shadow-lg shadow-cyan-900/30"
          >
            {loading ? <Clock className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            <span>{loading ? 'Running Multi-Agent Investigation...' : 'Start Investigation'}</span>
          </button>
        </div>
      </form>

      {/* Error state */}
      {error && (
        <div className="p-4 rounded-lg bg-red-950/40 border border-red-800/60 text-red-300 text-sm flex items-center gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 text-red-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Execution Events Stream */}
      {events.length > 0 && (
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-xl p-4 space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <ActivityIcon className="w-4 h-4 text-cyan-400" />
            Execution Event Trace ({events.length})
          </h4>
          <div className="divide-y divide-slate-800/60 text-xs font-mono">
            {events.map((evt) => (
              <div key={evt.id} className="py-1.5 flex items-center justify-between text-slate-300">
                <span className="text-cyan-400 font-semibold">{evt.event_type}</span>
                <span className="text-slate-500">{evt.agent_id || 'orchestrator'}</span>
                <span className="text-slate-600 text-[10px]">
                  {new Date(evt.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Investigation Results */}
      {investigation && (
        <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-5 space-y-5">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-base font-semibold text-white flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              Investigation Result ({investigation.status})
            </h3>
            <span className="text-xs text-slate-400">ID: {investigation.id}</span>
          </div>

          <p className="text-sm text-slate-200 leading-relaxed">{investigation.final_answer}</p>

          {/* Limitations */}
          {investigation.limitations.length > 0 && (
            <div className="bg-amber-950/20 border border-amber-800/40 rounded-lg p-3 text-xs text-amber-200 space-y-1">
              <div className="font-semibold flex items-center gap-1.5 text-amber-400">
                <AlertCircle className="w-4 h-4" /> Disclosed Limitations & Data Boundaries:
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-amber-300/80">
                {investigation.limitations.map((lim, i) => (
                  <li key={i}>{lim}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Evidence Registry Records */}
          <div className="space-y-2 pt-2 border-t border-slate-800">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <Database className="w-4 h-4 text-cyan-400" />
              Evidence Provenance ({evidenceList.length})
            </h4>
            {evidenceList.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No evidence records registered yet.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {evidenceList.map((ev) => (
                  <div key={ev.id} className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs space-y-1">
                    <div className="font-semibold text-cyan-300">{ev.id}</div>
                    <div className="text-slate-400 truncate">{ev.source_name}</div>
                    <div className="text-slate-500 text-[10px]">Data Type: {ev.data_type}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

const ActivityIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
  </svg>
);

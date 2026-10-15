import React from 'react';
import { VerificationStatus } from '../../types';
import { ShieldCheck, ShieldAlert, HelpCircle } from 'lucide-react';

interface EvidenceBadgeProps {
  status: VerificationStatus;
}

export const EvidenceBadge: React.FC<EvidenceBadgeProps> = ({ status }) => {
  switch (status) {
    case 'verified':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
          <ShieldCheck className="w-3 h-3" />
          Verified
        </span>
      );
    case 'conflicting':
    case 'needs_review':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-950/60 text-amber-400 border border-amber-800/60">
          <ShieldAlert className="w-3 h-3" />
          {status.replace('_', ' ').toUpperCase()}
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-400 border border-slate-700">
          <HelpCircle className="w-3 h-3" />
          {status.replace('_', ' ')}
        </span>
      );
  }
};

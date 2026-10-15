export type WorkspaceType =
  | 'fisherman'
  | 'marine_monitoring'
  | 'protected_areas'
  | 'coastal_authority'
  | 'disaster_management';

export type VerificationStatus =
  | 'verified'
  | 'unverified'
  | 'needs_review'
  | 'conflicting'
  | 'insufficient_evidence';

export type FindingCategory =
  | 'observation'
  | 'forecast'
  | 'historical_record'
  | 'deterministic_calculation'
  | 'ai_interpretation';

export interface EvidenceRecord {
  id: string;
  source_name: string;
  source_uri: string;
  observation_time?: string;
  retrieval_time: string;
  latitude?: number;
  longitude?: number;
  data_type: string;
  value?: any;
  unit?: string;
  metadata?: Record<string, any>;
}

export interface Finding {
  id?: string;
  claim: string;
  value?: any;
  unit?: string;
  category: FindingCategory;
  evidence_ids: string[];
  uncertainty?: string;
  verification_status: VerificationStatus;
}

export type EventType =
  | 'investigation_started'
  | 'agent_started'
  | 'tool_completed'
  | 'evidence_added'
  | 'agent_completed'
  | 'verification_failed'
  | 'verification_passed'
  | 'investigation_completed';

export interface ExecutionEvent {
  id: string;
  investigation_id: string;
  event_type: EventType;
  agent_id?: string;
  timestamp: string;
  details: Record<string, any>;
}

export interface InvestigationCreateRequest {
  workspace: WorkspaceType;
  prompt: string;
  latitude?: number;
  longitude?: number;
  target_time?: string;
  parameters?: Record<string, any>;
}

export interface InvestigationResponse {
  id: string;
  workspace: WorkspaceType;
  prompt: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  latitude?: number;
  longitude?: number;
  target_time?: string;
  final_answer?: string;
  findings: Finding[];
  limitations: string[];
  created_at: string;
  completed_at?: string;
}

export interface InvestigationReportResponse {
  investigation_id: string;
  workspace: WorkspaceType;
  title: string;
  summary: string;
  findings: Finding[];
  evidence: EvidenceRecord[];
  verification_summary: Record<string, any>;
  limitations: string[];
  generated_at: string;
}

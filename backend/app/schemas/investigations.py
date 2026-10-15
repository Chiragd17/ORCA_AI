from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.evidence import Finding, EvidenceRecord

class WorkspaceType(str, Enum):
    FISHERMAN = "fisherman"
    MARINE_MONITORING = "marine_monitoring"
    PROTECTED_AREAS = "protected_areas"
    COASTAL_AUTHORITY = "coastal_authority"
    DISASTER_MANAGEMENT = "disaster_management"

class InvestigationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class EventType(str, Enum):
    INVESTIGATION_STARTED = "investigation_started"
    AGENT_STARTED = "agent_started"
    TOOL_COMPLETED = "tool_completed"
    EVIDENCE_ADDED = "evidence_added"
    AGENT_COMPLETED = "agent_completed"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_PASSED = "verification_passed"
    INVESTIGATION_COMPLETED = "investigation_completed"

class InvestigationCreateRequest(BaseModel):
    workspace: WorkspaceType
    prompt: str = Field(..., min_length=3, description="User's investigation query")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    target_time: Optional[datetime] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

class ExecutionEvent(BaseModel):
    id: str
    investigation_id: str
    event_type: EventType
    agent_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = Field(default_factory=dict)

class InvestigationResponse(BaseModel):
    id: str
    workspace: WorkspaceType
    prompt: str
    status: InvestigationStatus
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    target_time: Optional[datetime] = None
    final_answer: Optional[str] = None
    findings: List[Finding] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None

class InvestigationReportResponse(BaseModel):
    investigation_id: str
    workspace: WorkspaceType
    title: str
    summary: str
    findings: List[Finding]
    evidence: List[EvidenceRecord]
    verification_summary: Dict[str, Any]
    limitations: List[str]
    generated_at: datetime

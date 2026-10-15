from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.evidence import EvidenceRecord, Finding
from app.schemas.investigations import WorkspaceType

class AgentStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"

class InvestigationTask(BaseModel):
    investigation_id: str
    workspace: WorkspaceType
    prompt: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    target_time: Optional[datetime] = None
    context: Dict[str, Any] = Field(default_factory=dict)

class AgentResult(BaseModel):
    agent_id: str
    status: AgentStatus
    findings: List[Finding] = Field(default_factory=list)
    evidence: List[EvidenceRecord] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

class BaseAgent(ABC):
    """
    Mandatory abstract base class for all specialist agents.
    Every agent (Ocean Research, Marine Hazard, Coastal Risk, Evidence Verification)
    must inherit from BaseAgent and implement the async run() method.
    """
    agent_id: str
    name: str
    description: str

    @abstractmethod
    async def run(self, task: InvestigationTask) -> AgentResult:
        """
        Executes the agent's deterministic analysis and evidence collection for the given task.
        Must return an AgentResult complying with the shared schema.
        """
        pass

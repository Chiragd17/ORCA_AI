import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.schemas.investigations import (
    InvestigationCreateRequest,
    InvestigationResponse,
    InvestigationStatus,
    EventType,
)
from app.schemas.evidence import Finding, EvidenceRecord
from app.agents.base import BaseAgent, InvestigationTask, AgentStatus
from app.agents.ocean_research.agent import OceanResearchAgent
from app.agents.marine_hazard.agent import MarineHazardAgent
from app.agents.coastal_risk.agent import CoastalRiskAgent
from app.agents.evidence_verification.agent import EvidenceVerificationAgent
from app.orchestrator.planner import OrchestrationPlanner
from app.orchestrator.events import EventBus
from app.evidence.registry import EvidenceRegistry
from app.evidence.verification import verify_findings

class OrchestratorService:
    """
    Coordinates multi-agent investigations, executing specialist agents,
    collecting evidence, emitting execution events, and orchestrating verification.
    """
    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {
            "ocean_research": OceanResearchAgent(),
            "marine_hazard": MarineHazardAgent(),
            "coastal_risk": CoastalRiskAgent(),
            "evidence_verification": EvidenceVerificationAgent(),
        }
        # In-memory session store (can also sync with PostgreSQL)
        self._investigations: Dict[str, InvestigationResponse] = {}
        self._event_buses: Dict[str, EventBus] = {}
        self._evidence_registries: Dict[str, EvidenceRegistry] = {}

    def get_event_bus(self, investigation_id: str) -> EventBus:
        if investigation_id not in self._event_buses:
            self._event_buses[investigation_id] = EventBus(investigation_id)
        return self._event_buses[investigation_id]

    def get_evidence_registry(self, investigation_id: str) -> EvidenceRegistry:
        if investigation_id not in self._evidence_registries:
            self._evidence_registries[investigation_id] = EvidenceRegistry()
        return self._evidence_registries[investigation_id]

    async def execute_investigation(
        self, request: InvestigationCreateRequest, investigation_id: Optional[str] = None
    ) -> InvestigationResponse:
        inv_id = investigation_id or f"inv-{uuid.uuid4().hex[:12]}"
        event_bus = self.get_event_bus(inv_id)
        evidence_reg = self.get_evidence_registry(inv_id)

        # 1. Start investigation
        event_bus.emit(
            EventType.INVESTIGATION_STARTED,
            details={"workspace": request.workspace, "prompt": request.prompt},
        )

        # 2. Plan agent sequence
        agent_ids = OrchestrationPlanner.select_agents(request)
        event_bus.emit(
            EventType.TOOL_COMPLETED,
            details={"tool": "planner", "selected_agents": agent_ids},
        )

        task = InvestigationTask(
            investigation_id=inv_id,
            workspace=request.workspace,
            prompt=request.prompt,
            latitude=request.latitude,
            longitude=request.longitude,
            target_time=request.target_time,
            context=request.parameters,
        )

        all_findings: List[Finding] = []
        all_limitations: List[str] = []

        # 3. Execute specialist agents
        for aid in agent_ids:
            agent = self._agents.get(aid)
            if not agent:
                continue

            event_bus.emit(EventType.AGENT_STARTED, agent_id=aid)

            try:
                res = await agent.run(task)
                if res.evidence:
                    evidence_reg.register_many(res.evidence)
                    event_bus.emit(
                        EventType.EVIDENCE_ADDED,
                        agent_id=aid,
                        details={"count": len(res.evidence)},
                    )

                all_findings.extend(res.findings)
                all_limitations.extend(res.limitations)

                event_bus.emit(
                    EventType.AGENT_COMPLETED,
                    agent_id=aid,
                    details={"status": res.status, "findings_count": len(res.findings)},
                )
            except Exception as e:
                all_limitations.append(f"Agent {aid} encountered an execution error: {str(e)}")
                event_bus.emit(
                    EventType.AGENT_COMPLETED,
                    agent_id=aid,
                    details={"status": AgentStatus.FAILED, "error": str(e)},
                )

        # 4. Perform deterministic evidence verification
        v_summary = verify_findings(all_findings, evidence_reg)
        if v_summary["unverified"] > 0 or v_summary["insufficient_evidence"] > 0:
            event_bus.emit(EventType.VERIFICATION_FAILED, details=v_summary)
        else:
            event_bus.emit(EventType.VERIFICATION_PASSED, details=v_summary)

        # 5. Conclude investigation
        event_bus.emit(
            EventType.INVESTIGATION_COMPLETED,
            details={"total_findings": len(all_findings), "total_evidence": len(evidence_reg.list_all())},
        )

        response = InvestigationResponse(
            id=inv_id,
            workspace=request.workspace,
            prompt=request.prompt,
            status=InvestigationStatus.COMPLETED,
            latitude=request.latitude,
            longitude=request.longitude,
            target_time=request.target_time,
            final_answer=f"Completed investigation for workspace '{request.workspace.value}'. Collected {len(all_findings)} finding(s) backed by {len(evidence_reg.list_all())} evidence record(s).",
            findings=all_findings,
            limitations=list(set(all_limitations)),
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )

        self._investigations[inv_id] = response
        return response

    def get_investigation(self, investigation_id: str) -> Optional[InvestigationResponse]:
        return self._investigations.get(investigation_id)

orchestrator_service = OrchestratorService()

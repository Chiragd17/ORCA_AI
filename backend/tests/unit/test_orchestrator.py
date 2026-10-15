import pytest
from app.schemas.investigations import (
    InvestigationCreateRequest,
    WorkspaceType,
    InvestigationStatus,
    EventType,
)
from app.orchestrator.service import OrchestratorService
from app.orchestrator.planner import OrchestrationPlanner

def test_planner_agent_selection():
    req_fisherman = InvestigationCreateRequest(
        workspace=WorkspaceType.FISHERMAN,
        prompt="Wave height check",
    )
    agents = OrchestrationPlanner.select_agents(req_fisherman)
    assert "ocean_research" in agents
    assert "evidence_verification" in agents

    req_disaster = InvestigationCreateRequest(
        workspace=WorkspaceType.DISASTER_MANAGEMENT,
        prompt="Cyclone track alert Arabian Sea",
    )
    agents_dm = OrchestrationPlanner.select_agents(req_disaster)
    assert "marine_hazard" in agents_dm
    assert "coastal_risk" in agents_dm

@pytest.mark.asyncio
async def test_orchestrator_execution_flow():
    service = OrchestratorService()
    req = InvestigationCreateRequest(
        workspace=WorkspaceType.FISHERMAN,
        prompt="Mangaluru wind speed inquiry",
        latitude=12.87,
        longitude=74.88,
    )
    res = await service.execute_investigation(req)
    assert res.status == InvestigationStatus.COMPLETED
    assert res.workspace == WorkspaceType.FISHERMAN

    events = service.get_event_bus(res.id).get_events()
    event_types = [e.event_type for e in events]
    assert EventType.INVESTIGATION_STARTED in event_types
    assert EventType.INVESTIGATION_COMPLETED in event_types

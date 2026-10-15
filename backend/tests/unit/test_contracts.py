import pytest

from app.agents.base import AgentResult, AgentStatus, BaseAgent, InvestigationTask
from app.agents.coastal_risk.agent import CoastalRiskAgent
from app.agents.evidence_verification.agent import EvidenceVerificationAgent
from app.agents.marine_hazard.agent import MarineHazardAgent
from app.agents.ocean_research.agent import OceanResearchAgent
from app.schemas.investigations import WorkspaceType


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_cls, expected_id", [
    (OceanResearchAgent, "ocean_research"),
    (MarineHazardAgent, "marine_hazard"),
    (CoastalRiskAgent, "coastal_risk"),
    (EvidenceVerificationAgent, "evidence_verification"),
])
async def test_agent_contract_conformance(agent_cls, expected_id):
    agent = agent_cls()
    assert isinstance(agent, BaseAgent)
    assert agent.agent_id == expected_id

    task = InvestigationTask(
        investigation_id="test-task-1",
        workspace=WorkspaceType.FISHERMAN,
        prompt="Test inquiry for agent contract validation",
    )

    result = await agent.run(task)
    assert isinstance(result, AgentResult)
    assert result.agent_id == expected_id
    assert result.status in [AgentStatus.COMPLETED, AgentStatus.PARTIAL, AgentStatus.UNAVAILABLE, AgentStatus.FAILED]
    assert isinstance(result.findings, list)
    assert isinstance(result.evidence, list)
    assert isinstance(result.limitations, list)
    assert isinstance(result.errors, list)

from typing import List
from app.schemas.investigations import WorkspaceType, InvestigationCreateRequest

class OrchestrationPlanner:
    """
    Determines which specialist agents to invoke based on workspace context and user inquiry.
    Deterministic agent selection ensures efficient, relevant execution.
    """
    @staticmethod
    def select_agents(request: InvestigationCreateRequest) -> List[str]:
        agents: List[str] = []

        workspace = request.workspace
        prompt_lower = request.prompt.lower()

        # Workspace-driven agent defaults
        if workspace == WorkspaceType.FISHERMAN:
            agents.append("ocean_research")
            if any(k in prompt_lower for k in ["cyclone", "storm", "warning", "hazard", "gale"]):
                agents.append("marine_hazard")
        elif workspace == WorkspaceType.MARINE_MONITORING:
            agents.append("ocean_research")
            if any(k in prompt_lower for k in ["protected", "sanctuary", "coral"]):
                agents.append("coastal_risk")
        elif workspace == WorkspaceType.PROTECTED_AREAS:
            agents.append("coastal_risk")
            agents.append("ocean_research")
        elif workspace == WorkspaceType.COASTAL_AUTHORITY:
            agents.append("coastal_risk")
            if any(k in prompt_lower for k in ["storm", "cyclone", "surge", "flood"]):
                agents.append("marine_hazard")
        elif workspace == WorkspaceType.DISASTER_MANAGEMENT:
            agents.append("marine_hazard")
            agents.append("coastal_risk")
            if any(k in prompt_lower for k in ["wave", "sst", "wind", "marine"]):
                agents.append("ocean_research")
        else:
            agents.append("ocean_research")

        # Deduplicate preserving order
        selected = list(dict.fromkeys(agents))

        # Always include verification agent as the final audit step
        selected.append("evidence_verification")
        return selected

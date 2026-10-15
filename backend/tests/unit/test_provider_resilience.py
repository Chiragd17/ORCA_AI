import json
import pytest
from unittest.mock import patch, AsyncMock
import httpx

from app.providers.data.open_meteo import OpenMeteoMarineClient
from app.agents.ocean_research.agent import OceanResearchAgent
from app.agents.base import InvestigationTask, AgentStatus
from app.schemas.investigations import WorkspaceType
from app.schemas.evidence import FindingCategory

# -----------------------------------------------------------------------------
# 1. Open-Meteo Provider HTTP Error and Exception Handling
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_provider_connection_error_fallback():
    """Simulates complete network disconnection (ConnectError)."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused by remote host")):
        client = OpenMeteoMarineClient()
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        # Must fall back to labelled scientific baseline fixture
        assert len(obs) > 0
        assert len(evs) == 1
        assert evs[0].metadata.get("is_fixture") is True
        assert any("Live provider query error" in lim for lim in limits)
        assert any("scientific baseline fixture" in lim for lim in limits)

@pytest.mark.asyncio
async def test_provider_timeout_fallback():
    """Simulates provider request timeout."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Read timed out after 12.0s")):
        client = OpenMeteoMarineClient()
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        assert len(obs) > 0
        assert evs[0].metadata.get("is_fixture") is True
        assert any("timed out" in lim for lim in limits)

@pytest.mark.asyncio
async def test_provider_http_500_server_error():
    """Simulates HTTP 500 Internal Server Error from Open-Meteo."""
    mock_resp = httpx.Response(status_code=500, request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        client = OpenMeteoMarineClient()
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        assert len(obs) > 0
        assert evs[0].metadata.get("is_fixture") is True
        assert any("500" in lim for lim in limits)

@pytest.mark.asyncio
async def test_provider_http_429_rate_limit():
    """Simulates HTTP 429 Too Many Requests response."""
    mock_resp = httpx.Response(
        status_code=429,
        text="Rate limit exceeded",
        request=httpx.Request("GET", "https://test.local"),
    )
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        client = OpenMeteoMarineClient()
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        assert len(obs) > 0
        assert evs[0].metadata.get("is_fixture") is True
        assert any("429" in lim for lim in limits)

@pytest.mark.asyncio
async def test_provider_malformed_json_payload():
    """Simulates provider returning unexpected schema without hourly payload."""
    mock_resp = httpx.Response(
        status_code=200,
        text=json.dumps({"error": True, "reason": "Malformed internal database response"}),
        request=httpx.Request("GET", "https://test.local"),
    )
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        client = OpenMeteoMarineClient()
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        # When hourly is missing, returns empty observations gracefully (no unhandled crash)
        assert len(obs) == 0

# -----------------------------------------------------------------------------
# 2. Historical Analysis Continuity During Live Provider Failure
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_historical_analysis_continuity_during_provider_outage():
    """
    Proves that when the live provider is down (HTTP 503),
    the agent still conducts valid historical analysis, period comparisons,
    and anomaly detection using persisted/archived records.
    Historical records must NEVER be mislabelled as live observations.
    """
    mock_resp = httpx.Response(status_code=503, request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent()
        task = InvestigationTask(
            investigation_id="task-outage-continuity-01",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Compare historical Southwest Monsoon sea state with Post-Monsoon wave baseline and check for thermal anomalies",
            latitude=12.87,
            longitude=74.88,
        )
        result = await agent.run(task)

        # Historical analysis must succeed despite live provider failure
        assert result.status == AgentStatus.COMPLETED
        assert len(result.findings) >= 2

        # Verify no historical records are mislabelled as live observations
        hist_categories = {f.category for f in result.findings if "Karnataka Coast" in f.claim or "Monsoon" in f.claim}
        assert FindingCategory.OBSERVATION not in hist_categories
        assert FindingCategory.HISTORICAL_RECORD in hist_categories or FindingCategory.DETERMINISTIC_CALCULATION in hist_categories

@pytest.mark.asyncio
async def test_zero_data_returns_unavailable_without_fabrication():
    """
    Proves that when both live and historical sources return zero records,
    the agent returns UNAVAILABLE without fabricating false measurements.
    """
    mock_client = AsyncMock()
    mock_client.fetch_marine_data.return_value = ([], [], ["Live provider returned empty feed."])

    mock_loader = AsyncMock()
    mock_loader.load_local_dataset.return_value = ([], AsyncMock(id="ev-empty"), {"processed": 0, "valid": 0, "rejected": 0})

    agent = OceanResearchAgent(live_client=mock_client, historical_loader=mock_loader)
    task = InvestigationTask(
        investigation_id="task-empty-feed",
        workspace=WorkspaceType.MARINE_MONITORING,
        prompt="Retrieve sea state for an unmonitored offshore oceanic void",
        latitude=0.0,
        longitude=0.0,
    )

    result = await agent.run(task)
    # Must report UNAVAILABLE or zero findings; never fabricate observations
    assert len(result.findings) == 0
    assert result.status in (AgentStatus.UNAVAILABLE, AgentStatus.FAILED, AgentStatus.PARTIAL)

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.agents.base import AgentStatus, InvestigationTask
from app.agents.ocean_research.agent import OceanResearchAgent
from app.providers.data.open_meteo import OpenMeteoMarineClient
from app.schemas.evidence import FindingCategory
from app.schemas.investigations import WorkspaceType

# -----------------------------------------------------------------------------
# 1. Open-Meteo Provider HTTP Error and Exception Handling
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_provider_connection_error_normal_mode_discloses_failure():
    """In normal mode, network disconnection returns empty observations and discloses error without fabricating fixtures."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused by remote host")):
        client = OpenMeteoMarineClient(demo_mode=False)
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        # Normal mode must NOT fall back to fixtures masquerading as live data
        assert len(obs) == 0
        assert len(evs) == 0
        assert any("Live marine provider unavailable" in lim for lim in limits)


@pytest.mark.asyncio
async def test_provider_error_demo_mode_returns_explicit_demo_fixture():
    """In explicit demo mode, provider failure loads labelled fixture clearly marked as DEMO DATA."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused by remote host")):
        client = OpenMeteoMarineClient(demo_mode=True)
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        # In demo mode, sample fixture is returned with explicit demo labels
        assert len(obs) > 0
        assert len(evs) == 1
        assert evs[0].metadata.get("is_fixture") is True
        assert evs[0].metadata.get("is_demo") is True
        assert "DEMO DATA" in evs[0].source_name
        assert any("DEMO DATA" in lim for lim in limits)


@pytest.mark.asyncio
async def test_provider_timeout_normal_mode():
    """Simulates provider request timeout in normal mode."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Read timed out after 12.0s")):
        client = OpenMeteoMarineClient(demo_mode=False)
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        assert len(obs) == 0
        assert len(evs) == 0
        assert any("Live marine provider unavailable" in lim for lim in limits)


@pytest.mark.asyncio
async def test_provider_http_500_server_error_normal_mode():
    """Simulates HTTP 500 Internal Server Error from Open-Meteo in normal mode."""
    mock_resp = httpx.Response(status_code=500, request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        client = OpenMeteoMarineClient(demo_mode=False)
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        assert len(obs) == 0
        assert len(evs) == 0
        assert any("Live marine provider unavailable" in lim for lim in limits)


@pytest.mark.asyncio
async def test_provider_http_429_rate_limit_normal_mode():
    """Simulates HTTP 429 Too Many Requests response in normal mode."""
    mock_resp = httpx.Response(
        status_code=429,
        text="Rate limit exceeded",
        request=httpx.Request("GET", "https://test.local"),
    )
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        client = OpenMeteoMarineClient(demo_mode=False)
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        assert len(obs) == 0
        assert len(evs) == 0
        assert any("Live marine provider unavailable" in lim for lim in limits)


@pytest.mark.asyncio
async def test_provider_malformed_json_payload():
    """Simulates provider returning unexpected schema without hourly payload."""
    mock_resp = httpx.Response(
        status_code=200,
        text=json.dumps({"error": True, "reason": "Malformed internal database response"}),
        request=httpx.Request("GET", "https://test.local"),
    )
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        client = OpenMeteoMarineClient(demo_mode=False)
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
    and returns status=PARTIAL (never false COMPLETED).
    Historical records must NEVER be mislabelled as live observations.
    """
    mock_resp = httpx.Response(status_code=503, request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent(demo_mode=True)
        task = InvestigationTask(
            investigation_id="task-outage-continuity-01",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Compare historical Southwest Monsoon sea state with Post-Monsoon wave baseline",
            latitude=12.87,
            longitude=74.88,
        )
        result = await agent.run(task)

        # Historical analysis succeeds, but overall status is PARTIAL because live provider failed
        assert result.status == AgentStatus.PARTIAL
        assert len(result.findings) >= 2

        # Verify no historical records are mislabelled as live observations
        hist_categories = {f.category for f in result.findings if "Karnataka Coast" in f.claim or "Monsoon" in f.claim}
        assert FindingCategory.OBSERVATION not in hist_categories
        assert FindingCategory.HISTORICAL_RECORD in hist_categories or FindingCategory.DETERMINISTIC_CALCULATION in hist_categories
        assert any("Live marine provider unavailable" in lim for lim in result.limitations)


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
    # Must report UNAVAILABLE; never fabricate observations or false COMPLETED status
    assert len(result.findings) == 0
    assert result.status == AgentStatus.UNAVAILABLE

import pytest
from datetime import datetime, timezone
from app.agents.ocean_research.calculations import (
    compute_series_stats,
    get_indian_ocean_season,
    compute_seasonal_breakdown,
    compare_time_periods,
    detect_anomalies,
)
from app.providers.data.open_meteo import OpenMeteoMarineClient
from app.providers.data.historical_marine import HistoricalMarineDataLoader
from app.agents.ocean_research.agent import OceanResearchAgent
from app.agents.base import InvestigationTask, AgentStatus
from app.schemas.investigations import WorkspaceType
from app.schemas.evidence import VerificationStatus, FindingCategory

# -----------------------------------------------------------------------------
# 1. Deterministic Calculation Tests
# -----------------------------------------------------------------------------

def test_compute_series_stats_deterministic():
    data = [10.0, 12.0, 14.0, 16.0]
    stats = compute_series_stats(data)
    assert stats["count"] == 4
    assert stats["min"] == 10.0
    assert stats["max"] == 16.0
    assert stats["mean"] == 13.0
    assert stats["std_dev"] == 2.58

def test_compute_series_stats_empty():
    stats = compute_series_stats([])
    assert stats["count"] == 0
    assert stats["mean"] is None

def test_indian_ocean_seasons():
    assert get_indian_ocean_season(datetime(2026, 7, 15)) == "Southwest Monsoon"
    assert get_indian_ocean_season(datetime(2026, 11, 1)) == "Post-Monsoon"
    assert get_indian_ocean_season(datetime(2026, 1, 10)) == "Winter"
    assert get_indian_ocean_season(datetime(2026, 4, 20)) == "Pre-Monsoon"

def test_seasonal_breakdown():
    dates = [
        datetime(2026, 7, 1),
        datetime(2026, 7, 15),
        datetime(2026, 11, 5),
    ]
    vals = [2.5, 3.5, 1.2]
    res = compute_seasonal_breakdown(dates, vals)
    assert res["Southwest Monsoon"]["count"] == 2
    assert res["Southwest Monsoon"]["mean"] == 3.0
    assert res["Post-Monsoon"]["count"] == 1
    assert res["Post-Monsoon"]["mean"] == 1.2
    assert res["Winter"]["count"] == 0

def test_compare_time_periods():
    p1 = [1.0, 1.2, 1.4]  # mean = 1.2
    p2 = [1.8, 2.0, 2.2]  # mean = 2.0
    comp = compare_time_periods(p1, p2, "wave_height", "m")
    assert comp["valid_comparison"] is True
    assert comp["mean_difference"] == 0.8
    assert comp["percentage_change"] == pytest.approx(66.67, 0.1)

def test_anomaly_detection_insufficient_baseline():
    vals = [32.0, 33.0]
    baseline_small = [28.0] * 5  # < 10 samples
    res = detect_anomalies(vals, baseline_small, min_baseline_samples=10)
    assert res["eligible"] is False
    assert "Insufficient baseline" in res["limitation"]

def test_anomaly_detection_threshold():
    baseline = [28.0, 28.2, 28.1, 28.3, 28.0, 28.2, 28.1, 28.0, 28.2, 28.1]
    vals = [28.1, 28.2, 31.5]  # 31.5 is way above 2-sigma
    res = detect_anomalies(vals, baseline, threshold_sigma=2.0, min_baseline_samples=10)
    assert res["eligible"] is True
    assert res["anomaly_detected"] is True
    assert 31.5 in res["anomalous_values"]

# -----------------------------------------------------------------------------
# 2. Historical Data Loader Tests
# -----------------------------------------------------------------------------

def test_historical_marine_loader():
    loader = HistoricalMarineDataLoader()
    records, evidence, counts = loader.load_local_dataset()
    assert counts["processed"] >= 15
    assert counts["valid"] >= 15
    assert counts["rejected"] == 0
    assert evidence.data_type == "historical_oceanographic_series"
    assert evidence.metadata["is_historical"] is True

    # Validate physical bounds on loaded records
    for r in records:
        assert 20.0 <= r["sea_surface_temperature_celsius"] <= 35.0
        assert 0.0 <= r["wave_height_meters"] <= 10.0

# -----------------------------------------------------------------------------
# 3. Open-Meteo Client & Fixture Fallback Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_meteo_client_invalid_coordinates():
    client = OpenMeteoMarineClient()
    obs, evs, limits = await client.fetch_marine_data(latitude=120.0, longitude=50.0)
    assert len(obs) == 0
    assert any("Invalid coordinate bounds" in l for l in limits)

@pytest.mark.asyncio
async def test_open_meteo_client_fallback_to_fixture():
    client = OpenMeteoMarineClient(base_url="http://invalid-nonexistent-domain.test/marine")
    obs, evs, limits = await client.fetch_marine_data(latitude=12.87, longitude=74.88)
    assert len(obs) > 0
    assert len(evs) == 1
    assert evs[0].metadata.get("is_fixture") is True

# -----------------------------------------------------------------------------
# 4. Ocean Research Agent Full Execution Tests (Historical & Live)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ocean_research_agent_live_inquiry():
    agent = OceanResearchAgent()
    task = InvestigationTask(
        investigation_id="task-live-01",
        workspace=WorkspaceType.FISHERMAN,
        prompt="Check wave conditions offshore Mangaluru tomorrow",
        latitude=12.87,
        longitude=74.88,
    )
    result = await agent.run(task)
    assert result.agent_id == "ocean_research"
    assert result.status == AgentStatus.COMPLETED
    assert len(result.findings) > 0
    assert any(f.category == FindingCategory.OBSERVATION for f in result.findings)

@pytest.mark.asyncio
async def test_ocean_research_agent_historical_comparison():
    agent = OceanResearchAgent()
    task = InvestigationTask(
        investigation_id="task-hist-01",
        workspace=WorkspaceType.MARINE_MONITORING,
        prompt="Compare historical Southwest Monsoon sea state with Post-Monsoon wave baseline and check for thermal anomalies",
        latitude=12.87,
        longitude=74.88,
    )
    result = await agent.run(task)
    assert result.agent_id == "ocean_research"
    assert result.status == AgentStatus.COMPLETED
    
    # Must contain historical findings
    hist_findings = [f for f in result.findings if f.category in (FindingCategory.HISTORICAL_RECORD, FindingCategory.DETERMINISTIC_CALCULATION)]
    assert len(hist_findings) >= 2

    # Check comparison finding
    comp_claims = [f.claim for f in result.findings if "Southwest Monsoon" in f.claim]
    assert len(comp_claims) > 0

@pytest.mark.asyncio
async def test_ocean_research_agent_limitations():
    agent = OceanResearchAgent()
    task = InvestigationTask(
        investigation_id="task-limits-01",
        workspace=WorkspaceType.MARINE_MONITORING,
        prompt="Assess chlorophyll concentration and ocean color across 5 years",
        latitude=14.80,
        longitude=74.12,
    )
    result = await agent.run(task)
    assert any("Chlorophyll" in lim for lim in result.limitations)
    assert any("5+ year" in lim or "5-year" in lim for lim in result.limitations)

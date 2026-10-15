from datetime import UTC, datetime

import pytest

from app.agents.base import AgentStatus, InvestigationTask
from app.agents.ocean_research.agent import OceanResearchAgent
from app.agents.ocean_research.calculations import (
    compare_locations,
    compare_time_periods,
    compute_seasonal_breakdown,
    compute_series_stats,
    detect_anomalies,
    filter_and_clean_observations,
    get_indian_ocean_season,
    validate_geographic_coordinates,
    validate_unit_compatibility,
)
from app.agents.ocean_research.queries import (
    MarineResearchQueryService,
)
from app.providers.data.historical_marine import HistoricalMarineDataLoader
from app.providers.data.open_meteo import OpenMeteoMarineClient
from app.providers.llm.base import BaseLLMProvider
from app.schemas.evidence import FindingCategory, VerificationStatus
from app.schemas.investigations import WorkspaceType

# -----------------------------------------------------------------------------
# 1. Query Parameter & Variable Validation Tests
# -----------------------------------------------------------------------------

def test_query_coordinate_validation():
    # Valid coordinates
    ok, err = validate_geographic_coordinates(12.87, 74.88)
    assert ok is True
    assert err is None

    # Latitude out of bounds
    ok, err = validate_geographic_coordinates(95.0, 74.88)
    assert ok is False
    assert "Latitude 95.0 out of bounds" in err

    # Longitude out of bounds
    ok, err = validate_geographic_coordinates(12.87, -190.0)
    assert ok is False
    assert "Longitude -190.0 out of bounds" in err

    # None coordinates
    ok, err = validate_geographic_coordinates(None, 74.88)
    assert ok is False
    assert "Missing coordinate" in err

    # NaN coordinates
    ok, err = validate_geographic_coordinates(float("nan"), 74.88)
    assert ok is False
    assert "cannot be NaN" in err

def test_query_service_parameters():
    service = MarineResearchQueryService()

    # Valid parameters
    t_start = datetime(2025, 6, 1, tzinfo=UTC)
    t_end = datetime(2025, 9, 30, tzinfo=UTC)
    ok, errs = service.validate_query_parameters(
        latitude=12.87,
        longitude=74.88,
        start_time=t_start,
        end_time=t_end,
        variables=["sea_surface_temperature_celsius", "wave_height_meters"],
        radius_km=50.0,
    )
    assert ok is True
    assert len(errs) == 0

    # Inverted time range
    ok, errs = service.validate_query_parameters(
        latitude=12.87,
        longitude=74.88,
        start_time=t_end,
        end_time=t_start,
    )
    assert ok is False
    assert any("Invalid temporal range" in e for e in errs)

    # Unsupported variable
    ok, errs = service.validate_query_parameters(
        latitude=12.87,
        longitude=74.88,
        variables=["salinity_psu", "turbidity_ntu"],
    )
    assert ok is False
    assert any("Unsupported marine variable" in e for e in errs)

# -----------------------------------------------------------------------------
# 2. Time-Series Summaries, Median, and Gap Detection
# -----------------------------------------------------------------------------

def test_compute_series_stats_deterministic():
    # Odd count: median is exact midpoint
    data_odd = [10.0, 12.0, 14.0, 16.0, 18.0]
    stats_odd = compute_series_stats(data_odd)
    assert stats_odd["count"] == 5
    assert stats_odd["min"] == 10.0
    assert stats_odd["max"] == 18.0
    assert stats_odd["mean"] == 14.0
    assert stats_odd["median"] == 14.0
    assert stats_odd["std_dev"] == pytest.approx(3.16, 0.01)

    # Even count: median is average of two midpoints
    data_even = [10.0, 12.0, 14.0, 16.0]
    stats_even = compute_series_stats(data_even)
    assert stats_even["count"] == 4
    assert stats_even["median"] == 13.0

def test_compute_series_stats_never_treats_missing_as_zero():
    # Missing / None / NaN values should not skew mean towards 0
    data_with_missing = [10.0, None, float("nan"), 20.0]
    stats = compute_series_stats(data_with_missing)
    assert stats["count"] == 2
    assert stats["mean"] == 15.0  # (10 + 20) / 2 = 15.0, NOT (10 + 0 + 0 + 20) / 4 = 7.5
    assert stats["median"] == 15.0
    assert stats["min"] == 10.0

def test_compute_series_stats_temporal_coverage_and_gaps():
    times = [
        datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
        datetime(2026, 6, 1, 6, 0, tzinfo=UTC),   # 6h gap (normal)
        datetime(2026, 6, 2, 12, 0, tzinfo=UTC),  # 30h gap (> 12h threshold)
        datetime(2026, 6, 2, 18, 0, tzinfo=UTC),  # 6h gap
    ]
    vals = [28.0, 28.2, 28.5, 28.3]
    stats = compute_series_stats(vals, timestamps=times, max_gap_hours=12.0)
    assert stats["count"] == 4
    assert stats["temporal_coverage"] is not None
    assert stats["temporal_coverage"]["duration_hours"] == 42.0
    assert len(stats["sampling_gaps"]) == 1
    assert stats["sampling_gaps"][0]["gap_hours"] == 30.0

def test_compute_series_stats_empty():
    stats = compute_series_stats([])
    assert stats["count"] == 0
    assert stats["mean"] is None
    assert stats["median"] is None
    assert stats["temporal_coverage"] is None
    assert stats["sampling_gaps"] == []

# -----------------------------------------------------------------------------
# 3. Seasonal Summaries & Inadequate Temporal Coverage
# -----------------------------------------------------------------------------

def test_indian_ocean_seasons():
    assert get_indian_ocean_season(datetime(2026, 7, 15)) == "Southwest Monsoon"
    assert get_indian_ocean_season(datetime(2026, 11, 1)) == "Post-Monsoon"
    assert get_indian_ocean_season(datetime(2026, 1, 10)) == "Winter"
    assert get_indian_ocean_season(datetime(2026, 4, 20)) == "Pre-Monsoon"

def test_seasonal_breakdown_adequate_and_inadequate():
    dates = [
        datetime(2026, 7, 1),
        datetime(2026, 7, 15),
        datetime(2026, 11, 5),
    ]
    vals = [2.5, 3.5, 1.2]

    # With minimum required = 2:
    res = compute_seasonal_breakdown(dates, vals, min_observations_per_season=2)
    assert res["Southwest Monsoon"]["count"] == 2
    assert res["Southwest Monsoon"]["mean"] == 3.0
    assert res["Southwest Monsoon"]["is_adequate_coverage"] is True

    # Post-Monsoon has only 1 sample, so coverage is inadequate
    assert res["Post-Monsoon"]["count"] == 1
    assert res["Post-Monsoon"]["is_adequate_coverage"] is False
    assert "Insufficient seasonal coverage" in res["Post-Monsoon"]["limitation"]

    # Winter has 0 samples
    assert res["Winter"]["count"] == 0
    assert res["Winter"]["is_adequate_coverage"] is False

# -----------------------------------------------------------------------------
# 4. Historical Period & Spatial Location Comparisons
# -----------------------------------------------------------------------------

def test_compare_time_periods():
    p1 = [1.0, 1.2, 1.4]  # mean = 1.2, median = 1.2
    p2 = [1.8, 2.0, 2.2]  # mean = 2.0, median = 2.0
    comp = compare_time_periods(p1, p2, "wave_height", "m")
    assert comp["valid_comparison"] is True
    assert comp["mean_difference"] == 0.8
    assert comp["median_difference"] == 0.8
    assert comp["percentage_change"] == pytest.approx(66.67, 0.1)

def test_compare_time_periods_empty_rejected():
    comp = compare_time_periods([], [2.0, 2.5], "wave_height", "m")
    assert comp["valid_comparison"] is False
    assert "Insufficient observations" in comp["reason"]

def test_compare_locations():
    mangaluru_sst = [28.0, 28.2, 28.4]  # mean = 28.2
    karwar_sst = [29.0, 29.2, 29.4]     # mean = 29.2
    comp = compare_locations(
        loc_a_values=mangaluru_sst,
        loc_b_values=karwar_sst,
        loc_a_name="Mangaluru Offshore",
        loc_b_name="Karwar Offshore",
        variable_name="sea_surface_temperature_celsius",
        unit="°C",
    )
    assert comp["valid_comparison"] is True
    assert comp["mean_difference"] == 1.0
    assert comp["location_a"]["stats"]["mean"] == 28.2
    assert comp["location_b"]["stats"]["mean"] == 29.2

# -----------------------------------------------------------------------------
# 5. Anomaly Detection & Baseline Requirements
# -----------------------------------------------------------------------------

def test_anomaly_detection_insufficient_baseline():
    vals = [32.0, 33.0]
    baseline_small = [28.0] * 5  # < 10 samples
    res = detect_anomalies(vals, baseline_small, min_baseline_samples=10)
    assert res["eligible"] is False
    assert "Insufficient baseline" in res["limitation"]

def test_anomaly_detection_zero_std():
    vals = [30.0]
    baseline_flat = [28.0] * 12  # Std dev is zero
    res = detect_anomalies(vals, baseline_flat, min_baseline_samples=10)
    assert res["eligible"] is False
    assert "standard deviation is zero" in res["limitation"]

def test_anomaly_detection_threshold_exceeded():
    baseline = [28.0, 28.2, 28.1, 28.3, 28.0, 28.2, 28.1, 28.0, 28.2, 28.1]
    vals = [28.1, 28.2, 31.5]  # 31.5 exceeds 2.0-sigma
    res = detect_anomalies(vals, baseline, threshold_sigma=2.0, min_baseline_samples=10)
    assert res["eligible"] is True
    assert res["anomaly_detected"] is True
    assert 31.5 in res["anomalous_values"]
    assert res["anomaly_count"] == 1

def test_anomaly_detection_normal_baseline():
    baseline = [28.0, 28.2, 28.1, 28.3, 28.0, 28.2, 28.1, 28.0, 28.2, 28.1]
    vals = [28.1, 28.15]  # Normal values
    res = detect_anomalies(vals, baseline, threshold_sigma=2.0, min_baseline_samples=10)
    assert res["eligible"] is True
    assert res["anomaly_detected"] is False
    assert res["anomaly_count"] == 0

# -----------------------------------------------------------------------------
# 6. Missing, Duplicated, and Invalid Observations Handling
# -----------------------------------------------------------------------------

def test_filter_and_clean_observations():
    t1 = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 6, 1, 6, 0, tzinfo=UTC)

    raw_vals = [
        28.0,
        None,             # Missing
        "bad_data",       # Invalid type
        99.9,             # Out of physical bound for SST (limit: 45°C)
        28.5,             # Valid
        28.5,             # Duplicate timestamp
    ]
    raw_times = [t1, t1, t1, t1, t2, t2]

    cleaned_vals, cleaned_times, issues = filter_and_clean_observations(
        values=raw_vals,
        timestamps=raw_times,
        variable_name="sea_surface_temperature_celsius",
        deduplicate_timestamps=True,
    )

    assert cleaned_vals == [28.0, 28.5]
    assert cleaned_times == [t1, t2]
    assert any("violates physical plausibility" in iss for iss in issues)
    assert any("duplicate timestamp" in iss for iss in issues)

# -----------------------------------------------------------------------------
# 7. Unit Compatibility Validation
# -----------------------------------------------------------------------------

def test_unit_compatibility():
    assert validate_unit_compatibility("°C", "celsius") is True
    assert validate_unit_compatibility("m", "meters") is True
    assert validate_unit_compatibility("knots", "kt") is True
    assert validate_unit_compatibility("°C", "m") is False
    assert validate_unit_compatibility("knots", "°C") is False
    assert validate_unit_compatibility(None, "m") is False

def test_compare_time_periods_incompatible_units():
    res = compare_time_periods([28.0], [2.5], "metric", unit="°C", unit_b="m")
    assert res["valid_comparison"] is False
    assert "Incompatible units" in res["reason"]

# -----------------------------------------------------------------------------
# 8. Deterministic Output for Identical Inputs
# -----------------------------------------------------------------------------

def test_deterministic_output_reproducibility():
    vals = [28.1, 28.4, 28.2, 28.9, 29.1, 28.0, 28.5]
    run_1 = compute_series_stats(vals)
    run_2 = compute_series_stats(vals)
    assert run_1 == run_2

# -----------------------------------------------------------------------------
# 9. Historical Data Loader Integrity
# -----------------------------------------------------------------------------

def test_historical_marine_loader():
    loader = HistoricalMarineDataLoader()
    records, evidence, counts = loader.load_local_dataset()
    assert counts["processed"] >= 15
    assert counts["valid"] >= 15
    assert counts["rejected"] == 0
    assert evidence.data_type == "historical_oceanographic_series"
    assert evidence.metadata["is_historical"] is True

    for r in records:
        assert 20.0 <= r["sea_surface_temperature_celsius"] <= 35.0
        assert 0.0 <= r["wave_height_meters"] <= 10.0

# -----------------------------------------------------------------------------
# 10. Open-Meteo Client & Fixture Fallback
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_meteo_client_invalid_coordinates():
    client = OpenMeteoMarineClient()
    obs, evs, limits = await client.fetch_marine_data(latitude=120.0, longitude=50.0)
    assert len(obs) == 0
    assert any("Invalid coordinate bounds" in lim for lim in limits)

@pytest.mark.asyncio
async def test_open_meteo_client_fallback_to_fixture():
    client = OpenMeteoMarineClient(base_url="http://invalid-nonexistent-domain.test/marine")
    obs, evs, limits = await client.fetch_marine_data(latitude=12.87, longitude=74.88)
    assert len(obs) > 0
    assert len(evs) == 1
    assert evs[0].metadata.get("is_fixture") is True

# -----------------------------------------------------------------------------
# 11. Ocean Research Agent Full Execution & Evidence Integrity
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

    # Verify evidence references
    evidence_ids = {e.id for e in result.evidence}
    for f in result.findings:
        assert f.verification_status == VerificationStatus.UNVERIFIED
        for ref_id in f.evidence_ids:
            assert ref_id in evidence_ids

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

    # Verify median and delta calculation
    comp_claims = [f.claim for f in result.findings if "Southwest Monsoon" in f.claim]
    assert len(comp_claims) > 0

@pytest.mark.asyncio
async def test_ocean_research_agent_spatial_location_comparison():
    agent = OceanResearchAgent()
    task = InvestigationTask(
        investigation_id="task-loc-comp-01",
        workspace=WorkspaceType.MARINE_MONITORING,
        prompt="Compare sea surface temperatures off Mangaluru with Karwar offshore",
        latitude=12.87,
        longitude=74.88,
        context={
            "location_name": "Mangaluru Coastal Zone",
            "compare_latitude": 14.80,
            "compare_longitude": 74.12,
            "compare_location_name": "Karwar Deepwater Station",
        },
    )
    result = await agent.run(task)
    assert result.status == AgentStatus.COMPLETED

    loc_findings = [f for f in result.findings if "Karwar" in f.claim]
    assert len(loc_findings) > 0
    assert loc_findings[0].category == FindingCategory.DETERMINISTIC_CALCULATION

@pytest.mark.asyncio
async def test_ocean_research_agent_limitations():
    agent = OceanResearchAgent()
    task = InvestigationTask(
        investigation_id="task-limits-01",
        workspace=WorkspaceType.MARINE_MONITORING,
        prompt="Assess chlorophyll concentration and salinity across 5 years",
        latitude=14.80,
        longitude=74.12,
    )
    result = await agent.run(task)
    assert any("Chlorophyll" in lim for lim in result.limitations)
    assert any("salinity" in lim for lim in result.limitations)
    assert any("5+ year" in lim or "5-year" in lim for lim in result.limitations)

@pytest.mark.asyncio
async def test_ocean_research_agent_invalid_input_fails_gracefully():
    agent = OceanResearchAgent()
    task = InvestigationTask(
        investigation_id="task-invalid-coords",
        workspace=WorkspaceType.MARINE_MONITORING,
        prompt="Analyze marine observations at invalid coordinates",
        latitude=125.0,  # Invalid latitude > 90
        longitude=74.88,
    )
    result = await agent.run(task)
    assert result.status == AgentStatus.FAILED
    assert len(result.errors) > 0
    assert "Latitude 125.0 out of bounds" in result.errors[0]
    assert len(result.findings) == 0

# -----------------------------------------------------------------------------
# 12. Optional LLM Failure Resilience
# -----------------------------------------------------------------------------

class FailingMockLLMProvider(BaseLLMProvider):
    name = "failing_mock_llm"
    async def generate_text(self, prompt: str, system_instruction: str = None, temperature: float = 0.2) -> str:
        raise RuntimeError("Simulated upstream LLM service outage (503 Service Unavailable)")

@pytest.mark.asyncio
async def test_ocean_research_agent_llm_failure_resilience():
    failing_llm = FailingMockLLMProvider()
    agent = OceanResearchAgent(llm_provider=failing_llm)
    task = InvestigationTask(
        investigation_id="task-llm-fail-01",
        workspace=WorkspaceType.FISHERMAN,
        prompt="Check wave and wind conditions offshore Mangaluru",
        latitude=12.87,
        longitude=74.88,
    )
    result = await agent.run(task)
    # The agent must NOT crash. Deterministic results must be returned!
    assert len(result.findings) > 0
    assert any(f.category == FindingCategory.OBSERVATION for f in result.findings)
    # LLM failure must be disclosed in limitations
    assert any("LLM scientific synthesis unavailable" in lim for lim in result.limitations)

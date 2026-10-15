from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest

from app.agents.base import AgentStatus, InvestigationTask
from app.agents.ocean_research.agent import OceanResearchAgent
from app.agents.ocean_research.calculations import (
    PHYSICAL_BOUNDS,
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
from app.providers.data.open_meteo import OpenMeteoMarineClient, to_utc_datetime
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
    assert comp["direction"] == "higher"

def test_compare_time_periods_signed_direction():
    # Test positive, negative, and zero differences
    higher_comp = compare_time_periods([1.0], [2.0], "wave_height", "m")
    assert higher_comp["mean_difference"] == 1.0
    assert higher_comp["direction"] == "higher"

    lower_comp = compare_time_periods([3.0], [1.5], "wave_height", "m")
    assert lower_comp["mean_difference"] == -1.5
    assert lower_comp["direction"] == "lower"

    identical_comp = compare_time_periods([2.5], [2.5], "wave_height", "m")
    assert identical_comp["mean_difference"] == 0.0
    assert identical_comp["direction"] == "identical"

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

def test_anomaly_detection_rejects_identical_sample_and_baseline():
    # Regression test: anomaly detection cannot evaluate a baseline against itself
    baseline = [28.0, 28.2, 28.1, 28.3, 28.0, 28.2, 28.1, 28.0, 28.2, 28.1]
    res = detect_anomalies(baseline, baseline, threshold_sigma=2.0)
    assert res["eligible"] is False
    assert "evaluation sample cannot be identical to the baseline" in res["limitation"]

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
async def test_open_meteo_client_failure_handling():
    # Normal mode: returns empty observations, no disguised fixture
    client_normal = OpenMeteoMarineClient(base_url="http://invalid-nonexistent-domain.test/marine", demo_mode=False)
    obs, evs, limits = await client_normal.fetch_marine_data(latitude=12.87, longitude=74.88)
    assert len(obs) == 0
    assert len(evs) == 0
    assert any("Live marine provider unavailable" in lim for lim in limits)

    # Demo mode: returns labelled demo fixture
    client_demo = OpenMeteoMarineClient(base_url="http://invalid-nonexistent-domain.test/marine", demo_mode=True)
    obs_d, evs_d, limits_d = await client_demo.fetch_marine_data(latitude=12.87, longitude=74.88)
    assert len(obs_d) > 0
    assert len(evs_d) == 1
    assert evs_d[0].metadata.get("is_fixture") is True
    assert evs_d[0].metadata.get("is_demo") is True


@pytest.mark.asyncio
async def test_open_meteo_client_live_variables_and_currents():
    """
    Verifies that OpenMeteoMarineClient correctly parses sea_surface_temperature,
    wave parameters, and converts ocean_current_velocity from km/h to m/s.
    """
    from unittest.mock import patch

    import httpx

    mock_payload = {
        "latitude": 12.87,
        "longitude": 74.88,
        "hourly": {
            "time": ["2026-10-15T00:00:00Z", "2026-10-15T01:00:00Z"],
            "sea_surface_temperature": [28.6, 28.7],
            "wave_height": [1.5, 1.6],
            "wave_period": [7.0, 7.2],
            "wave_direction": [245.0, 250.0],
            "ocean_current_velocity": [3.6, 7.2],  # 3.6 km/h = 1.0 m/s, 7.2 km/h = 2.0 m/s
            "ocean_current_direction": [180.0, 190.0],
        },
    }

    mock_resp = httpx.Response(200, json=mock_payload, request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        client = OpenMeteoMarineClient()
        obs, evs, limits = await client.fetch_marine_data(12.87, 74.88)

        assert len(obs) == 2
        assert obs[0].sea_surface_temperature_celsius == 28.6
        assert obs[0].wave_height_meters == 1.5
        # Verify velocity conversion from km/h to m/s (3.6 / 3.6 = 1.0)
        assert obs[0].ocean_current_velocity_mps == 1.0
        assert obs[0].ocean_current_direction_degrees == 180.0
        assert obs[1].ocean_current_velocity_mps == 2.0
        # Wind is not provided on marine endpoint
        assert obs[0].wind_speed_knots is None
        assert any("Surface wind variables are not provided" in lim for lim in limits)


@pytest.mark.asyncio
async def test_fetch_archive_from_open_meteo_temperature_semantics():
    """
    Verifies that HistoricalMarineDataLoader.fetch_archive_from_open_meteo()
    disconnects temperature_2m from sea_surface_temperature_celsius (leaving SST as None)
    and reports SST as unavailable.
    """
    from unittest.mock import patch

    import httpx

    mock_payload = {
        "latitude": 12.87,
        "longitude": 74.88,
        "hourly": {
            "time": ["2025-06-01T00:00:00Z", "2025-06-01T01:00:00Z"],
            "temperature_2m": [30.5, 31.0],  # 2-meter air temperature
            "wind_speed_10m": [15.0, 20.0],
            "wind_direction_10m": [220.0, 230.0],
        },
    }

    mock_resp = httpx.Response(200, json=mock_payload, request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        loader = HistoricalMarineDataLoader()
        records, ev, limits = await loader.fetch_archive_from_open_meteo(12.87, 74.88, "2025-06-01", "2025-06-02")

        assert len(records) == 2
        for r in records:
            # SST must NEVER be populated with 2m air temperature!
            assert r["sea_surface_temperature_celsius"] is None
            # Air temperature preserved only in metadata
            assert r["metadata_json"]["temperature_2m_celsius"] is not None

        assert any("NOT sea surface temperature (SST)" in lim for lim in limits)
        assert ev.metadata.get("sea_surface_temperature_available") is False
        assert ev.metadata.get("air_temperature_2m_available") is True

# -----------------------------------------------------------------------------
# 11. Mock Helper for Deterministic Unit Tests
# -----------------------------------------------------------------------------

def make_mock_marine_payload(start_dt: datetime | None = None, hours: int = 48) -> dict:
    """Generates deterministic Open-Meteo marine hourly JSON payload for testing without network."""
    start = start_dt or datetime(2026, 10, 15, 0, 0, tzinfo=UTC)
    times = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ") for i in range(hours)]
    return {
        "latitude": 12.87,
        "longitude": 74.88,
        "generationtime_ms": 0.5,
        "utc_offset_seconds": 0,
        "timezone": "UTC",
        "timezone_abbreviation": "UTC",
        "hourly": {
            "time": times,
            "wave_height": [1.5 + 0.05 * (i % 5) for i in range(hours)],
            "wave_period": [7.0 + 0.1 * (i % 3) for i in range(hours)],
            "wave_direction": [240.0 + (i % 10) for i in range(hours)],
            "sea_surface_temperature": [28.5 + 0.02 * (i % 4) for i in range(hours)],
            "ocean_current_velocity": [3.6 + 0.1 * (i % 5) for i in range(hours)],
            "ocean_current_direction": [180.0 + (i % 10) for i in range(hours)],
        },
    }

# -----------------------------------------------------------------------------
# 12. Ocean Research Agent Full Execution & Evidence Integrity
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ocean_research_agent_live_inquiry():
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
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
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        # 1. In demo mode: sample fixture is loaded and labeled
        agent_demo = OceanResearchAgent(demo_mode=True)
        task_demo = InvestigationTask(
            investigation_id="task-hist-demo",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Compare historical Southwest Monsoon sea state with Post-Monsoon wave baseline and check for thermal anomalies",
            latitude=12.87,
            longitude=74.88,
            context={"demo_mode": True},
        )
        res_demo = await agent_demo.run(task_demo)
        assert res_demo.agent_id == "ocean_research"
        assert len(res_demo.findings) >= 2
        # Verify findings and evidence unmistakably identify fixture
        demo_findings = [f for f in res_demo.findings if "[SAMPLE FIXTURE / DEMO DATA]" in f.claim]
        assert len(demo_findings) > 0
        for f in demo_findings:
            assert "DEMO FIXTURE ONLY" in f.uncertainty
        assert any("SAMPLE FIXTURE / DEMO DATA" in lim for lim in res_demo.limitations)

        # 2. In production mode with unconfigured repository: fixture is NOT substituted
        agent_prod = OceanResearchAgent(demo_mode=False)
        task_prod = InvestigationTask(
            investigation_id="task-hist-prod",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Compare historical Southwest Monsoon sea state with Post-Monsoon wave baseline",
            latitude=12.87,
            longitude=74.88,
        )
        res_prod = await agent_prod.run(task_prod)
        assert not any("[SAMPLE FIXTURE / DEMO DATA]" in f.claim for f in res_prod.findings)
        assert any("Offline sample fixture was not substituted in production mode" in lim for lim in res_prod.limitations)

@pytest.mark.asyncio
async def test_ocean_research_agent_spatial_location_comparison():
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent(demo_mode=True)
        task = InvestigationTask(
            investigation_id="task-loc-comp-01",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Compare sea surface temperatures off Mangaluru with Karwar offshore",
            latitude=12.87,
            longitude=74.88,
            context={
                "demo_mode": True,
                "location_name": "Mangaluru Coastal Zone",
                "compare_latitude": 14.80,
                "compare_longitude": 74.12,
                "compare_location_name": "Karwar Deepwater Station",
            },
        )
        result = await agent.run(task)
        loc_findings = [f for f in result.findings if "Karwar" in f.claim]
        assert len(loc_findings) > 0
        assert loc_findings[0].category == FindingCategory.DETERMINISTIC_CALCULATION

@pytest.mark.asyncio
async def test_ocean_research_agent_limitations():
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
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
# 13. Optional LLM Failure Resilience
# -----------------------------------------------------------------------------

class FailingMockLLMProvider(BaseLLMProvider):
    name = "failing_mock_llm"
    async def generate_text(self, prompt: str, system_instruction: str = None, temperature: float = 0.2) -> str:
        raise RuntimeError("Simulated upstream LLM service outage (503 Service Unavailable)")

@pytest.mark.asyncio
async def test_ocean_research_agent_llm_failure_resilience():
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
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
        assert any(f.category in (FindingCategory.OBSERVATION, FindingCategory.FORECAST) for f in result.findings)
        # LLM failure must be disclosed in limitations
        assert any("LLM scientific synthesis unavailable" in lim for lim in result.limitations)

# -----------------------------------------------------------------------------
# 14. Deterministic Time-Window & Temporal Constraint Regression Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_target_time_past_rejection():
    """Verifies that a target time in the past is explicitly rejected without substituting current forecast."""
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent()
        past_time = datetime.now(UTC) - timedelta(days=10)
        task = InvestigationTask(
            investigation_id="task-target-past",
            workspace=WorkspaceType.FISHERMAN,
            prompt="Analyze marine conditions at past target time",
            latitude=12.87,
            longitude=74.88,
            target_time=past_time,
        )
        result = await agent.run(task)
        assert any("in the past" in lim for lim in result.limitations)
        assert any("current forecast was not substituted" in lim for lim in result.limitations)
        # Forecast findings must not be returned for past target time
        forecast_findings = [f for f in result.findings if f.category == FindingCategory.FORECAST]
        assert len(forecast_findings) == 0

@pytest.mark.asyncio
async def test_target_time_within_coverage_filtering():
    """Verifies that a target time within coverage filters forecast series to the matching hour."""
    now_utc = datetime.now(UTC)
    target_dt = now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=12)
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(start_dt=target_dt - timedelta(hours=12), hours=48), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent()
        task = InvestigationTask(
            investigation_id="task-target-within",
            workspace=WorkspaceType.FISHERMAN,
            prompt="Check wave conditions at specific target hour",
            latitude=12.87,
            longitude=74.88,
            target_time=target_dt,
        )
        result = await agent.run(task)
        assert result.status == AgentStatus.COMPLETED
        # The forecast observation finding should specifically target the requested valid time
        fcst_findings = [f for f in result.findings if f.category == FindingCategory.FORECAST]
        assert len(fcst_findings) > 0
        assert any(target_dt.strftime("%Y-%m-%d %H:00") in f.claim for f in fcst_findings)

@pytest.mark.asyncio
async def test_target_time_out_of_coverage():
    """Verifies that a target time beyond the 7-day forecast horizon returns an explicit limitation."""
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent()
        future_time = datetime.now(UTC) + timedelta(days=20)
        task = InvestigationTask(
            investigation_id="task-target-out-of-cov",
            workspace=WorkspaceType.FISHERMAN,
            prompt="Check sea state 20 days ahead",
            latitude=12.87,
            longitude=74.88,
            target_time=future_time,
        )
        result = await agent.run(task)
        assert any("exceeds the 7-day model forecast horizon" in lim for lim in result.limitations)
        assert len([f for f in result.findings if f.category == FindingCategory.FORECAST]) == 0

@pytest.mark.asyncio
async def test_time_window_one_day_filtering():
    """Verifies that requesting a single target date filters the series to that day rather than all 168 hours."""
    start_dt = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    target_date = (start_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(start_dt=start_dt, hours=72), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent()
        task = InvestigationTask(
            investigation_id="task-target-date",
            workspace=WorkspaceType.FISHERMAN,
            prompt=f"Check sea state for {target_date}",
            latitude=12.87,
            longitude=74.88,
            context={"target_date": target_date},
        )
        result = await agent.run(task)
        assert result.status == AgentStatus.COMPLETED
        fcst_findings = [f for f in result.findings if f.category == FindingCategory.FORECAST]
        assert len(fcst_findings) > 0
        assert any(target_date in f.claim for f in fcst_findings)

# -----------------------------------------------------------------------------
# 15. Timezone-Aware UTC Normalisation Regression Tests
# -----------------------------------------------------------------------------

def test_utc_datetime_normalisation():
    """Verifies robust conversion of various timestamp formats to timezone-aware UTC."""
    # 1. Trailing 'Z'
    dt_z = to_utc_datetime("2026-10-15T12:00:00Z")
    assert dt_z == datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)
    assert dt_z.tzinfo == UTC

    # 2. Explicit positive offset (+05:30 Indian Standard Time)
    dt_ist = to_utc_datetime("2026-10-15T17:30:00+05:30")
    assert dt_ist == datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)
    assert dt_ist.tzinfo == UTC

    # 3. Explicit negative offset (-04:00 EDT)
    dt_edt = to_utc_datetime("2026-10-15T08:00:00-04:00")
    assert dt_edt == datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)

    # 4. Naive string without timezone info
    dt_naive_str = to_utc_datetime("2026-10-15 12:00:00")
    assert dt_naive_str == datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)
    assert dt_naive_str.tzinfo == UTC

    # 5. Naive datetime object
    dt_naive_obj = to_utc_datetime(datetime(2026, 10, 15, 12, 0, 0))
    assert dt_naive_obj.tzinfo == UTC

    # 6. None handling
    assert to_utc_datetime(None) is None

# -----------------------------------------------------------------------------
# 16. Scientific Series Integrity Regression Tests
# -----------------------------------------------------------------------------

def test_spatial_distinct_grid_cells_deduplication():
    """Verifies that spatially distinct grid cells at identical timestamps are preserved."""
    t0 = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    times = [t0, t0, t0]
    coords = [(12.0, 74.0), (12.5, 74.5), (12.0, 74.0)]  # 1st and 2nd are distinct; 3rd is duplicate of 1st
    vals = [28.0, 28.5, 28.0]

    clean_vals, clean_times, issues = filter_and_clean_observations(
        values=vals,
        timestamps=times,
        coordinates=coords,
        variable_name="sea_surface_temperature_celsius",
        deduplicate_timestamps=True,
    )
    # The two spatially distinct coordinates at t0 must BOTH be preserved
    assert len(clean_vals) == 2
    assert clean_vals == [28.0, 28.5]
    assert any("duplicate spatial observation" in iss for iss in issues)

def test_non_finite_values_rejection():
    """Verifies consistent rejection of NaN, +Inf, -Inf across observation cleaning."""
    raw_vals = [28.0, float("nan"), float("inf"), float("-inf"), 29.0]
    times = [datetime(2026, 10, 15, h, 0, tzinfo=UTC) for h in range(5)]

    clean_vals, clean_times, issues = filter_and_clean_observations(
        values=raw_vals,
        timestamps=times,
        variable_name="sea_surface_temperature_celsius",
    )
    assert clean_vals == [28.0, 29.0]
    assert len(clean_times) == 2
    assert any("non-finite observation" in iss for iss in issues)

def test_ocean_current_physical_bounds():
    """Verifies physical bounds validation for ocean current velocity and direction."""
    assert PHYSICAL_BOUNDS["ocean_current_velocity_mps"] == (0.0, 10.0)
    assert PHYSICAL_BOUNDS["ocean_current_direction_degrees"] == (0.0, 360.0)

    # Valid velocity
    c_vals, _, _ = filter_and_clean_observations(
        values=[0.5, 2.5, 15.0],  # 15.0 m/s exceeds physical limit of 10.0 m/s
        variable_name="ocean_current_velocity_mps",
    )
    assert c_vals == [0.5, 2.5]

    # Valid direction
    d_vals, _, _ = filter_and_clean_observations(
        values=[90.0, 270.0, 400.0],  # 400° exceeds 360°
        variable_name="ocean_current_direction_degrees",
    )
    assert d_vals == [90.0, 270.0]

def test_anomaly_detection_distinct_period_identities():
    """
    Verifies that identical numerical values from distinct periods or provenances
    are not falsely rejected as the same baseline.
    """
    baseline_vals = [27.5, 28.0, 28.5, 27.8, 28.2, 28.1, 27.9, 28.3, 28.0, 27.7, 28.4, 28.0]
    assessment_vals = [28.0, 28.1, 28.0]

    # With distinct period identifiers:
    res = detect_anomalies(
        values=assessment_vals,
        baseline_values=baseline_vals,
        threshold_sigma=2.0,
        min_baseline_samples=10,
        baseline_period="Decadal Baseline (2015-2024)",
        assessment_period="Current Observation (2025)",
    )
    assert res["eligible"] is True
    assert res["anomaly_detected"] is False

    # But identical object reference is rejected:
    res_same = detect_anomalies(
        values=baseline_vals,
        baseline_values=baseline_vals,
        threshold_sigma=2.0,
    )
    assert res_same["eligible"] is False
    assert "Anomaly detection requires separate" in res_same["limitation"]

# -----------------------------------------------------------------------------
# 17. Live External API Smoke Test (Explicit Group)
# -----------------------------------------------------------------------------

@pytest.mark.live_api
@pytest.mark.asyncio
async def test_live_open_meteo_smoke():
    """Smoke test for live Open-Meteo external service. Requires network access."""
    client = OpenMeteoMarineClient()
    obs, evs, limits = await client.fetch_marine_data(latitude=12.87, longitude=74.88)
    assert len(obs) > 0
    assert len(evs) > 0
    assert obs[0].wave_height_meters is not None

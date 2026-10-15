import uuid
from datetime import UTC, datetime, timedelta

from app.agents.base import AgentResult, AgentStatus, BaseAgent, InvestigationTask
from app.agents.ocean_research.calculations import (
    compare_locations,
    compare_time_periods,
    compute_seasonal_breakdown,
    compute_series_stats,
    detect_anomalies,
    filter_and_clean_observations,
    get_indian_ocean_season,
    validate_geographic_coordinates,
)
from app.agents.ocean_research.queries import (
    MarineResearchQueryService,
)
from app.core.config import settings
from app.db.repositories.marine import MarineRepository
from app.providers.data.historical_marine import HistoricalMarineDataLoader
from app.providers.data.open_meteo import OpenMeteoMarineClient, to_utc_datetime
from app.providers.llm.base import BaseLLMProvider
from app.schemas.evidence import (
    EvidenceRecord,
    Finding,
    FindingCategory,
    VerificationStatus,
)


class OceanResearchAgent(BaseAgent):
    """
    Ocean Intelligence & Research Agent (Person 1 Ownership).
    Conducts deterministic analysis of marine conditions, sea-surface temperatures,
    wave dynamics, ocean currents, and environmental patterns using the ORCA hybrid
    marine data architecture (real historical datasets + live Open-Meteo observations).
    """
    agent_id: str = "ocean_research"
    name: str = "Ocean Intelligence & Research Agent"
    description: str = "Analyzes marine observations, SST series, wave spectra, seasonal patterns, and anomaly baselines."

    def __init__(
        self,
        live_client: OpenMeteoMarineClient | None = None,
        historical_loader: HistoricalMarineDataLoader | None = None,
        marine_repository: MarineRepository | None = None,
        llm_provider: BaseLLMProvider | None = None,
        demo_mode: bool = False,
    ):
        self.live_client = live_client or OpenMeteoMarineClient(demo_mode=demo_mode)
        self.historical_loader = historical_loader or HistoricalMarineDataLoader()
        self.marine_repository = marine_repository
        self.demo_mode = demo_mode
        self.query_service = MarineResearchQueryService(
            repository=self.marine_repository,
            historical_loader=self.historical_loader,
        )
        if llm_provider is not None:
            self.llm_provider = llm_provider
        elif getattr(settings, "GROQ_API_KEY", None) and not settings.GROQ_API_KEY.startswith("your_"):
            try:
                from app.providers.llm.groq import GroqLLMProvider
                self.llm_provider = GroqLLMProvider()
            except Exception:
                self.llm_provider = None
        else:
            self.llm_provider = None

    def set_repository(self, repository: MarineRepository) -> None:
        """Injects or updates the shared MarineRepository instance."""
        self.marine_repository = repository
        self.query_service.repository = repository

    async def run(self, task: InvestigationTask) -> AgentResult:
        findings: list[Finding] = []
        evidence_records: list[EvidenceRecord] = []
        limitations: list[str] = []
        errors: list[str] = []

        is_demo_mode = self.demo_mode or bool(task.context.get("demo_mode", False))

        # Resolve effective query service (supporting repository or session injected via task context)
        effective_query_service = self.query_service
        if "repository" in task.context and isinstance(task.context["repository"], MarineRepository):
            effective_query_service = MarineResearchQueryService(
                repository=task.context["repository"],
                historical_loader=self.historical_loader,
            )
        elif "session" in task.context:
            effective_query_service = MarineResearchQueryService(
                repository=MarineRepository(task.context["session"]),
                historical_loader=self.historical_loader,
            )

        # 1. Geographic Coordinate Normalization & Validation (Default: Mangaluru Offshore)
        lat = task.latitude if task.latitude is not None else 12.87
        lon = task.longitude if task.longitude is not None else 74.88

        is_valid_coords, coord_err = validate_geographic_coordinates(lat, lon)
        if not is_valid_coords:
            errors.append(coord_err or "Invalid geographic coordinates.")
            return AgentResult(
                agent_id=self.agent_id,
                status=AgentStatus.FAILED,
                findings=[],
                evidence=[],
                limitations=limitations,
                errors=errors,
            )

        prompt_lower = task.prompt.lower()

        # Temporal bounds extraction and normalization to UTC
        now_utc = datetime.now(UTC)
        target_time = to_utc_datetime(getattr(task, "target_time", None) or task.context.get("target_time"))
        start_time = to_utc_datetime(getattr(task, "start_time", None) or task.context.get("start_time"))
        end_time = to_utc_datetime(getattr(task, "end_time", None) or task.context.get("end_time"))
        target_date_val = task.context.get("target_date")
        target_date = None
        if target_date_val:
            if isinstance(target_date_val, datetime):
                target_date = target_date_val.date()
            elif hasattr(target_date_val, "year") and hasattr(target_date_val, "month") and hasattr(target_date_val, "day") and not hasattr(target_date_val, "hour"):
                target_date = target_date_val
            elif isinstance(target_date_val, str):
                try:
                    target_date = datetime.fromisoformat(target_date_val.replace("Z", "+00:00")).date()
                except Exception:
                    pass

        # Check if target_time is in the past or out of forecast coverage
        is_past_target = False
        is_out_of_coverage = False

        if target_time is not None:
            if target_time < (now_utc - timedelta(hours=1)):
                is_past_target = True
                limitations.append(
                    f"Requested target_time ({target_time.isoformat()}) is in the past. "
                    "Live numerical forecast does not cover historical dates; current forecast was not substituted for past conditions."
                )
            elif target_time > (now_utc + timedelta(days=8)):
                is_out_of_coverage = True
                limitations.append(
                    f"Requested target_time ({target_time.isoformat()}) exceeds the 7-day model forecast horizon. "
                    "Marine forecast is unavailable for this date."
                )

        # Determine effective historical query temporal bounds
        if target_date:
            day_start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=UTC)
            day_end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999, tzinfo=UTC)
            hist_start = start_time or day_start
            hist_end = end_time or min(day_end, now_utc)
        elif is_past_target and target_time:
            hist_start = start_time
            hist_end = end_time or target_time
        else:
            hist_start = start_time
            hist_end = min(end_time, now_utc) if end_time else now_utc

        # Enforce limitations on unsupported variables requested in prompt
        if "chlorophyll" in prompt_lower:
            limitations.append(
                "Chlorophyll ocean-color measurements require satellite optical sensors (e.g. MODIS/Copernicus Sentinel-3). "
                "Not available in Open-Meteo meteorological feeds."
            )

        if "salinity" in prompt_lower:
            limitations.append(
                "Sea surface salinity (SSS) is not currently ingested in connected near-real-time atmospheric feeds. "
                "Requires SMOS/Aquarius satellite or Argo float profile datasets."
            )

        if any(term in prompt_lower for term in ["five years", "5 years", "decade", "decadal"]):
            limitations.append(
                "Requested multi-year (5+ year) trend exceeds available active dataset coverage (June 2025 - May 2026). "
                "Long-term multi-decadal analysis requires deep archive ingestion."
            )

        # 2. Location Comparison Analysis (if requested in task context or prompt)
        compare_lat = task.context.get("compare_latitude")
        compare_lon = task.context.get("compare_longitude")
        compare_loc_name = task.context.get("compare_location_name")

        if compare_lat is None and "karwar" in prompt_lower and ("mangaluru" in prompt_lower or "compare" in prompt_lower):
            # Built-in coastal reference: Karwar Offshore (Uttara Kannada)
            compare_lat = 14.80
            compare_lon = 74.12
            compare_loc_name = "Karwar Offshore"

        if compare_lat is not None and compare_lon is not None:
            is_comp_valid, comp_err = validate_geographic_coordinates(compare_lat, compare_lon)
            if not is_comp_valid:
                limitations.append(f"Comparative location coordinates invalid: {comp_err}")
            else:
                loc_a_name = task.context.get("location_name", f"Location A ({lat:.2f}°N, {lon:.2f}°E)")
                loc_b_name = compare_loc_name or f"Location B ({compare_lat:.2f}°N, {compare_lon:.2f}°E)"

                obs_a, src_a = await effective_query_service.get_observations(lat, lon, radius_km=60.0, allow_fixture_fallback=is_demo_mode)
                obs_b, src_b = await effective_query_service.get_observations(compare_lat, compare_lon, radius_km=60.0, allow_fixture_fallback=is_demo_mode)
                if src_a == "sample_fixture_demo" or src_b == "sample_fixture_demo":
                    limitations.append(
                        "Location comparison used offline sample fixture data (demo mode)."
                    )

                sst_a = [o["sea_surface_temperature_celsius"] for o in obs_a if o.get("sea_surface_temperature_celsius") is not None]
                sst_b = [o["sea_surface_temperature_celsius"] for o in obs_b if o.get("sea_surface_temperature_celsius") is not None]

                if sst_a and sst_b:
                    loc_comp = compare_locations(
                        loc_a_values=sst_a,
                        loc_b_values=sst_b,
                        loc_a_name=loc_a_name,
                        loc_b_name=loc_b_name,
                        variable_name="sea_surface_temperature_celsius",
                        unit="°C",
                    )
                    if loc_comp["valid_comparison"]:
                        # Create evidence record for location comparison
                        comp_ev_id = f"ev-comp-loc-{uuid.uuid4().hex[:8]}"
                        evidence_records.append(
                            EvidenceRecord(
                                id=comp_ev_id,
                                source_name="ORCA Marine Geospatial Comparison Service",
                                source_uri=f"geo:pairwise?a={lat},{lon}&b={compare_lat},{compare_lon}",
                                data_type="spatial_comparison",
                                unit="°C",
                                metadata={
                                    "location_a": loc_a_name,
                                    "location_b": loc_b_name,
                                    "mean_diff": loc_comp["mean_difference"],
                                    "source_types": [src_a, src_b],
                                },
                            )
                        )
                        mean_diff = loc_comp["mean_difference"]
                        if mean_diff > 0:
                            diff_desc = f"{mean_diff} °C warmer"
                        elif mean_diff < 0:
                            diff_desc = f"{abs(mean_diff)} °C cooler"
                        else:
                            diff_desc = "identical in temperature (0.0 °C difference)"

                        findings.append(
                            Finding(
                                id=f"fnd-comp-loc-{uuid.uuid4().hex[:8]}",
                                claim=(
                                    f"{loc_b_name} is on average {diff_desc} "
                                    f"than {loc_a_name} (mean: {loc_comp['location_b']['stats']['mean']} °C vs "
                                    f"{loc_comp['location_a']['stats']['mean']} °C)."
                                ),
                                value=loc_comp["mean_difference"],
                                unit="°C",
                                category=FindingCategory.DETERMINISTIC_CALCULATION,
                                evidence_ids=[comp_ev_id],
                                uncertainty="Pairwise spatial comparison across regional observations.",
                                verification_status=VerificationStatus.UNVERIFIED,
                            )
                        )
                else:
                    limitations.append(
                        f"Insufficient spatial observations to compare {loc_a_name} with {loc_b_name}."
                    )

        # Dynamic location label avoiding hardcoded regions where unjustified
        if task.context.get("location_name"):
            loc_label = task.context["location_name"]
        elif 11.5 <= lat <= 15.5 and 73.0 <= lon <= 75.5:
            loc_label = "Karnataka Coast"
        else:
            loc_label = f"coordinates ({lat:.2f}°N, {lon:.2f}°E)"

        # 3. Historical Scientific Data Processing
        is_historical_inquiry = any(
            kw in prompt_lower for kw in [
                "historical", "season", "past", "compare", "monsoon",
                "trend", "baseline", "anomaly", "annual", "year", "series", "summary"
            ]
        )
        hist_query_failed_or_empty = False

        if is_historical_inquiry or is_past_target:
            try:
                # Filter historical records for target geographic proximity and temporal window
                target_hist, query_source = await effective_query_service.get_observations(
                    latitude=lat,
                    longitude=lon,
                    radius_km=100.0,
                    start_time=hist_start,
                    end_time=hist_end,
                    allow_fixture_fallback=is_demo_mode,
                    query_nature="historical",
                )
                if query_source in ("database_error", "database_empty", "no_repository_configured") or not target_hist:
                    hist_query_failed_or_empty = True

                is_demo_hist = query_source == "sample_fixture_demo"
                hist_prefix = "[SAMPLE FIXTURE / DEMO DATA] " if is_demo_hist else ""
                hist_uncertainty = (
                    "DEMO FIXTURE ONLY: Not an authoritative scientific archive or real baseline."
                    if is_demo_hist
                    else f"Derived from regional database historical observation series ({query_source})."
                )

                if query_source == "database_repository" and target_hist:
                    db_ev_id = f"ev-db-marine-{uuid.uuid4().hex[:8]}"
                    rec_meta = target_hist[0].get("metadata_json", {})
                    data_nature = rec_meta.get("data_nature", "persisted_marine_observations")
                    src_model = rec_meta.get("model") or rec_meta.get("dataset") or "hindcast_reanalysis"
                    db_evidence = EvidenceRecord(
                        id=db_ev_id,
                        source_name="PostgreSQL Marine Repository (ORCA Shared Backend)",
                        source_uri=f"db://postgres/marine_observations?lat={lat:.2f}&lon={lon:.2f}&radius=100km",
                        data_type=data_nature,
                        unit="mixed",
                        metadata={
                            "record_count": len(target_hist),
                            "storage": "postgresql_shared_repository",
                            "station_coverage": f"Area centered on ({lat:.2f}°N, {lon:.2f}°E) radius 100km",
                            "data_nature": data_nature,
                            "model_or_product": src_model,
                            "temporal_start": hist_start.isoformat() if hist_start else None,
                            "temporal_end": hist_end.isoformat() if hist_end else None,
                        },
                    )
                    evidence_records.append(db_evidence)
                    primary_hist_ev_id = db_ev_id
                elif is_demo_hist and target_hist:
                    hist_records, hist_ev, parse_counts = self.historical_loader.load_local_dataset()
                    evidence_records.append(hist_ev)
                    primary_hist_ev_id = hist_ev.id
                    limitations.append(
                        "[SAMPLE FIXTURE / DEMO DATA] Historical analysis utilized offline sample reference fixture. "
                        "Results represent demonstration data, not an authoritative scientific baseline."
                    )
                else:
                    if query_source == "database_empty":
                        limitations.append(
                            f"No qualifying historical observation records available in database repository within 100km radius of coordinates ({lat:.2f}°N, {lon:.2f}°E). "
                            "Offline sample fixture was not substituted in production mode; current forecast was not substituted for missing historical data."
                        )
                    elif query_source == "database_error":
                        limitations.append(
                            "Database repository query failed while retrieving historical marine observations. "
                            "Offline sample fixture was not substituted in production mode; current forecast was not substituted for missing historical data."
                        )
                    else:
                        limitations.append(
                            "Shared marine database repository is not configured. "
                            "Offline sample fixture was not substituted in production mode; current forecast was not substituted for missing historical data."
                        )
                    primary_hist_ev_id = None

                if target_hist and primary_hist_ev_id:
                    # Clean & validate observations (check physical bounds & deduplicate preserving distinct spatial coords)
                    raw_coords = [(r.get("latitude", lat), r.get("longitude", lon)) for r in target_hist]
                    raw_sst = [r.get("sea_surface_temperature_celsius") for r in target_hist]
                    raw_dates = [r.get("observation_time") for r in target_hist]
                    clean_sst, clean_dates, clean_issues = filter_and_clean_observations(
                        values=raw_sst,
                        timestamps=raw_dates,
                        coordinates=raw_coords,
                        variable_name="sea_surface_temperature_celsius",
                        deduplicate_timestamps=True,
                    )
                    limitations.extend(clean_issues)

                    raw_waves = [r.get("wave_height_meters") for r in target_hist]
                    clean_waves, wave_dates, wave_issues = filter_and_clean_observations(
                        values=raw_waves,
                        timestamps=raw_dates,
                        coordinates=raw_coords,
                        variable_name="wave_height_meters",
                        deduplicate_timestamps=True,
                    )
                    limitations.extend(wave_issues)

                    if hist_start and hist_end:
                        period_desc = f"from {hist_start.strftime('%Y-%m-%d')} to {hist_end.strftime('%Y-%m-%d')}"
                    elif hist_start:
                        period_desc = f"from {hist_start.strftime('%Y-%m-%d')} onwards"
                    elif hist_end:
                        period_desc = f"up to {hist_end.strftime('%Y-%m-%d')}"
                    else:
                        period_desc = f"historical series up to {now_utc.strftime('%Y-%m-%d')}"

                    # Historical Time-Series Summary with Median & Temporal Gaps
                    if clean_sst:
                        sst_stats = compute_series_stats(clean_sst, clean_dates, max_gap_hours=72.0)
                        gap_count = len(sst_stats["sampling_gaps"])
                        gap_info = f", with {gap_count} sampling gap(s) > 72h" if gap_count > 0 else ""

                        findings.append(
                            Finding(
                                id=f"fnd-hist-sst-{uuid.uuid4().hex[:8]}",
                                claim=(
                                    f"{hist_prefix}Historical sea surface temperature off {loc_label} ({period_desc}) averages {sst_stats['mean']} °C "
                                    f"(median: {sst_stats['median']} °C, range: {sst_stats['min']} - {sst_stats['max']} °C "
                                    f"across {sst_stats['count']} records{gap_info})."
                                ),
                                value=sst_stats["mean"],
                                unit="°C",
                                category=FindingCategory.HISTORICAL_RECORD,
                                evidence_ids=[primary_hist_ev_id],
                                uncertainty=hist_uncertainty,
                                verification_status=VerificationStatus.UNVERIFIED,
                            )
                        )

                    # Seasonal Breakdown Analysis (preserving wave_dates with clean_waves)
                    if len(wave_dates) >= 4 and clean_waves:
                        seasonal = compute_seasonal_breakdown(wave_dates, clean_waves, min_observations_per_season=2)
                        for season_name, sstats in seasonal.items():
                            if sstats["is_adequate_coverage"] and sstats["count"] > 0:
                                findings.append(
                                    Finding(
                                        id=f"fnd-season-{season_name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
                                        claim=(
                                            f"{hist_prefix}{season_name} sea state records mean wave height of {sstats['mean']} m "
                                            f"(median: {sstats['median']} m, max: {sstats['max']} m, count: {sstats['count']})."
                                        ),
                                        value=sstats["mean"],
                                        unit="m",
                                        category=FindingCategory.DETERMINISTIC_CALCULATION,
                                        evidence_ids=[primary_hist_ev_id],
                                        uncertainty=hist_uncertainty,
                                        verification_status=VerificationStatus.UNVERIFIED,
                                    )
                                )
                            elif not sstats["is_adequate_coverage"] and sstats["limitation"]:
                                limitations.append(sstats["limitation"])

                        # Deterministic Period Comparison: Southwest Monsoon vs. Post-Monsoon
                        # Derived dynamically from timestamps via get_indian_ocean_season (not requiring fixture-only metadata)
                        monsoon_waves = [
                            r["wave_height_meters"] for r in target_hist
                            if r.get("observation_time") and get_indian_ocean_season(r["observation_time"]) == "Southwest Monsoon"
                            and r.get("wave_height_meters") is not None
                        ]
                        post_monsoon_waves = [
                            r["wave_height_meters"] for r in target_hist
                            if r.get("observation_time") and get_indian_ocean_season(r["observation_time"]) == "Post-Monsoon"
                            and r.get("wave_height_meters") is not None
                        ]
                        if monsoon_waves and post_monsoon_waves:
                            comp = compare_time_periods(
                                period_a_values=post_monsoon_waves,
                                period_b_values=monsoon_waves,
                                variable_name="wave_height",
                                unit="m",
                                period_a_name="Post-Monsoon",
                                period_b_name="Southwest Monsoon",
                            )
                            if comp["valid_comparison"]:
                                mean_diff = comp["mean_difference"]
                                if mean_diff > 0:
                                    diff_desc = f"{mean_diff} m higher"
                                elif mean_diff < 0:
                                    diff_desc = f"{abs(mean_diff)} m lower"
                                else:
                                    diff_desc = "identical (0.0 m difference)"

                                findings.append(
                                    Finding(
                                        id=f"fnd-comp-monsoon-{uuid.uuid4().hex[:8]}",
                                        claim=(
                                            f"{hist_prefix}Southwest Monsoon wave heights are {diff_desc} "
                                            f"(median diff: {comp['median_difference']} m, {comp['percentage_change']}% change) "
                                            f"compared to Post-Monsoon baseline."
                                        ),
                                        value=comp["mean_difference"],
                                        unit="m",
                                        category=FindingCategory.DETERMINISTIC_CALCULATION,
                                        evidence_ids=[primary_hist_ev_id],
                                        uncertainty=hist_uncertainty,
                                        verification_status=VerificationStatus.UNVERIFIED,
                                    )
                                )

                    # Anomaly check requiring separate, sufficiently supported baseline and assessment periods
                    assessment_sst = None
                    baseline_sst = None
                    if "assessment_sst" in task.context:
                        assessment_sst = task.context["assessment_sst"]
                        baseline_sst = clean_sst
                    elif task.target_time:
                        target_dt = task.target_time.replace(tzinfo=UTC) if task.target_time.tzinfo is None else task.target_time
                        assessment_sst = [
                            r.get("sea_surface_temperature_celsius") for r in target_hist
                            if r.get("sea_surface_temperature_celsius") is not None
                            and r.get("observation_time")
                            and abs((r.get("observation_time") - target_dt).total_seconds()) <= 48 * 3600
                        ]
                        baseline_sst = [
                            r.get("sea_surface_temperature_celsius") for r in target_hist
                            if r.get("sea_surface_temperature_celsius") is not None
                            and r.get("observation_time")
                            and (target_dt - r.get("observation_time")).total_seconds() > 48 * 3600
                        ]
                    elif "baseline_sst" in task.context:
                        baseline_sst = task.context["baseline_sst"]
                        assessment_sst = clean_sst

                    # Do not run anomaly calculations on demo fixtures in normal mode
                    if is_demo_hist and not is_demo_mode:
                        limitations.append("Statistical anomaly detection skipped: sample fixtures cannot establish a scientific baseline in production mode.")
                    elif baseline_sst is not None and assessment_sst is not None and len(baseline_sst) >= 10 and len(assessment_sst) >= 1:
                        anom = detect_anomalies(assessment_sst, baseline_sst, threshold_sigma=2.0, min_baseline_samples=10)
                        if anom["eligible"]:
                            if anom["anomaly_detected"]:
                                findings.append(
                                    Finding(
                                        id=f"fnd-anom-sst-{uuid.uuid4().hex[:8]}",
                                        claim=f"{hist_prefix}Detected {anom['anomaly_count']} sea surface temperature reading(s) exceeding 2.0-sigma baseline variance.",
                                        value=anom["anomaly_count"],
                                        unit="occurrences",
                                        category=FindingCategory.DETERMINISTIC_CALCULATION,
                                        evidence_ids=[primary_hist_ev_id],
                                        uncertainty=hist_uncertainty,
                                        verification_status=VerificationStatus.UNVERIFIED,
                                    )
                                )
                            else:
                                findings.append(
                                    Finding(
                                        id=f"fnd-anom-sst-{uuid.uuid4().hex[:8]}",
                                        claim=f"{hist_prefix}No sea surface temperature anomalies detected beyond 2.0-sigma variance threshold.",
                                        value=0,
                                        unit="occurrences",
                                        category=FindingCategory.DETERMINISTIC_CALCULATION,
                                        evidence_ids=[primary_hist_ev_id],
                                        uncertainty=hist_uncertainty,
                                        verification_status=VerificationStatus.UNVERIFIED,
                                    )
                                )
                        else:
                            limitations.append(anom["limitation"])
                    else:
                        limitations.append("Statistical anomaly detection was not performed: requires separate, sufficiently supported baseline and assessment periods.")

            except Exception as e:
                errors.append(f"Historical dataset processing error: {e!s}")

        # 4. Live Marine Observations Retrieval & Time-Window Filtering
        live_obs, live_ev, live_limits = await self.live_client.fetch_marine_data(lat, lon, demo_mode=is_demo_mode)
        evidence_records.extend(live_ev)
        limitations.extend(live_limits)

        # Ingest live observations into shared PostgreSQL repository if active
        if live_obs and effective_query_service.repository:
            try:
                await effective_query_service.repository.ensure_data_source(
                    source_id="open_meteo",
                    name="Open-Meteo Marine API",
                    base_url="https://marine-api.open-meteo.com/v1/marine",
                    description="Near-real-time oceanic wave and current numerical model observations",
                )
                db_recs = []
                for p in live_obs:
                    db_recs.append({
                        "source_id": "open_meteo",
                        "observation_time": p.time,
                        "latitude": p.latitude,
                        "longitude": p.longitude,
                        "sea_surface_temperature_celsius": p.sea_surface_temperature_celsius,
                        "wave_height_meters": p.wave_height_meters,
                        "wave_period_seconds": p.wave_period_seconds,
                        "wave_direction_degrees": p.wave_direction_degrees,
                        "ocean_current_velocity_mps": p.ocean_current_velocity_mps,
                        "ocean_current_direction_degrees": p.ocean_current_direction_degrees,
                        "wind_speed_knots": p.wind_speed_knots,
                        "wind_direction_degrees": p.wind_direction_degrees,
                        "chlorophyll_mg_m3": p.chlorophyll_mg_m3,
                        "metadata_json": {
                            "ingested_at": now_utc.isoformat(),
                            "forecast_run_time": now_utc.replace(minute=0, second=0, microsecond=0).isoformat(),
                            "retrieval_time": now_utc.isoformat(),
                            "data_nature": "numerical_model_forecast",
                            "is_demo": is_demo_mode,
                        },
                    })
                await effective_query_service.repository.bulk_ingest(db_recs)
            except Exception as e:
                limitations.append(f"Persistence of live marine observations to PostgreSQL skipped ({e!s}).")

        # Evaluate live forecast only if target time is not past and not out of coverage
        if live_obs and not is_past_target and not is_out_of_coverage:
            primary_live_ev_id = live_ev[0].id if live_ev else "ev-live-none"
            effective_live_obs = []
            time_desc = ""

            # Apply requested time constraints with strict precedence:
            # Precedence 1: target_time (exact valid forecast point)
            if target_time:
                closest_obs = min(live_obs, key=lambda p: abs((p.time - target_time).total_seconds()))
                diff_sec = abs((closest_obs.time - target_time).total_seconds())
                FORECAST_TIME_TOLERANCE_SECONDS = 3600.0
                if diff_sec <= FORECAST_TIME_TOLERANCE_SECONDS:
                    effective_live_obs = [closest_obs]
                    time_desc = f"at {closest_obs.time.strftime('%Y-%m-%d %H:%M UTC')} (requested: {target_time.strftime('%Y-%m-%d %H:%M UTC')})"
                else:
                    effective_live_obs = []
                    limitations.append(
                        f"Requested target_time ({target_time.isoformat()}) differs from nearest available forecast hour "
                        f"({closest_obs.time.isoformat()}) by {int(diff_sec)}s, exceeding tolerance of {int(FORECAST_TIME_TOLERANCE_SECONDS)}s. "
                        "Full forecast summary was not substituted."
                    )
            # Precedence 2: target_date (single-day forecast window)
            elif target_date:
                effective_live_obs = [p for p in live_obs if p.time.date() == target_date]
                time_desc = f"on {target_date.isoformat()} (excluding other forecast days)"
                if not effective_live_obs:
                    limitations.append(
                        f"No forecast observations available for target date {target_date.isoformat()}. "
                        "Full forecast summary was not substituted."
                    )
            # Precedence 3: start_time and/or end_time (independent bounds)
            elif start_time or end_time:
                effective_live_obs = list(live_obs)
                bound_desc = []
                if start_time:
                    effective_live_obs = [p for p in effective_live_obs if p.time >= start_time]
                    bound_desc.append(f"from {start_time.strftime('%Y-%m-%d %H:%M UTC')}")
                if end_time:
                    effective_live_obs = [p for p in effective_live_obs if p.time <= end_time]
                    bound_desc.append(f"to {end_time.strftime('%Y-%m-%d %H:%M UTC')}")
                time_desc = " ".join(bound_desc)
                if not effective_live_obs:
                    limitations.append(
                        f"No forecast observations available within requested interval ({' '.join(bound_desc)}). "
                        "Full forecast summary was not substituted."
                    )
            # Precedence 4: full available forecast horizon
            else:
                effective_live_obs = live_obs
                time_desc = f"across {len(live_obs)} forecast hours"

            raw_live_sst = [p.sea_surface_temperature_celsius for p in effective_live_obs if p.sea_surface_temperature_celsius is not None]
            raw_live_waves = [p.wave_height_meters for p in effective_live_obs if p.wave_height_meters is not None]
            raw_live_currents = [p.ocean_current_velocity_mps for p in effective_live_obs if p.ocean_current_velocity_mps is not None]
            raw_live_winds = [p.wind_speed_knots for p in effective_live_obs if p.wind_speed_knots is not None]

            prefix = "[SAMPLE FIXTURE / DEMO DATA] " if is_demo_mode else ""
            finding_cat = FindingCategory.FORECAST

            if raw_live_sst:
                sst_stats = compute_series_stats(raw_live_sst)
                count_str = "1 forecast hour" if sst_stats['count'] == 1 else f"{sst_stats['count']} forecast hours"
                findings.append(
                    Finding(
                        id=f"fnd-live-sst-{uuid.uuid4().hex[:8]}",
                        claim=(
                            f"{prefix}Near-surface sea temperature model forecast off {loc_label} {time_desc} averages {sst_stats['mean']} °C "
                            f"(range: {sst_stats['min']} - {sst_stats['max']} °C across {count_str})."
                        ),
                        value=sst_stats["mean"],
                        unit="°C",
                        category=finding_cat,
                        evidence_ids=[primary_live_ev_id],
                        uncertainty="DEMO FIXTURE ONLY: Sample data for demonstration, not genuine observations or forecasts." if is_demo_mode else "Numerical ocean circulation model forecast.",
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                )

            if raw_live_waves:
                w_stats = compute_series_stats(raw_live_waves)
                findings.append(
                    Finding(
                        id=f"fnd-live-wave-{uuid.uuid4().hex[:8]}",
                        claim=(
                            f"{prefix}Wave model forecast off {loc_label} {time_desc} indicates mean significant wave height "
                            f"of {w_stats['mean']} m (median: {w_stats['median']} m, range: {w_stats['min']} - {w_stats['max']} m)."
                        ),
                        value=w_stats["mean"],
                        unit="m",
                        category=finding_cat,
                        evidence_ids=[primary_live_ev_id],
                        uncertainty="DEMO FIXTURE ONLY: Sample data for demonstration, not genuine observations or forecasts." if is_demo_mode else "Short-term wave spectrum numerical forecast model.",
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                )

            if raw_live_currents:
                c_stats = compute_series_stats(raw_live_currents)
                findings.append(
                    Finding(
                        id=f"fnd-live-current-{uuid.uuid4().hex[:8]}",
                        claim=(
                            f"{prefix}Ocean current model forecast off {loc_label} {time_desc} indicates mean current velocity "
                            f"of {c_stats['mean']} m/s (peak: {c_stats['max']} m/s)."
                        ),
                        value=c_stats["mean"],
                        unit="m/s",
                        category=finding_cat,
                        evidence_ids=[primary_live_ev_id],
                        uncertainty="DEMO FIXTURE ONLY: Sample data for demonstration, not genuine observations or forecasts." if is_demo_mode else "Hydrodynamic ocean circulation model forecast.",
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                )

            if raw_live_winds:
                wind_stats = compute_series_stats(raw_live_winds)
                findings.append(
                    Finding(
                        id=f"fnd-live-wind-{uuid.uuid4().hex[:8]}",
                        claim=(
                            f"{prefix}Offshore surface wind speed {time_desc} averages {wind_stats['mean']} knots "
                            f"(median: {wind_stats['median']} knots, peak: {wind_stats['max']} knots)."
                        ),
                        value=wind_stats["mean"],
                        unit="knots",
                        category=finding_cat,
                        evidence_ids=[primary_live_ev_id],
                        uncertainty="DEMO FIXTURE ONLY: Sample data for demonstration, not genuine observations or forecasts." if is_demo_mode else "10-meter surface marine wind forecast.",
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                )
        elif not live_obs and not is_past_target and not is_out_of_coverage:
            limitations.append("Live marine observations were not retrieved from external provider.")

        # 5. Optional LLM Scientific Synthesis (Preserving Deterministic Results upon Failure)
        if self.llm_provider and findings:
            try:
                summary_prompt = (
                    "Summarize these oceanographic findings objectively without inventing any data: "
                    + "; ".join(f.claim for f in findings[:4])
                )
                ai_text = await self.llm_provider.generate_text(
                    prompt=summary_prompt,
                    system_instruction="You are a marine scientist assistant. Be concise and strictly factual.",
                )
                if ai_text and ai_text.strip():
                    first_ev_id = evidence_records[0].id if evidence_records else "ev-synth-none"
                    ai_claim = f"[SAMPLE FIXTURE / DEMO DATA] {ai_text.strip()}" if is_demo_mode else ai_text.strip()
                    findings.append(
                        Finding(
                            id=f"fnd-ai-synth-{uuid.uuid4().hex[:8]}",
                            claim=ai_claim,
                            value=None,
                            unit=None,
                            category=FindingCategory.AI_INTERPRETATION,
                            evidence_ids=[first_ev_id],
                            uncertainty="DEMO FIXTURE ONLY: AI synthesis based on sample demonstration fixtures." if is_demo_mode else "AI natural-language synthesis derived strictly from deterministic findings.",
                            verification_status=VerificationStatus.UNVERIFIED,
                        )
                    )
            except Exception as e:
                limitations.append(f"Optional LLM scientific synthesis unavailable ({e!s}). Deterministic results preserved.")

        # 6. Determine Agent Status
        prompt_requested_unsupported = any(
            kw in prompt_lower for kw in ["chlorophyll", "salinity", "5 year", "five year", "decade", "decadal"]
        )
        live_provider_failed = any("Live marine provider unavailable" in lim or "Live provider query error" in lim for lim in limitations)
        is_only_fixture = bool(findings) and (
            is_demo_mode or all(
                "[SAMPLE FIXTURE" in f.claim or "[DEMO FIXTURE]" in f.claim for f in findings
            )
        )

        if errors and not findings:
            status = AgentStatus.FAILED
        elif not findings:
            status = AgentStatus.UNAVAILABLE
        elif is_only_fixture:
            # Do not mark the investigation completed merely because a fixture produced plausible values
            status = AgentStatus.PARTIAL
        elif (prompt_requested_unsupported or live_provider_failed or is_past_target or is_out_of_coverage or hist_query_failed_or_empty) and findings:
            status = AgentStatus.PARTIAL
        elif findings:
            status = AgentStatus.COMPLETED
        else:
            status = AgentStatus.PARTIAL

        # Clean duplicates in limitations
        unique_limitations = []
        for lim in limitations:
            if lim not in unique_limitations:
                unique_limitations.append(lim)

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            findings=findings,
            evidence=evidence_records,
            limitations=unique_limitations,
            errors=errors,
        )

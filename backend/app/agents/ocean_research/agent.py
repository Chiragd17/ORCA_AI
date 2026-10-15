import uuid
import math
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from app.agents.base import BaseAgent, InvestigationTask, AgentResult, AgentStatus
from app.schemas.evidence import Finding, EvidenceRecord, FindingCategory, VerificationStatus
from app.providers.data.open_meteo import OpenMeteoMarineClient
from app.providers.data.historical_marine import HistoricalMarineDataLoader
from app.providers.llm.base import BaseLLMProvider
from app.core.config import settings
from app.db.repositories.marine import MarineRepository
from app.agents.ocean_research.calculations import (
    compute_series_stats,
    compute_seasonal_breakdown,
    compare_time_periods,
    compare_locations,
    detect_anomalies,
    validate_geographic_coordinates,
    validate_unit_compatibility,
    filter_and_clean_observations,
)
from app.agents.ocean_research.queries import (
    MarineResearchQueryService,
    SUPPORTED_MARINE_VARIABLES,
    VARIABLE_UNITS,
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
        live_client: Optional[OpenMeteoMarineClient] = None,
        historical_loader: Optional[HistoricalMarineDataLoader] = None,
        marine_repository: Optional[MarineRepository] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
    ):
        self.live_client = live_client or OpenMeteoMarineClient()
        self.historical_loader = historical_loader or HistoricalMarineDataLoader()
        self.marine_repository = marine_repository
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
        findings: List[Finding] = []
        evidence_records: List[EvidenceRecord] = []
        limitations: List[str] = []
        errors: List[str] = []

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

                obs_a, src_a = await effective_query_service.get_observations(lat, lon, radius_km=60.0)
                obs_b, src_b = await effective_query_service.get_observations(compare_lat, compare_lon, radius_km=60.0)
                if src_a == "database_fallback" or src_b == "database_fallback":
                    limitations.append(
                        "Database query failed during location comparison; proceeded using offline historical scientific dataset fallback."
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
                        diff_sign = "warmer" if loc_comp["mean_difference"] > 0 else "cooler"
                        findings.append(
                            Finding(
                                id=f"fnd-comp-loc-{uuid.uuid4().hex[:8]}",
                                claim=(
                                    f"{loc_b_name} is on average {abs(loc_comp['mean_difference'])} °C {diff_sign} "
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

        # 3. Historical Scientific Data Processing
        is_historical_inquiry = any(
            kw in prompt_lower for kw in [
                "historical", "season", "past", "compare", "monsoon",
                "trend", "baseline", "anomaly", "annual", "year", "series", "summary"
            ]
        )

        if is_historical_inquiry:
            try:
                # Filter historical records for target geographic proximity
                target_hist, query_source = await effective_query_service.get_observations(
                    latitude=lat,
                    longitude=lon,
                    radius_km=100.0,
                )

                if query_source == "database_fallback":
                    limitations.append(
                        "PostgreSQL repository query failed; analysis proceeded using offline historical scientific dataset fallback."
                    )

                if query_source == "database_repository" and target_hist:
                    db_ev_id = f"ev-db-marine-{uuid.uuid4().hex[:8]}"
                    db_evidence = EvidenceRecord(
                        id=db_ev_id,
                        source_name="PostgreSQL Marine Repository (ORCA Shared Backend)",
                        source_uri=f"db://postgres/marine_observations?lat={lat:.2f}&lon={lon:.2f}&radius=100km",
                        data_type="persisted_marine_observations",
                        unit="mixed",
                        metadata={
                            "record_count": len(target_hist),
                            "storage": "postgresql_shared_repository",
                            "station_coverage": "Arabian Sea (Karnataka Offshore)",
                        },
                    )
                    evidence_records.append(db_evidence)
                    primary_hist_ev_id = db_ev_id
                elif target_hist:
                    hist_records, hist_ev, parse_counts = self.historical_loader.load_local_dataset()
                    evidence_records.append(hist_ev)
                    primary_hist_ev_id = hist_ev.id
                else:
                    limitations.append(
                        f"No historical observation records available within 100km radius of coordinates ({lat:.2f}°N, {lon:.2f}°E)."
                    )
                    primary_hist_ev_id = None

                if target_hist and primary_hist_ev_id:
                    # Clean & validate observations (check physical bounds & deduplicate)
                    raw_sst = [r.get("sea_surface_temperature_celsius") for r in target_hist]
                    raw_dates = [r.get("observation_time") for r in target_hist]
                    clean_sst, clean_dates, clean_issues = filter_and_clean_observations(
                        values=raw_sst,
                        timestamps=raw_dates,
                        variable_name="sea_surface_temperature_celsius",
                        deduplicate_timestamps=True,
                    )
                    limitations.extend(clean_issues)

                    raw_waves = [r.get("wave_height_meters") for r in target_hist]
                    clean_waves, wave_dates, wave_issues = filter_and_clean_observations(
                        values=raw_waves,
                        timestamps=raw_dates,
                        variable_name="wave_height_meters",
                        deduplicate_timestamps=True,
                    )
                    limitations.extend(wave_issues)

                    # Historical Time-Series Summary with Median & Temporal Gaps
                    if clean_sst:
                        sst_stats = compute_series_stats(clean_sst, clean_dates, max_gap_hours=72.0)
                        gap_count = len(sst_stats["sampling_gaps"])
                        gap_info = f", with {gap_count} sampling gap(s) > 72h" if gap_count > 0 else ""

                        findings.append(
                            Finding(
                                id=f"fnd-hist-sst-{uuid.uuid4().hex[:8]}",
                                claim=(
                                    f"Historical sea surface temperature off Karnataka Coast averages {sst_stats['mean']} °C "
                                    f"(median: {sst_stats['median']} °C, range: {sst_stats['min']} - {sst_stats['max']} °C "
                                    f"across {sst_stats['count']} records{gap_info})."
                                ),
                                value=sst_stats["mean"],
                                unit="°C",
                                category=FindingCategory.HISTORICAL_RECORD,
                                evidence_ids=[primary_hist_ev_id],
                                uncertainty="Derived from validated multi-season ERA5 / Copernicus Marine reanalysis.",
                                verification_status=VerificationStatus.UNVERIFIED,
                            )
                        )

                    # Seasonal Breakdown Analysis
                    if len(clean_dates) >= 4 and clean_waves:
                        seasonal = compute_seasonal_breakdown(clean_dates, clean_waves, min_observations_per_season=2)
                        for season_name, sstats in seasonal.items():
                            if sstats["is_adequate_coverage"] and sstats["count"] > 0:
                                findings.append(
                                    Finding(
                                        id=f"fnd-season-{season_name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
                                        claim=(
                                            f"{season_name} sea state records mean wave height of {sstats['mean']} m "
                                            f"(median: {sstats['median']} m, max: {sstats['max']} m, count: {sstats['count']})."
                                        ),
                                        value=sstats["mean"],
                                        unit="m",
                                        category=FindingCategory.DETERMINISTIC_CALCULATION,
                                        evidence_ids=[primary_hist_ev_id],
                                        uncertainty=f"Categorized via Arabian Sea meteorological seasons ({sstats['season_definition']}).",
                                        verification_status=VerificationStatus.UNVERIFIED,
                                    )
                                )
                            elif not sstats["is_adequate_coverage"] and sstats["limitation"]:
                                limitations.append(sstats["limitation"])

                        # Deterministic Period Comparison: Southwest Monsoon vs. Post-Monsoon
                        monsoon_waves = [
                            r["wave_height_meters"] for r in target_hist
                            if r.get("metadata_json", {}).get("season") == "Southwest Monsoon"
                            and r.get("wave_height_meters") is not None
                        ]
                        post_monsoon_waves = [
                            r["wave_height_meters"] for r in target_hist
                            if r.get("metadata_json", {}).get("season") == "Post-Monsoon"
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
                                findings.append(
                                    Finding(
                                        id=f"fnd-comp-monsoon-{uuid.uuid4().hex[:8]}",
                                        claim=(
                                            f"Southwest Monsoon wave heights are {abs(comp['mean_difference'])} m higher "
                                            f"(median diff: {comp['median_difference']} m, {comp['percentage_change']}% change) "
                                            f"compared to Post-Monsoon baseline."
                                        ),
                                        value=comp["mean_difference"],
                                        unit="m",
                                        category=FindingCategory.DETERMINISTIC_CALCULATION,
                                        evidence_ids=[primary_hist_ev_id],
                                        uncertainty="Deterministic delta calculated from multi-month seasonal records.",
                                        verification_status=VerificationStatus.UNVERIFIED,
                                    )
                                )

                    # Anomaly check against historical baseline
                    if len(clean_sst) >= 10:
                        baseline_sst = clean_sst
                        anom = detect_anomalies(clean_sst, baseline_sst, threshold_sigma=2.0, min_baseline_samples=10)
                        if anom["eligible"]:
                            if anom["anomaly_detected"]:
                                findings.append(
                                    Finding(
                                        id=f"fnd-anom-sst-{uuid.uuid4().hex[:8]}",
                                        claim=f"Detected {anom['anomaly_count']} sea surface temperature reading(s) exceeding 2.0-sigma baseline variance.",
                                        value=anom["anomaly_count"],
                                        unit="occurrences",
                                        category=FindingCategory.DETERMINISTIC_CALCULATION,
                                        evidence_ids=[primary_hist_ev_id],
                                        uncertainty=f"Statistical z-score against baseline mean={anom['baseline_mean']}°C, std={anom['baseline_std_dev']}°C.",
                                        verification_status=VerificationStatus.UNVERIFIED,
                                    )
                                )
                            else:
                                findings.append(
                                    Finding(
                                        id=f"fnd-anom-none-{uuid.uuid4().hex[:8]}",
                                        claim=f"No thermal anomalies detected beyond 2.0-sigma threshold relative to the regional scientific baseline.",
                                        value=0,
                                        unit="occurrences",
                                        category=FindingCategory.DETERMINISTIC_CALCULATION,
                                        evidence_ids=[primary_hist_ev_id],
                                        uncertainty=f"Validated against {anom['baseline_sample_count']}-sample regional baseline.",
                                        verification_status=VerificationStatus.UNVERIFIED,
                                    )
                                )
                        else:
                            limitations.append(anom["limitation"])
                    else:
                        limitations.append("Insufficient historical baseline depth (<10 samples) for statistical anomaly detection.")

            except Exception as e:
                errors.append(f"Historical dataset processing error: {str(e)}")

        # 4. Live Marine Observations Retrieval
        live_obs, live_ev, live_limits = await self.live_client.fetch_marine_data(lat, lon)
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
                        "wave_height_meters": p.wave_height_meters,
                        "wave_period_seconds": p.wave_period_seconds,
                        "wave_direction_degrees": p.wave_direction_degrees,
                        "wind_speed_knots": p.wind_speed_knots,
                        "wind_direction_degrees": p.wind_direction_degrees,
                        "chlorophyll_mg_m3": p.chlorophyll_mg_m3,
                        "metadata_json": {
                            "ingested_at": datetime.now(timezone.utc).isoformat(),
                        },
                    })
                await effective_query_service.repository.bulk_ingest(db_recs)
            except Exception as e:
                limitations.append(f"Persistence of live marine observations to PostgreSQL skipped ({str(e)}).")

        if live_obs:
            primary_live_ev_id = live_ev[0].id if live_ev else "ev-live-none"
            raw_live_waves = [p.wave_height_meters for p in live_obs if p.wave_height_meters is not None]
            raw_live_winds = [p.wind_speed_knots for p in live_obs if p.wind_speed_knots is not None]

            if raw_live_waves:
                w_stats = compute_series_stats(raw_live_waves)
                findings.append(
                    Finding(
                        id=f"fnd-live-wave-{uuid.uuid4().hex[:8]}",
                        claim=(
                            f"Current wave observations off ({lat:.2f}°N, {lon:.2f}°E) indicate mean significant wave height "
                            f"of {w_stats['mean']} m (median: {w_stats['median']} m, range: {w_stats['min']} - {w_stats['max']} m)."
                        ),
                        value=w_stats["mean"],
                        unit="m",
                        category=FindingCategory.OBSERVATION,
                        evidence_ids=[primary_live_ev_id],
                        uncertainty="Short-term wave spectrum forecast model.",
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                )

            if raw_live_winds:
                wind_stats = compute_series_stats(raw_live_winds)
                findings.append(
                    Finding(
                        id=f"fnd-live-wind-{uuid.uuid4().hex[:8]}",
                        claim=(
                            f"Current offshore surface wind speed averages {wind_stats['mean']} knots "
                            f"(median: {wind_stats['median']} knots, peak: {wind_stats['max']} knots)."
                        ),
                        value=wind_stats["mean"],
                        unit="knots",
                        category=FindingCategory.OBSERVATION,
                        evidence_ids=[primary_live_ev_id],
                        uncertainty="Standard 10-meter surface marine wind vector.",
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                )
        else:
            limitations.append("Live marine observations were not retrieved from external provider.")

        # 5. Optional LLM Scientific Synthesis (Preserving Deterministic Results upon Failure)
        if self.llm_provider and findings:
            try:
                summary_prompt = (
                    f"Summarize these oceanographic findings objectively without inventing any data: "
                    + "; ".join(f.claim for f in findings[:4])
                )
                ai_text = await self.llm_provider.generate_text(
                    prompt=summary_prompt,
                    system_instruction="You are a marine scientist assistant. Be concise and strictly factual.",
                )
                if ai_text and ai_text.strip():
                    first_ev_id = evidence_records[0].id if evidence_records else "ev-synth-none"
                    findings.append(
                        Finding(
                            id=f"fnd-ai-synth-{uuid.uuid4().hex[:8]}",
                            claim=ai_text.strip(),
                            value=None,
                            unit=None,
                            category=FindingCategory.AI_INTERPRETATION,
                            evidence_ids=[first_ev_id],
                            uncertainty="AI natural-language synthesis derived strictly from deterministic findings.",
                            verification_status=VerificationStatus.UNVERIFIED,
                        )
                    )
            except Exception as e:
                limitations.append(f"Optional LLM scientific synthesis unavailable ({str(e)}). Deterministic results preserved.")

        # 6. Determine Agent Status
        prompt_requested_unsupported = any(
            kw in prompt_lower for kw in ["chlorophyll", "salinity", "5 year", "five year", "decade", "decadal"]
        )
        if errors and not findings:
            status = AgentStatus.FAILED
        elif not findings and not evidence_records:
            status = AgentStatus.UNAVAILABLE
        elif prompt_requested_unsupported and findings:
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

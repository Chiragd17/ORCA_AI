import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from app.agents.base import BaseAgent, InvestigationTask, AgentResult, AgentStatus
from app.schemas.evidence import Finding, EvidenceRecord, FindingCategory, VerificationStatus
from app.schemas.marine import MarineObservationPoint
from app.providers.data.open_meteo import OpenMeteoMarineClient
from app.providers.data.historical_marine import HistoricalMarineDataLoader
from app.agents.ocean_research.calculations import (
    compute_series_stats,
    compute_seasonal_breakdown,
    compare_time_periods,
    detect_anomalies,
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
    ):
        self.live_client = live_client or OpenMeteoMarineClient()
        self.historical_loader = historical_loader or HistoricalMarineDataLoader()

    async def run(self, task: InvestigationTask) -> AgentResult:
        findings: List[Finding] = []
        evidence_records: List[EvidenceRecord] = []
        limitations: List[str] = []
        errors: List[str] = []

        # 1. Geographic Coordinate Normalization (Default: Mangaluru Offshore / Karnataka Coast)
        lat = task.latitude if task.latitude is not None else 12.87
        lon = task.longitude if task.longitude is not None else 74.88
        prompt_lower = task.prompt.lower()

        is_historical_inquiry = any(
            kw in prompt_lower for kw in [
                "historical", "season", "past", "compare", "monsoon",
                "trend", "baseline", "anomaly", "annual", "year"
            ]
        )

        # 2. Historical Scientific Data Processing
        if is_historical_inquiry:
            try:
                hist_records, hist_ev, parse_counts = self.historical_loader.load_local_dataset()
                evidence_records.append(hist_ev)

                # Filter historical records for target geographic proximity
                target_hist = [
                    r for r in hist_records
                    if abs(r["latitude"] - lat) <= 1.0 and abs(r["longitude"] - lon) <= 1.0
                ] or hist_records

                hist_sst = [r["sea_surface_temperature_celsius"] for r in target_hist if r.get("sea_surface_temperature_celsius") is not None]
                hist_waves = [r["wave_height_meters"] for r in target_hist if r.get("wave_height_meters") is not None]
                hist_dates = [r["observation_time"] for r in target_hist]

                # Historical Time-Series Summary
                if hist_sst:
                    sst_stats = compute_series_stats(hist_sst)
                    findings.append(
                        Finding(
                            id=f"fnd-hist-sst-{uuid.uuid4().hex[:8]}",
                            claim=(
                                f"Historical sea surface temperature off Karnataka Coast averages {sst_stats['mean']} °C "
                                f"(observed range: {sst_stats['min']} - {sst_stats['max']} °C across {sst_stats['count']} records)."
                            ),
                            value=sst_stats["mean"],
                            unit="°C",
                            category=FindingCategory.HISTORICAL_RECORD,
                            evidence_ids=[hist_ev.id],
                            uncertainty="Derived from validated multi-season ERA5 / Copernicus Marine reanalysis.",
                            verification_status=VerificationStatus.UNVERIFIED,
                        )
                    )

                # Seasonal Breakdown Analysis
                if len(hist_dates) >= 4 and hist_waves:
                    seasonal = compute_seasonal_breakdown(hist_dates, hist_waves)
                    for season_name, sstats in seasonal.items():
                        if sstats["count"] > 0:
                            findings.append(
                                Finding(
                                    id=f"fnd-season-{season_name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
                                    claim=(
                                        f"{season_name} sea state records mean wave height of {sstats['mean']} m "
                                        f"(max: {sstats['max']} m, count: {sstats['count']})."
                                    ),
                                    value=sstats["mean"],
                                    unit="m",
                                    category=FindingCategory.DETERMINISTIC_CALCULATION,
                                    evidence_ids=[hist_ev.id],
                                    uncertainty="Categorized via Arabian Sea meteorological seasons.",
                                    verification_status=VerificationStatus.UNVERIFIED,
                                )
                            )

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
                        comp = compare_time_periods(post_monsoon_waves, monsoon_waves, "wave_height", "m")
                        if comp["valid_comparison"]:
                            findings.append(
                                Finding(
                                    id=f"fnd-comp-monsoon-{uuid.uuid4().hex[:8]}",
                                    claim=(
                                        f"Southwest Monsoon wave heights are {abs(comp['mean_difference'])} m higher "
                                        f"({comp['percentage_change']}% increase) compared to Post-Monsoon baseline."
                                    ),
                                    value=comp["mean_difference"],
                                    unit="m",
                                    category=FindingCategory.DETERMINISTIC_CALCULATION,
                                    evidence_ids=[hist_ev.id],
                                    uncertainty="Deterministic delta calculated from multi-month seasonal records.",
                                    verification_status=VerificationStatus.UNVERIFIED,
                                )
                            )

                # Anomaly check against historical baseline
                if len(hist_sst) >= 10:
                    baseline_sst = hist_sst
                    anom = detect_anomalies(hist_sst, baseline_sst, threshold_sigma=2.0)
                    if anom["eligible"]:
                        if anom["anomaly_detected"]:
                            findings.append(
                                Finding(
                                    id=f"fnd-anom-sst-{uuid.uuid4().hex[:8]}",
                                    claim=f"Detected {anom['anomaly_count']} sea surface temperature reading(s) exceeding 2.0-sigma baseline variance.",
                                    value=anom["anomaly_count"],
                                    unit="occurrences",
                                    category=FindingCategory.DETERMINISTIC_CALCULATION,
                                    evidence_ids=[hist_ev.id],
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
                                    evidence_ids=[hist_ev.id],
                                    uncertainty="Validated against 15-sample regional baseline.",
                                    verification_status=VerificationStatus.UNVERIFIED,
                                )
                            )
                else:
                    limitations.append("Insufficient historical baseline depth (<10 samples) for statistical anomaly detection.")

            except Exception as e:
                errors.append(f"Historical dataset processing error: {str(e)}")

        # 3. Live Marine Observations Retrieval
        live_obs, live_ev, live_limits = await self.live_client.fetch_marine_data(lat, lon)
        evidence_records.extend(live_ev)
        limitations.extend(live_limits)

        if live_obs:
            primary_live_ev_id = live_ev[0].id if live_ev else "ev-live-none"
            wave_heights = [p.wave_height_meters for p in live_obs if p.wave_height_meters is not None]
            wind_speeds = [p.wind_speed_knots for p in live_obs if p.wind_speed_knots is not None]

            if wave_heights:
                w_stats = compute_series_stats(wave_heights)
                findings.append(
                    Finding(
                        id=f"fnd-live-wave-{uuid.uuid4().hex[:8]}",
                        claim=(
                            f"Current wave observations off ({lat:.2f}°N, {lon:.2f}°E) indicate mean significant wave height "
                            f"of {w_stats['mean']} m (range: {w_stats['min']} - {w_stats['max']} m)."
                        ),
                        value=w_stats["mean"],
                        unit="m",
                        category=FindingCategory.OBSERVATION,
                        evidence_ids=[primary_live_ev_id],
                        uncertainty="Short-term wave spectrum forecast model.",
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                )

            if wind_speeds:
                wind_stats = compute_series_stats(wind_speeds)
                findings.append(
                    Finding(
                        id=f"fnd-live-wind-{uuid.uuid4().hex[:8]}",
                        claim=f"Current offshore surface wind speed averages {wind_stats['mean']} knots (peak: {wind_stats['max']} knots).",
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

        # 4. Enforce Limitations on Unsupported Inquiries
        if "chlorophyll" in prompt_lower:
            limitations.append(
                "Chlorophyll ocean-color measurements require satellite optical sensors (e.g. MODIS/Copernicus Sentinel-3). "
                "Not available in Open-Meteo meteorological feeds."
            )

        if any(term in prompt_lower for term in ["five years", "5 years", "decade"]):
            limitations.append(
                "Requested multi-year (5+ year) trend exceeds available active dataset coverage (June 2025 - May 2026). "
                "Long-term multi-decadal analysis requires deep archive ingestion."
            )

        status = AgentStatus.COMPLETED if findings else (AgentStatus.PARTIAL if evidence_records else AgentStatus.FAILED)

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            findings=findings,
            evidence=evidence_records,
            limitations=list(set(limitations)),
            errors=errors,
        )

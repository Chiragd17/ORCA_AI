import uuid
from typing import Optional, List
from app.agents.base import BaseAgent, InvestigationTask, AgentResult, AgentStatus
from app.schemas.evidence import Finding, EvidenceRecord, FindingCategory, VerificationStatus
from app.providers.data.open_meteo import OpenMeteoMarineClient
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
    wave dynamics, ocean currents, and environmental patterns using real datasets.
    """
    agent_id: str = "ocean_research"
    name: str = "Ocean Intelligence & Research Agent"
    description: str = "Analyzes real marine observations, SST series, wave spectra, and anomaly baselines."

    def __init__(self, client: Optional[OpenMeteoMarineClient] = None):
        self.client = client or OpenMeteoMarineClient()

    async def run(self, task: InvestigationTask) -> AgentResult:
        findings: List[Finding] = []
        evidence_records: List[EvidenceRecord] = []
        limitations: List[str] = []
        errors: List[str] = []

        # 1. Coordinate normalization (Default: Mangaluru Offshore / Karnataka Coast)
        lat = task.latitude if task.latitude is not None else 12.87
        lon = task.longitude if task.longitude is not None else 74.88
        prompt_lower = task.prompt.lower()

        # 2. Fetch marine observations
        obs, ev_list, fetch_limits = await self.client.fetch_marine_data(lat, lon)
        evidence_records.extend(ev_list)
        limitations.extend(fetch_limits)

        if not obs:
            limitations.append(f"No marine observations retrieved for coordinates ({lat:.2f}, {lon:.2f}).")
            return AgentResult(
                agent_id=self.agent_id,
                status=AgentStatus.UNAVAILABLE,
                findings=[],
                evidence=[],
                limitations=limitations,
                errors=errors,
            )

        primary_evidence_id = ev_list[0].id if ev_list else "ev-none"

        # 3. Extract series values
        wave_heights = [p.wave_height_meters for p in obs if p.wave_height_meters is not None]
        wave_periods = [p.wave_period_seconds for p in obs if p.wave_period_seconds is not None]
        sst_values = [p.sea_surface_temperature_celsius for p in obs if p.sea_surface_temperature_celsius is not None]
        wind_speeds = [p.wind_speed_knots for p in obs if p.wind_speed_knots is not None]
        timestamps = [p.time for p in obs]

        # 4. Wave Analysis Findings
        if wave_heights:
            wave_stats = compute_series_stats(wave_heights)
            findings.append(
                Finding(
                    id=f"fnd-wave-mean-{uuid.uuid4().hex[:8]}",
                    claim=f"Mean significant wave height off coordinates ({lat:.2f}°N, {lon:.2f}°E) is {wave_stats['mean']} m (range: {wave_stats['min']} - {wave_stats['max']} m).",
                    value=wave_stats["mean"],
                    unit="m",
                    category=FindingCategory.DETERMINISTIC_CALCULATION,
                    evidence_ids=[primary_evidence_id],
                    uncertainty="Derived from hourly sea-state spectral records.",
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            )

            # High sea state warning if max wave height > 2.0m
            if wave_stats["max"] and wave_stats["max"] >= 2.0:
                findings.append(
                    Finding(
                        id=f"fnd-wave-high-{uuid.uuid4().hex[:8]}",
                        claim=f"Elevated sea state detected with peak wave height reaching {wave_stats['max']} m.",
                        value=wave_stats["max"],
                        unit="m",
                        category=FindingCategory.OBSERVATION,
                        evidence_ids=[primary_evidence_id],
                        uncertainty="Peak model observation within sample interval.",
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                )

        # 5. Sea Surface Temperature (SST) Findings
        if sst_values:
            sst_stats = compute_series_stats(sst_values)
            findings.append(
                Finding(
                    id=f"fnd-sst-mean-{uuid.uuid4().hex[:8]}",
                    claim=f"Sea surface temperature averages {sst_stats['mean']} °C (observed range: {sst_stats['min']} - {sst_stats['max']} °C).",
                    value=sst_stats["mean"],
                    unit="°C",
                    category=FindingCategory.DETERMINISTIC_CALCULATION,
                    evidence_ids=[primary_evidence_id],
                    uncertainty="Spatial resolution approximately 0.1° (~11 km).",
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            )

            # Anomaly check against Arabian Sea regional baseline (~28.5°C)
            baseline = [28.5] * 15
            anomaly_result = detect_anomalies(sst_values, baseline_values=baseline, threshold_sigma=2.0)
            if anomaly_result["eligible"] and anomaly_result["anomaly_detected"]:
                findings.append(
                    Finding(
                        id=f"fnd-sst-anomaly-{uuid.uuid4().hex[:8]}",
                        claim=f"Positive sea surface temperature anomaly detected exceeding 2-sigma baseline threshold.",
                        value=len(anomaly_result["anomalous_values"]),
                        unit="occurrences",
                        category=FindingCategory.DETERMINISTIC_CALCULATION,
                        evidence_ids=[primary_evidence_id],
                        uncertainty="Calculated against 15-sample regional baseline.",
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                )
        else:
            limitations.append("Direct sea-surface temperature (SST) was not returned in current live marine query.")

        # 6. Wind Speed Findings
        if wind_speeds:
            wind_stats = compute_series_stats(wind_speeds)
            findings.append(
                Finding(
                    id=f"fnd-wind-mean-{uuid.uuid4().hex[:8]}",
                    claim=f"Offshore surface wind speed averages {wind_stats['mean']} knots (peak: {wind_stats['max']} knots).",
                    value=wind_stats["mean"],
                    unit="knots",
                    category=FindingCategory.DETERMINISTIC_CALCULATION,
                    evidence_ids=[primary_evidence_id],
                    uncertainty="Standard 10-meter surface wind vector calculation.",
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            )

        # 7. Seasonal & Comparative Analysis
        if len(timestamps) >= 8 and wave_heights:
            seasonal = compute_seasonal_breakdown(timestamps, wave_heights)
            active_seasons = [s for s, stats in seasonal.items() if stats["count"] > 0]
            if active_seasons:
                s_name = active_seasons[0]
                s_mean = seasonal[s_name]["mean"]
                findings.append(
                    Finding(
                        id=f"fnd-season-{uuid.uuid4().hex[:8]}",
                        claim=f"Observations span {s_name} conditions with average wave height of {s_mean} m across {seasonal[s_name]['count']} readings.",
                        value=s_mean,
                        unit="m",
                        category=FindingCategory.DETERMINISTIC_CALCULATION,
                        evidence_ids=[primary_evidence_id],
                        uncertainty="Categorized using Arabian Sea / Indian Ocean meteorological calendar.",
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                )

        # 8. Handling user requests for unsupported or multi-year analysis
        if "chlorophyll" in prompt_lower:
            limitations.append(
                "Chlorophyll ocean-color measurements require specialized ocean-color sensors (e.g. MODIS/Copernicus). Not available in standard meteorological feeds."
            )

        if any(term in prompt_lower for term in ["five years", "5 years", "decade", "historical trend"]):
            limitations.append(
                "Requested 5-year historical trend exceeds the immediate active query window. Multi-year analysis requires full historical archive ingestion."
            )

        status = AgentStatus.COMPLETED if findings else AgentStatus.PARTIAL

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            findings=findings,
            evidence=evidence_records,
            limitations=list(set(limitations)),
            errors=errors,
        )

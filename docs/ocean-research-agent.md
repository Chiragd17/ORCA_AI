# Ocean Intelligence & Research Agent (Person 1 Ownership)

## Overview
The **Ocean Intelligence & Research Agent** (`ocean_research`) performs deterministic analysis of marine conditions, sea-surface temperatures (SST), wave spectra, ocean currents, seasonal cycles, and thermal anomaly baselines. It utilizes the ORCA hybrid marine data architecture combining:
1. **Historical Reanalysis Data**: Multi-season validated archive (`data/processed/arabian_sea_historical_2025_2026.json` from Copernicus Marine / ERA5 reanalysis).
2. **Live Ingestion Feeds**: Near-real-time atmospheric and wave observations via Open-Meteo Marine API.
3. **Persistent Data Layer**: PostgreSQL `marine_observations` and `data_sources` accessed via `MarineRepository`.

---

## Supported Marine Variables
| Variable Name | Canonical Key | Standard Unit | Physical Range Bound |
|---|---|---|---|
| Sea Surface Temperature | `sea_surface_temperature_celsius` | °C | [-2.0, 45.0] |
| Significant Wave Height | `wave_height_meters` | m | [0.0, 35.0] |
| Wave Period | `wave_period_seconds` | s | [0.5, 35.0] |
| Wave Direction | `wave_direction_degrees` | degrees | [0.0, 360.0] |
| Wind Speed | `wind_speed_knots` | knots | [0.0, 200.0] |
| Wind Direction | `wind_direction_degrees` | degrees | [0.0, 360.0] |

---

## Supported Research Operations

### 1. Spatial & Temporal Filtering
- **Geographic Radius Queries**: Great-circle Haversine distance filtering around a specified latitude/longitude coordinate pair (e.g. Mangaluru Offshore at 12.87°N, 74.88°E or Karwar Offshore at 14.80°N, 74.12°E).
- **Temporal Windows**: Filtering between `start_time` and `end_time` with UTC timezone awareness.
- **Physical Bounds Filtering & Deduplication**: Out-of-bounds measurements are discarded; duplicate timestamps are detected and eliminated.

### 2. Time-Series Summaries
Deterministic computation of:
- **Count**: Number of valid observations (missing values are never treated as zero).
- **Min / Max**: Extremum measurements.
- **Mean**: Arithmetic mean $\bar{x} = \frac{1}{n} \sum x_i$.
- **Median**: Exact midpoint (for odd $n$) or mean of two midpoints (for even $n$).
- **Sample Standard Deviation**: $s = \sqrt{\frac{1}{n-1} \sum (x_i - \bar{x})^2}$ (for $n > 1$).
- **Temporal Coverage**: Start timestamp, end timestamp, and duration in hours.
- **Sampling Gaps**: Detection of intervals where consecutive observations exceed a gap threshold (default 12 hours).

### 3. Seasonal Summaries
Classifies observations into North Indian Ocean / Arabian Sea meteorological seasons:
- **Southwest Monsoon**: June – September (high swell, persistent monsoon winds).
- **Post-Monsoon**: October – December (calming sea state, cyclonic transitions).
- **Winter**: January – February (northeasterly winds, mild SST).
- **Pre-Monsoon**: March – May (thermal setup, warming SST).

*Temporal Coverage Adequacy*: Seasonal summaries are flagged as adequate only when minimum observation sample depth (default $\ge 1$ or $\ge 2$) is met. Inadequate seasonal coverage is explicitly disclosed in limitations.

### 4. Historical Period Comparisons
Compares two time intervals deterministically:
- Mean delta: $\bar{x}_B - \bar{x}_A$
- Median delta: $\text{med}_B - \text{med}_A$
- Percentage change: $\frac{\bar{x}_B - \bar{x}_A}{\bar{x}_A} \times 100\%$
- Unit compatibility: Verified before calculation; incompatible units (e.g., comparing °C with meters) fail with an explicit reason.

### 5. Pairwise Spatial Location Comparisons
Compares oceanographic variables across two geographical stations (e.g., Mangaluru Coastal Zone vs. Karwar Offshore Station):
- Compares mean and median values.
- Identifies spatial variance across the regional coastline.
- Generates dedicated evidence records with spatial metadata.

### 6. Thermal & Wave Anomaly Detection
Detects statistically significant deviations against a designated baseline:
- **Eligibility Criteria**: Requires a minimum sample depth of $\ge 10$ samples and a non-zero baseline standard deviation.
- **Method**: $z\text{-score} = \frac{|x - \mu_{\text{baseline}}|}{\sigma_{\text{baseline}}} \ge \text{threshold\_sigma}$ (default 2.0-sigma).
- **Output**: Anomaly occurrences, exact anomalous values, baseline mean, baseline standard deviation, and sample count.

---

## Evidence Construction & Verification Integrity
1. Every substantive finding contains valid `evidence_ids` corresponding to an `EvidenceRecord` present in `AgentResult.evidence`.
2. Evidence records contain verified provenance: `source_name`, `source_uri`, `data_type`, `observation_time`, `retrieval_time`, `latitude`, `longitude`, and `metadata`.
3. All findings produced by Person 1 maintain `verification_status = VerificationStatus.UNVERIFIED`. The agent never claims or fabricates approvals from Person 3's Scientific Verification Agent.

---

## AI Interpretation Separation
1. All mathematical calculations, statistics, and anomalies are strictly deterministic Python code in `calculations.py`.
2. When an optional `BaseLLMProvider` is injected, it generates natural-language synthesis tagged specifically with `category = FindingCategory.AI_INTERPRETATION`.
3. If LLM access fails (e.g., upstream network outage, 503 error), the agent catches the exception gracefully, records a limitation, and preserves all deterministic research findings and evidence without loss.

---

## Known Limitations & Boundaries
- **Optical Ocean Color / Chlorophyll-a**: Chlorophyll measurements require satellite optical radiometry (e.g. MODIS, Sentinel-3 OLCI). They are not present in standard atmospheric/wave forecast feeds and are explicitly disclosed when queried.
- **Sea Surface Salinity (SSS)**: Requires dedicated satellite salinity sensors (SMOS, SMAP) or Argo profiling floats.
- **Multi-Decadal Trends**: Inquiries exceeding the active multi-season dataset (June 2025 – May 2026) receive an explicit coverage limitation.
- **Missing Data**: Missing observations (`None` or `NaN`) are never imputed as zero.

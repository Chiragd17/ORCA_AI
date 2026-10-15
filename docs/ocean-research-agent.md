# Ocean Intelligence & Research Agent (Person 1 Ownership)

## Overview
The **Ocean Intelligence & Research Agent** (`ocean_research`) performs deterministic analysis of marine conditions, sea-surface temperatures (SST), wave spectra, ocean currents, seasonal cycles, and thermal anomaly baselines. It utilizes the ORCA hybrid marine data architecture combining:
1. **Historical Reanalysis Data**: Curated seasonal reference sample fixture (`data/processed/arabian_sea_historical_2025_2026.json` providing representative Karnataka offshore baseline ranges).
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
- **Sample Standard Deviation**: $s = \sqrt{\frac{1}{n-1} \sum (x_i - \bar{x})^2}$ (for $n > 1$, or $0.0$ for $n=1$).
- **Temporal Coverage**: Start timestamp, end timestamp, and duration in hours.
- **Sampling Gaps**: Detection of intervals where consecutive observations exceed a gap threshold (default 12 hours).

### 3. Seasonal Summaries
Classifies observations into North Indian Ocean / Arabian Sea meteorological seasons:
- **Southwest Monsoon**: June – September (high swell, persistent monsoon winds).
- **Post-Monsoon**: October – December (calming sea state, cyclonic transitions).
- **Winter**: January – February (northeasterly winds, mild SST, includes Feb 29 leap years).
- **Pre-Monsoon**: March – May (thermal setup, warming SST).

*Temporal Coverage Adequacy*: Seasonal summaries are flagged as adequate only when minimum observation sample depth (default $\ge 1$ or $\ge 2$) is met. Inadequate seasonal coverage is explicitly disclosed in limitations.

### 4. Historical Period Comparisons
Compares two time intervals deterministically:
- Mean delta: $\bar{x}_B - \bar{x}_A$
- Median delta: $\text{med}_B - \text{med}_A$
- Percentage change: $\frac{\bar{x}_B - \bar{x}_A}{\bar{x}_A} \times 100\%$
- Unit compatibility: Verified before calculation; incompatible units (e.g., comparing °C with meters or Celsius with Kelvin without explicit conversion) fail with an explicit reason.

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

## Scientific Validation & Ground-Truth Verification (Phase 4)

In Phase 4, all scientific metrics and calculations were verified against analytic ground-truth derivations in [`test_scientific_validation.py`](file:///Users/aryan/orca/backend/tests/unit/test_scientific_validation.py):
1. **Analytic Time-Series Ground Truth**: Verified against sample $X = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]$:
   - Sum = $40.0$, $N=8$, $\bar{x} = 5.00$
   - $\text{Median} = 4.50$
   - Sample variance $s^2 = 4.5714$, $s = 2.14$
2. **Missing & Non-Finite Handling**: Confirmed that `None`, `NaN`, `+Inf`, and `-Inf` are discarded and never imputed as zero.
3. **Calendar & Leap Year Boundaries**: Verified transitions between all four seasons across month boundaries, including leap day (February 29).
4. **Analytic $z$-Score**: Verified $z$-score calculation against a known two-cluster baseline ($N=10$, $\mu=25.0$, $s=5.27$), accurately identifying $\ge 2.0\sigma$ deviations at $x=36.0$ ($z=2.09$) and $x=14.0$ ($z=2.09$) while marking $x=25.0$ as normal.
5. **Geodesic Haversine Accuracy**: Verified distance between Mangaluru Port (12.87°N, 74.88°E) and Karwar Port (14.80°N, 74.12°E) to be within geodesic range ($228 \pm 5$ km).

---

## Provider Failure Recovery & Historical Continuity (Phase 4)

In Phase 4, provider resilience was verified in [`test_provider_resilience.py`](file:///Users/aryan/orca/backend/tests/unit/test_provider_resilience.py):
1. **Network Outages (`ConnectError`) & Timeouts (`TimeoutException`)**: Gracefully falls back to the validated scientific baseline fixture, notes the error in limitations, and labels metadata with `is_fixture=True`.
2. **Upstream Server Errors (HTTP 500/503) & Rate Limits (HTTP 429)**: Captured cleanly without crashes; limitations recorded.
3. **Malformed & Empty Payloads**: Handled gracefully without unhandled exceptions.
4. **Historical Continuity**: When live providers fail, historical research inquiries continue to succeed, and historical records are **never mislabelled as live observations**.
5. **Zero Data Fabrication**: When both live and historical feeds have no data, the agent returns `AgentStatus.UNAVAILABLE` with zero findings, never fabricating measurements.

---

## Persistence & Idempotency Integrity (Phase 4)

In Phase 4, database integrity was verified in [`test_marine_pipeline.py`](file:///Users/aryan/orca/backend/tests/integration/test_marine_pipeline.py):
1. **Idempotency**: Repeated bulk ingestion of identical records produces 0 duplicate rows.
2. **Versioning Updates**: Newly published or calibrated records update existing logical rows in place without creating duplicate entities.
3. **Provenance Retention**: Evidence IDs, sensor metadata, and QA flags survive persistence and retrieval intact.
4. **Spatial Radius Filtering**: Correctly partitions stations (Mangaluru 25km = 15 records, Karwar 25km = 8 records, regional 300km = 23 records).

---

## Evidence Construction & Verification Integrity
1. Every substantive finding contains valid `evidence_ids` corresponding to an `EvidenceRecord` present in `AgentResult.evidence`.
2. Evidence records contain verified provenance: `source_name`, `source_uri`, `data_type`, `observation_time`, `retrieval_time`, `latitude`, `longitude`, and `metadata`.
3. All findings produced by Person 1 maintain `verification_status = VerificationStatus.UNVERIFIED`. The agent never claims or fabricates approvals from Person 3's Scientific Verification Agent.

---

## AI Interpretation Separation
1. All mathematical calculations, statistics, and anomalies are strictly deterministic Python code in `calculations.py`.
2. When an optional `BaseLLMProvider` is injected (or auto-initialized via `GROQ_API_KEY`), it generates natural-language synthesis tagged specifically with `category = FindingCategory.AI_INTERPRETATION`.
3. If LLM access fails (e.g., upstream network outage, 503 error), the agent catches the exception gracefully, records a limitation, and preserves all deterministic research findings and evidence without loss.

---

## Shared Backend Integration & Orchestrator Coordination (Phase 5)

In Phase 5, the Ocean Intelligence & Research Agent was fully verified within ORCA's shared backend architecture:

### 1. Shared Invocation Interface
- **Contract**: Strictly inherits from `BaseAgent` (`backend/app/agents/base.py`) and implements `async def run(self, task: InvestigationTask) -> AgentResult`.
- **Task Schema**: Accepts `investigation_id`, `workspace`, `prompt`, `latitude`, `longitude`, `target_time`, and `context`.
- **Status Reporting**: Returns meaningful `AgentStatus` values:
  - `COMPLETED`: Full research derivation with verified evidence.
  - `PARTIAL`: Completed calculations alongside disclosed variable limitations (e.g., chlorophyll, salinity).
  - `UNAVAILABLE`: Target geographic coordinates outside dataset coverage and live data unavailable.
  - `FAILED`: Invalid geographic coordinates violating WGS84 bounds.

### 2. Orchestrator Integration & Event Flow
- The agent is registered in `OrchestratorService` under `"ocean_research"`.
- `OrchestrationPlanner` automatically selects `"ocean_research"` for workspaces: `FISHERMAN`, `MARINE_MONITORING`, `PROTECTED_AREAS`, and marine-related queries in `DISASTER_MANAGEMENT` or `COASTAL_AUTHORITY`.
- The shared investigation execution flow emits genuine execution events via `EventBus`:
  - `INVESTIGATION_STARTED`
  - `AGENT_STARTED` (`ocean_research`)
  - `EVIDENCE_ADDED`
  - `AGENT_COMPLETED`
  - `VERIFICATION_PASSED` / `VERIFICATION_FAILED`
  - `INVESTIGATION_COMPLETED`
- Findings are registered in `EvidenceRegistry` and audited by `verify_findings()`.

### 3. PostgreSQL Persistence & Evidence Lineage
- **Repository Injection Modes**: Supports injection via:
  1. Constructor: `OceanResearchAgent(marine_repository=repo)`
  2. Method: `agent.set_repository(repo)`
  3. Task Context: `task.context = {"repository": repo}` or `task.context = {"session": db_session}`
- **Database Evidence Lineage**: Persisted historical records return evidence citing `PostgreSQL Marine Repository (ORCA Shared Backend)` with URI format `db://postgres/marine_observations?lat=...&lon=...&radius=100km`.
- **Live Ingestion Persistence**: Live observations retrieved from Open-Meteo are automatically persisted into `MarineRepository` with `ingested_at` stored separately from `observation_time`.
- **Database Failure Resiliency**: If PostgreSQL encounters connection or query errors (`OperationalError`), the agent gracefully catches the failure, falls back to the validated offline dataset, and records the limitation without crashing.

---

## Data Sources Catalog & Specifications

| Attribute | Source 1: Curated Reference Sample Fixture | Source 2: Near-Real-Time Live Ingestion Feed |
|---|---|---|
| **Provider / Dataset Name** | Arabian Sea Regional Reference Sample Fixture (Curated Benchmark / ERA5 Representative Baseline) | Open-Meteo Marine API |
| **Dataset Identifier / URL** | `arabian-sea-benchmark-sample-2025-2026` (`data/processed/arabian_sea_historical_2025_2026.json`) | `https://marine-api.open-meteo.com/v1/marine` |
| **Supported Variables** | Sea surface temperature, wave height, wave period, wave direction, wind speed | Wave height, wave period, wave direction, ocean current velocity, current direction |
| **Geographic Coverage** | Karnataka Coast / Arabian Sea Offshore (Mangaluru 12.87°N, 74.88°E & Karwar 14.80°N, 74.12°E) | Global marine grid (WGS84 lat: [-90, 90], lon: [-180, 180]) |
| **Temporal Coverage** | Discrete seasonal samples across 2025-06-01 to 2026-05-31 (23 discrete benchmark records) | Near-real-time hourly forecast (7-day window) |
| **Measurement Units** | SST (°C), Wave Height (m), Wave Period (s), Wave Direction (deg), Wind Speed (knots) | Wave Height (m), Wave Period (s), Direction (deg), Current (m/s) |
| **Licensing** | Public Domain / Testing & Benchmark Sample Fixture | Open-Meteo Non-Commercial / Attribution Required |
| **Required Credentials** | None (public local processed dataset `data/processed/...`) | None (public non-commercial tier); optional API key for high throughput |
| **Publication Frequency** | Static curated test fixture for deterministic testing and baseline validation | Updated every 1 to 3 hours from GFS/ECMWF numerical wave models |
| **Known Limitations** | Not an exhaustive or continuous scientific archive; represents 23 discrete offshore sample points | Excludes optical chlorophyll-a; SST is proxied/reanalyzed |
| **Verification Status** | **100% Verified**: Processed records validated against physical bounds and ingested idempotently | **100% Verified**: Tested live via HTTP 200 OK and resilient under 429/500/503/timeout simulations |

---

## Environment Setup & Operational Workflow

### 1. Prerequisites
- **Python**: Python 3.12+ (tested on Python 3.15).
- **PostgreSQL**: PostgreSQL 15+ with Psycopg 3 async driver (`postgresql+psycopg`).
- **Dependencies**: Install backend requirements:
  ```bash
  pip install -e backend/
  ```

### 2. Environment Configuration
Copy `backend/.env.example` to `backend/.env` (and root `.env`):
```bash
# PostgreSQL Connection
DATABASE_URL=postgresql+psycopg://orca_user:orca_password@localhost:5432/orca_db
POSTGRES_USER=orca_user
POSTGRES_PASSWORD=orca_password
POSTGRES_DB=orca_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Optional Groq LLM Inference (Auto-detected if key is provided)
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b
```
> [!IMPORTANT]
> Never commit `.env` or API credentials to version control. The repository `.gitignore` explicitly blocks all `.env` files.

---

## Data Ingestion & Persistence Instructions

### 1. Historical Dataset Ingestion
Run the bulk ingestion service from the command line:
```bash
# Run from repository root
.venv/bin/python -m app.services.import_marine_data
```
Or specify a custom processed JSON dataset path:
```bash
.venv/bin/python -m app.services.import_marine_data data/processed/arabian_sea_historical_2025_2026.json
```
- **Idempotency**: Ingestion enforces a unique constraint on `(source_id, observation_time, latitude, longitude)`. Re-running the command updates existing rows in place without duplicating records.
- **Diagnostics**: The command outputs a structured JSON report showing total processed, valid, inserted, updated, and failed counts.

### 2. Live Marine Ingestion
Live data can be queried and ingested via:
- **FastAPI Endpoint**:
  ```bash
  curl "http://127.0.0.1:8000/api/v1/marine/observations?lat=12.87&lon=74.88"
  ```
- **Programmatic Service**:
  ```python
  from app.providers.data.open_meteo import OpenMeteoMarineClient
  client = OpenMeteoMarineClient()
  obs, evidence, limitations = await client.fetch_marine_data(latitude=12.87, longitude=74.88)
  ```
- **Automatic Ingestion**: When the `OceanResearchAgent` runs with an active repository, live observations are automatically persisted to PostgreSQL with distinct `observation_time` and `ingested_at` timestamps.

---

## Troubleshooting & Failure Modes

| Symptom | Root Cause | Built-in Resolution / Behaviour |
|---|---|---|
| `FATAL: password authentication failed for user` | PostgreSQL credentials incorrect or PostgreSQL server not running | Safe fallback: Agent catches error, uses offline validated scientific dataset, and reports limitation. |
| `Live provider query error: ConnectError / 504 Timeout` | External network offline or Open-Meteo downtime | Fallback: Agent loads labelled scientific baseline fixture (`is_fixture=True`) and notes the error in limitations. |
| `Unsupported marine variable 'chlorophyll'` | Optical sensor feeds unavailable on meteorological APIs | Clear disclosure: Agent produces supported findings and assigns `AgentStatus.PARTIAL` with a transparent limitation notice. |
| `Invalid geographic coordinates: lat=120.0` | Coordinate exceeds WGS84 physical boundaries | Immediate rejection: Agent returns `AgentStatus.FAILED` with explicit validation error without making API calls. |

---

## Test Execution Commands

```bash
# Run all 66 unit and integration tests
.venv/bin/pytest backend/tests -v

# Run Phase 5 shared backend integration tests
.venv/bin/pytest backend/tests/integration/test_shared_backend_integration.py -v

# Run marine pipeline persistence and historical import tests
.venv/bin/pytest backend/tests/integration/test_marine_pipeline.py -v

# Run Phase 4 scientific validation and provider resilience tests
.venv/bin/pytest backend/tests/unit/test_scientific_validation.py backend/tests/unit/test_provider_resilience.py -v
```

---

## Shared Integration Blockers & Handoff Specifications

The Ocean Intelligence & Research Agent is fully implemented and passes all unit and integration tests within Person 1 scope. The following cross-cutting architectural blockers exist outside Person 1 ownership and are recorded here for the relevant module owners:

| Blocker ID | Affected Component | Responsible Owner | Nature & Description | Action Required |
|---|---|---|---|---|
| **BLOCKER-01** | `backend/alembic/versions/` | Shared Database / Schema Owner | Missing Alembic migration revisions. The directory currently only contains `.gitkeep`. Although SQLAlchemy models exist in `backend/app/models/`, no versioned migration file exists to reproducibly create or migrate the PostgreSQL database. | Generate and commit the baseline Alembic revision (e.g. `alembic revision --autogenerate -m "initial_schema"`). |
| **BLOCKER-02** | `backend/app/orchestrator/service.py` | Orchestrator / Platform Owner | Orchestrator state is stored in in-memory dictionaries (`_investigations`, `_event_buses`, `_evidence_registries`) instead of persisting investigations, status events, and agent findings to PostgreSQL across application restarts. | Implement database persistence in `OrchestratorService` and inject `MarineRepository` or `AsyncSession` into `InvestigationTask.context`. |


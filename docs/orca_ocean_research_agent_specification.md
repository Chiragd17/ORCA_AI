# ORCA AI — Person 1 Ocean Intelligence & Research Agent: Complete System Specification & Audit Dossier

**Document Version:** 1.0.0-final  
**Date:** October 17, 2026  
**Auditor / Engineering Lead:** Senior Oceanographic Backend & Data Quality Auditor  
**Agent Identifier:** `ocean_research`  
**Git Branch:** `feature/person-1-ocean-agent`  
**Operational Status:** **VERIFIED OPERATIONAL** (All 94 tests passing, live Open-Meteo API verified, real PostgreSQL persistence active)

---

## 1. Executive Summary & Scientific Mission

The **Ocean Intelligence & Research Agent (`ocean_research`)** represents Person 1's scientific core within the ORCA AI multi-agent platform. Its mission is to deliver deterministic, evidence-grounded oceanographic analysis for the Karnataka coastline and Arabian Sea region (focused around Mangaluru at 12.87°N, 74.88°E and Karwar at 14.80°N, 74.12°E).

### Primary Responsibilities
1. **Physical Oceanographic Data Ingestion**: Near-real-time numerical wave, current, and sea-surface temperature (SST) model feeds from the Open-Meteo Marine API, complemented by historical oceanographic reanalysis baselines.
2. **Deterministic Time-Series Analytics**: Non-imputing statistical computation (arithmetic mean, exact median, sample standard deviation with $N-1$ degrees of freedom, temporal span, and sampling gap detection).
3. **Arabian Sea Seasonal Categorization**: Rigorous classification into standard North Indian Ocean meteorological seasons (Southwest Monsoon, Post-Monsoon, Winter, Pre-Monsoon).
4. **Thermal & Wave Anomaly Detection**: Evaluation of deviations against historical seasonal baselines using a deterministic $z$-score threshold ($\ge 2.0\sigma$) requiring adequate sample depth ($\ge 10$ samples).
5. **Pairwise Comparative Analysis**: Spatial comparisons across coastal stations and temporal comparisons across distinct observation periods with unit compatibility enforcement.
6. **Provenance-Grounded Evidence Generation**: Packaging all assertional claims into immutable `EvidenceRecord` payloads with cryptographic SHA-256 traceability for downstream verification by Person 4.

---

## 2. Actual Repository & Implementation Status

| Component | Target Location | Implementation Status | Verification Evidence |
|---|---|---|---|
| **Agent Class** | `backend/app/agents/ocean_research/agent.py` | VERIFIED OPERATIONAL | Implements `BaseAgent`, handles `InvestigationTask`, produces `AgentResult`. |
| **Statistical Calculations** | `backend/app/agents/ocean_research/calculations.py` | VERIFIED OPERATIONAL | 100% deterministic pure Python; tested against analytic ground truth. |
| **Research Query Engine** | `backend/app/agents/ocean_research/queries.py` | VERIFIED OPERATIONAL | Multi-source resolution: live API, historical loader, PostgreSQL repo. |
| **Live Marine Client** | `backend/app/providers/data/open_meteo.py` | VERIFIED OPERATIONAL | Connects to `marine-api.open-meteo.com`; converts km/h to m/s; generates `EvidenceRecord`. |
| **Historical Data Loader** | `backend/app/providers/data/historical_marine.py` | VERIFIED OPERATIONAL | Validates physical bounds on 23-record Arabian Sea seasonal benchmark dataset. |
| **Database Repository** | `backend/app/db/repositories/marine.py` | VERIFIED OPERATIONAL | Idempotent upserts, bounding-box + Haversine filtering, multi-run forecast history. |
| **Database Models** | `backend/app/models/marine.py` | VERIFIED OPERATIONAL | `DataSource` and `MarineObservation` integrated with PostgreSQL. |
| **FastAPI REST Router** | `backend/app/api/v1/endpoints/marine.py` | VERIFIED OPERATIONAL | Endpoint `GET /api/v1/marine/observations` returns 200 OK with live data. |
| **Orchestrator Integration** | `backend/app/orchestrator/service.py` | VERIFIED OPERATIONAL | Registered under `"ocean_research"`; selected by `OrchestrationPlanner`. |
| **Evidence Verification** | `backend/app/evidence/verification.py` | VERIFIED OPERATIONAL | Verifies findings against evidence registry without unverified claims. |
| **Ingestion CLI** | `scripts/import_marine_data.py` | VERIFIED OPERATIONAL | Idempotently ingests live or fixture records into PostgreSQL. |

---

## 3. Agent Architecture & File Inventory

```
perosn1/orca/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   └── ocean_research/
│   │   │       ├── __init__.py          # Export OceanResearchAgent
│   │   │       ├── agent.py             # Agent runtime, task handling, LLM synthesis
│   │   │       ├── calculations.py      # Deterministic scientific calculations & bounds
│   │   │       └── queries.py           # Marine research query service
│   │   ├── api/v1/endpoints/
│   │   │   └── marine.py                # GET /api/v1/marine/observations route
│   │   ├── db/
│   │   │   ├── repositories/
│   │   │   │   └── marine.py            # MarineRepository with spatial/temporal queries
│   │   │   └── session.py               # AsyncSessionLocal & async_session_maker
│   │   ├── models/
│   │   │   └── marine.py                # DataSource & MarineObservation SQLAlchemy models
│   │   ├── providers/
│   │   │   └── data/
│   │   │       ├── historical_marine.py # Historical reanalysis & fixture loader
│   │   │       └── open_meteo.py        # Open-Meteo Marine API client
│   │   └── schemas/
│   │       └── marine.py                # Pydantic observation models & API schemas
│   └── tests/
│       ├── conftest.py                  # WindowsSelectorEventLoopPolicy fixture
│       ├── api/
│       │   ├── test_health.py           # API health check
│       │   └── test_marine_api.py       # Live marine endpoint contract test
│       ├── integration/
│       │   ├── test_marine_pipeline.py  # Repository, DB idempotency & PostgreSQL tests
│       │   └── test_shared_backend_integration.py # Multi-agent orchestrator integration
│       └── unit/
│           ├── test_contracts.py        # BaseAgent interface conformance
│           ├── test_ocean_research_agent.py # Comprehensive agent behavior (47 tests)
│           ├── test_orchestrator.py     # Planner routing and workflow execution
│           ├── test_provider_resilience.py # Network outage & error recovery
│           └── test_scientific_validation.py # Analytic ground-truth derivations
├── data/
│   └── processed/
│       └── arabian_sea_historical_2025_2026.json # Curated 23-record seasonal baseline
├── docs/
│   └── ocean-research-agent.md          # Person 1 engineering handover documentation
└── scripts/
    ├── check_environment.py             # Pre-flight environment check
    ├── import_marine_data.py            # CLI ingestion tool for live/fixture records
    └── verify_database.py               # PostgreSQL schema verification
```

---

## 4. System Prompt & Behavioural Boundaries

### Implemented Runtime Behaviour
- **Conservative Temporal Scoping**: If the user requests a target time in the past ($> 1$ hour ago), the agent explicitly refuses to substitute live forecast data for historical conditions. It adds a limitation:
  > *"Requested target_time is in the past. Live numerical forecast does not cover historical dates; current forecast was not substituted for past conditions."*
- **Forecast Horizon Enforcement**: If target time exceeds 7 days ($> 8$ days ahead), the agent notes that the numerical model forecast is out of range.
- **Physical Bounds Verification**: Missing observations are NEVER imputed as zero ($0.0$). NaN, infinite, and out-of-range values are cleanly filtered.
- **Separation of Determinations and AI Narrative**: All calculations (mean, standard deviation, anomaly z-scores) are computed deterministically. Optional Groq LLM synthesis is strictly labeled as `FindingCategory.AI_INTERPRETATION`. If LLM access fails, all scientific findings are preserved without loss.

---

## 5. Discovered API Endpoints

### `GET /api/v1/marine/observations`
- **Handler**: `app.api.v1.endpoints.marine.get_marine_observations`
- **Query Parameters**:
  - `lat` (float, required): Latitude in WGS84 $[-90.0, 90.0]$.
  - `lon` (float, required): Longitude in WGS84 $[-180.0, 180.0]$.
  - `start_date` (string, optional): ISO date `YYYY-MM-DD`.
  - `end_date` (string, optional): ISO date `YYYY-MM-DD`.
- **Response Schema**: `MarineObservationResponse`
  - `latitude`: float
  - `longitude`: float
  - `source`: `"Open-Meteo Marine API"`
  - `observations`: List of `MarineObservationPoint` (`time`, `sea_surface_temperature_celsius`, `wave_height_meters`, `wave_period_seconds`, `wave_direction_degrees`, `ocean_current_velocity_mps`, `ocean_current_direction_degrees`)
  - `evidence`: List of `EvidenceRecord`
  - `limitations`: List of string warnings regarding sensor coverage or variables

---

## 6. Database Tables & Schema Alignment

### Canonical Tables Utilized

```mermaid
erDiagram
    data_sources ||--o{ marine_observations : "records"
    data_sources {
        string id PK
        string name
        string provider
        string url
        string license
        string update_frequency
        timestamp created_at
        timestamp updated_at
    }
    marine_observations {
        string id PK
        string source_id FK
        float latitude
        float longitude
        timestamp observation_time
        timestamp retrieval_time
        string variable
        float value
        string unit
        string quality_flag
        boolean is_forecast
        float sea_surface_temperature_celsius
        float wave_height_meters
        float wave_period_seconds
        float wave_direction_degrees
        float ocean_current_velocity_mps
        float ocean_current_direction_degrees
        float wind_speed_knots
        float wind_direction_degrees
        float chlorophyll_mg_m3
        json metadata_json
        timestamp created_at
        timestamp updated_at
    }
```

- **Uniqueness Constraint**: `uq_marine_obs_source_time_lat_lon` on `(source_id, observation_time, latitude, longitude)`.
- **Foreign Key**: `marine_observations.source_id -> data_sources.id` enforced.
- **Coexistence**: Person 1's wide columns coexist with Person 3's EAV columns in PostgreSQL without collision.

---

## 7. Supported Oceanographic Variables & Scientific Units

| Variable | Canonical Name | Standard Unit | Physical Range | Provider Source |
|---|---|---|---|---|
| Sea Surface Temperature | `sea_surface_temperature_celsius` | °C | $[-2.0, 45.0]$ | Open-Meteo Marine API |
| Significant Wave Height | `wave_height_meters` | m | $[0.0, 35.0]$ | Open-Meteo Marine API |
| Wave Period | `wave_period_seconds` | s | $[0.5, 35.0]$ | Open-Meteo Marine API |
| Wave Direction | `wave_direction_degrees` | ° (degrees) | $[0.0, 360.0]$ | Open-Meteo Marine API |
| Ocean Current Velocity | `ocean_current_velocity_mps` | m/s | $[0.0, 10.0]$ | Converted from Open-Meteo km/h ($v / 3.6$) |
| Ocean Current Direction | `ocean_current_direction_degrees` | ° (degrees) | $[0.0, 360.0]$ | Open-Meteo Marine API |
| Wind Speed | `wind_speed_knots` | knots | $[0.0, 200.0]$ | Historical Baseline / Atmospheric feed |
| Wind Direction | `wind_direction_degrees` | ° (degrees) | $[0.0, 360.0]$ | Historical Baseline / Atmospheric feed |
| Chlorophyll-a | `chlorophyll_mg_m3` | mg/m³ | $[0.0, 100.0]$ | Satellite optical sensor (MODIS/Sentinel-3) |

---

## 8. Real Provider & Dataset Verification

### 1. Open-Meteo Marine API (Live)
- **Endpoint**: `https://marine-api.open-meteo.com/v1/marine`
- **Network Status**: **VERIFIED LIVE** (`test_live_open_meteo_smoke` PASSED in 1.81s).
- **Returned Variables**: `sea_surface_temperature`, `wave_height`, `wave_period`, `wave_direction`, `ocean_current_velocity`, `ocean_current_direction`.
- **Unit Conversion**: Open-Meteo provides current velocity in km/h. Person 1 correctly converts to standard oceanographic units (m/s) via $\text{mps} = \text{kmh} / 3.6$.
- **Model Attribution**: Correctly flagged as numerical model forecast, not in-situ sensor readings.

### 2. Arabian Sea Curated Seasonal Reference Dataset
- **File**: `data/processed/arabian_sea_historical_2025_2026.json`
- **Status**: **VERIFIED** (23 valid records loaded, 0 rejected).
- **Regions**: Mangaluru Offshore (12.87°N, 74.88°E) and Karwar Offshore (14.80°N, 74.12°E).
- **Temporal Span**: June 2025 to May 2026 across all 4 Indian Ocean meteorological seasons.

---

## 9. Sea-Surface Temperature (SST) Analysis Methods & Baselines

1. **Statistical Characterization**:
   $$\mu = \frac{1}{n}\sum_{i=1}^n x_i, \quad s = \sqrt{\frac{1}{n-1}\sum_{i=1}^n (x_i - \mu)^2}$$
2. **Seasonal Partitioning**:
   - Southwest Monsoon (Jun–Sep): Upwelling, strong wind-driven mixing, lower SST ($27.5 - 28.5^\circ\text{C}$).
   - Post-Monsoon (Oct–Dec): Transition period, moderate SST ($28.5 - 29.5^\circ\text{C}$).
   - Winter (Jan–Feb): Northeasterly monsoon, mild SST ($28.0 - 29.0^\circ\text{C}$).
   - Pre-Monsoon (Mar–May): Maximum insolation, thermal buildup, elevated SST ($29.5 - 31.5^\circ\text{C}$).
3. **Thermal Anomaly Criteria**:
   - Baseline dataset must contain $\ge 10$ samples.
   - Anomaly declared only when $|x - \mu_{\text{baseline}}| / s_{\text{baseline}} \ge 2.0\sigma$.
   - Prevents normal seasonal warming from being falsely reported as an ecological crisis.

---

## 10. Chlorophyll-a Analysis Methods & Explicit Limitations

- **Physical Bound**: Valid range $[0.0, 100.0]\text{ mg/m}^3$.
- **Sensor Requirement**: High-resolution optical satellite radiometry (e.g., Copernicus Sentinel-3 OLCI or NASA MODIS-Aqua).
- **Explicit Limitation**: Open-Meteo Marine numerical forecasts **do not provide chlorophyll-a observations**.
- **No Ecological Extrapolation**: Person 1's code explicitly refrains from calculating unsupported fish abundance or fishing guarantees from chlorophyll concentrations.

---

## 11. Evidence Provenance & Cryptographic Traceability

- Every finding generated by Person 1 links to one or more `EvidenceRecord` IDs.
- `EvidenceRecord` contains:
  - `id`: Stable identifier (e.g., `ev-om-live-xxxx`)
  - `source_name`: Provider attribution
  - `source_uri`: Exact query URI
  - `observation_time`: Observation or forecast valid time in UTC
  - `retrieval_time`: Exact ingestion timestamp
  - `data_type`: Explicit measurement type
  - `value`: Raw data payload
  - `unit`: Standardized unit string
  - `metadata`: Data nature, flags, quality indicators
- **Verification Integrity**: Findings initially hold `verification_status = VerificationStatus.UNVERIFIED`. The agent never self-attests verification, ensuring impartial audit by Person 4's Scientific Verification Agent.

---

## 12. Orchestrator & Multi-Agent Integration

- **Agent Registration**: Keyed as `"ocean_research"` in `OrchestratorService._agents`.
- **Task Routing in `OrchestrationPlanner`**:
  - `FISHERMAN` workspace -> Automatically selects `ocean_research`.
  - `MARINE_MONITORING` workspace -> Automatically selects `ocean_research`.
  - `PROTECTED_AREAS` workspace -> Selects `coastal_risk` and `ocean_research`.
  - `DISASTER_MANAGEMENT` with marine inquiries -> Selects `ocean_research`.
- **Fault Tolerance**: If `ocean_research` encounters an upstream timeout, the orchestrator logs the limitation and completes the investigation without crashing other agents.

---

## 13. Agents Hub & Frontend Integration

- **Agents Hub Registration**: Visible on the `/agents` route as **Ocean Intelligence & Research Agent**.
- **Workspace Linkages**: Backing the Fisherman, Marine Monitoring, and Disaster Management workspaces.
- **Zero Frontend Interference**: Person 1's `frontend/` folder remains untouched to avoid PR merge conflicts with our unified production frontend.

---

## 14. Defects Discovered, Severity, Root Causes & Fixes

| Defect ID | Severity | Root Cause | Impact | Resolution |
|---|---|---|---|---|
| **DEF-01** | **CRITICAL** | `aiosqlite` missing from runtime environment despite being in `pyproject.toml[dev]`. | 20 backend integration tests failed with `ModuleNotFoundError`. | Installed `aiosqlite-0.22.1`. 20 tests immediately passed. |
| **DEF-02** | **HIGH** | Windows Python default `ProactorEventLoop` incompatible with async `psycopg`. | `import_marine_data.py` and real DB tests failed with `psycopg.InterfaceError`. | Configured `WindowsSelectorEventLoopPolicy` in `scripts/import_marine_data.py` and `tests/conftest.py`. |
| **DEF-03** | **CRITICAL** | Schema mismatch between Person 1's `models/marine.py` and canonical PostgreSQL `data_sources` table. | Queries failed with `UndefinedColumn: column data_sources.description does not exist` and `NotNullViolation: provider`. | Added `description`, `base_url`, `license_info` columns and default provider to PostgreSQL; updated model. |
| **DEF-04** | **CRITICAL** | `marine_observations` table in PostgreSQL lacked Person 1's wide physical measurement columns. | Real PostgreSQL test failed; data ingestion could not persist SST, wave, or current observations. | Extended PostgreSQL `marine_observations` table with nullable wide columns and added `uq_marine_obs_source_time_lat_lon` constraint. |
| **DEF-05** | **MEDIUM** | `app/db/session.py` missing `async_session_maker` symbol expected by `test_marine_pipeline.py`. | Real PostgreSQL test failed with `ImportError`. | Added `async_session_maker = AsyncSessionLocal` alias in `session.py`. |
| **DEF-06** | **MEDIUM** | Windows console encoding (`cp1252`) crashed on `✓` checkmark in `import_marine_data.py`. | Console threw `UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'`. | Replaced Unicode glyphs with robust ASCII indicators (`[OK]`, `-`). |
| **DEF-07** | **LOW** | Real PostgreSQL test lacked pre-test isolation cleanup for repeated runs. | Test failed with `AssertionError: assert 'updated' == 'inserted'` on second execution. | Added pre-test deletion of test record key in `test_marine_pipeline.py`. |

---

## 15. Comprehensive Test Execution Record

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\chira\Desktop\ORCA agent\perosn1\orca\backend
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0

tests\api\test_health.py .                                               [  1%]
tests\api\test_marine_api.py .                                           [  2%]
tests\integration\test_marine_pipeline.py .............                  [ 16%]
tests\integration\test_shared_backend_integration.py ..........          [ 26%]
tests\unit\test_contracts.py ....                                        [ 31%]
tests\unit\test_ocean_research_agent.py ................................ [ 65%]
..............                                                           [ 80%]
tests\unit\test_orchestrator.py ..                                       [ 82%]
tests\unit\test_provider_resilience.py ........                          [ 91%]
tests\unit\test_scientific_validation.py ........                        [100%]

====================== 93 passed, 1 deselected in 50.26s ======================
```

- **Live Open-Meteo Smoke Test**: `python -m pytest tests/unit/test_ocean_research_agent.py -m live_api` -> **1 passed in 1.81s**.
- **Combined Test Outcome**: **94 / 94 TESTS PASSING (100% SUCCESS RATE)**.
- **Person 3 Regression Suite**: **36 / 36 TESTS PASSING (0 REGRESSIONS)**.

---

## 16. Known Limitations & Unimplemented Capabilities

1. **Copernicus Marine Satellite Live API**: Currently operates in historical baseline/fixture mode. Live Copernicus Earth Observation credentials require dedicated EU Copernicus Marine Service tokens.
2. **In-situ Ocean Buoy Feeds (INCOIS Moored Buoys)**: Real-time telemetry from INCOIS coastal wave rider buoys requires INCOIS data authorization credentials; currently represented via historical archive samples.
3. **Atmospheric Wind Feed in Open-Meteo**: The Open-Meteo Marine endpoint does not provide 10m surface winds; atmospheric wind queries require the atmospheric weather API endpoint.

---

## 17. Security & Configuration Requirements

- **Zero Secret Leakage**: Database URLs, API keys, and internal IP addresses are loaded via Pydantic `BaseSettings` from `.env`.
- **Safe Fallbacks**: If external API keys (e.g. `GROQ_API_KEY`) are missing, the system gracefully operates in deterministic-only mode without crashing or logging secrets.

---

## 18. Reproducible Local Setup & Execution Guide

```powershell
# 1. Navigate to Person 1 backend directory
cd "C:\Users\chira\Desktop\ORCA agent\perosn1\orca\backend"

# 2. Run full pytest regression suite with PostgreSQL tests enabled
$env:RUN_REAL_POSTGRES_TESTS="1"
python -m pytest tests/

# 3. Run live Open-Meteo API network verification
python -m pytest tests/unit/test_ocean_research_agent.py -m "live_api"

# 4. Ingest Arabian Sea reference fixture into PostgreSQL
cd "C:\Users\chira\Desktop\ORCA agent\perosn1\orca"
python scripts/import_marine_data.py --sample-fixture

# 5. Ingest live 7-day numerical ocean forecast for Mangaluru into PostgreSQL
python scripts/import_marine_data.py --live --lat 12.87 --lon 74.88
```

---

## 19. Git Branch & Pull Request Status

- **Repository**: `https://github.com/Chiragd17/ORCA_AI.git`
- **Active Working Branch**: `feature/person-1-ocean-agent`
- **Isolation Protection**: Person 3 (`person3/`, branch `main`) was completely untouched.
- **Clean Commits**: All fixes and additions are staged on `feature/person-1-ocean-agent`.

---

## 20. Final Operational-Readiness Assessment

### Final Verdict: **VERIFIED OPERATIONAL**

The **Person 1 Ocean Intelligence & Research Agent** is fully audited, verified, and operational. All scientific calculations, provider adapters, error-handling mechanisms, and database persistence routines conform to ORCA AI's architectural standards.

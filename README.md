# ORCA — Open-Source Marine and Coastal Intelligence Platform

ORCA is an AI-powered marine and coastal intelligence platform that combines real marine observations, hazard information, coastal geospatial data, deterministic scientific analysis, and collaborative AI agents.

---

## 1. 3-Person Team Role Allocation

| Teammate | Assigned Responsibility | Primary Working Directory |
|---|---|---|
| **Person 1** | **Ocean Intelligence & Research Agent** (SST, waves, winds, chlorophyll, anomaly detection) | `backend/app/agents/ocean_research/`, `scripts/import_marine_data.py` |
| **Person 2** | **Marine Hazard & Forecast Agent** (cyclone tracks, IBTrACS, GDACS, marine hazard forecasts) | `backend/app/agents/marine_hazard/`, `scripts/import_hazard_data.py` |
| **Person 3** | **Coastal Impact & Risk Agent** + **Evidence & Scientific Verification Agent** + **Shared Orchestrator / Integration** | `backend/app/agents/coastal_risk/`, `backend/app/agents/evidence_verification/`, `backend/app/orchestrator/`, `scripts/import_coastal_data.py` |

> **Critical Rule:** All three teammates work on the **same repository, same database schema, and same shared API client**. No separate applications or competing architectures.

---

## 2. The 5 Shared Workspaces

All five workspaces share the exact same backend, database, agents, evidence registry, and Orchestrator:

1. **Fisherman**: Local marine conditions, wave/wind forecasts, safe operating thresholds, advisory alerts.
2. **Marine Monitoring**: SST & ocean-color time series, seasonal analysis, environmental anomaly detection.
3. **Protected Areas**: Marine protected areas boundary overlap, ecological indicators, spatial baseline shifts.
4. **Coastal Authority**: Coastal settlements, infrastructure exposure, geographic intersection, population estimates.
5. **Disaster Management**: Cyclone track playback, multi-hazard exposure, timeline analysis, uncertainty tracking.

---

## 3. Technology Stack

- **Frontend**: React 19 / Vite / TypeScript / Tailwind CSS / Radix UI / MapLibre GL JS / Recharts
- **Backend**: Python 3.12 / FastAPI / Pydantic v2 / SQLAlchemy 2.x / Alembic / PostgreSQL (Psycopg 3) / HTTPX
- **AI Providers**: Groq (primary) → Gemini (secondary) → OpenRouter (fallback)
- **Geospatial & Time**: WGS84 (lon/lat), UTC timestamps, deterministic Python calculations.

---

## 4. Repository Structure

```text
orca/
├── README.md
├── .gitignore
├── .env.example
├── docs/                      # Architectural, API, schema, and integration documentation
├── backend/                   # Shared FastAPI backend, agents, orchestrator, and tests
│   ├── alembic/               # Database migrations
│   ├── app/
│   │   ├── agents/            # Four specialist agents
│   │   ├── orchestrator/      # Multi-agent coordinator
│   │   ├── evidence/          # Verification & evidence registry
│   │   ├── providers/         # LLM and external data clients
│   │   ├── api/v1/            # Shared REST endpoints
│   │   ├── models/            # SQLAlchemy database models
│   │   ├── schemas/           # Shared Pydantic contracts
│   │   └── core/              # Config, exceptions, logging
│   └── tests/                 # Unit, integration, and API tests
├── frontend/                  # React + Vite application
│   └── src/
│       ├── features/          # Five workspaces + investigations
│       ├── components/        # Reusable UI, map, chart, and evidence components
│       └── lib/               # Shared typed API client
├── scripts/                   # Verification and idempotent data import scripts
└── data/                      # Raw and processed data documentation & sample fixtures
```

---

## 5. Quickstart

### Prerequisites
- Node.js 22+
- Python 3.12+
- PostgreSQL instance running

### Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .
cp ../.env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Environment Check
```bash
python scripts/check_environment.py
```

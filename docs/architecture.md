# ORCA System Architecture

## 1. Architectural Overview

ORCA (Open-Source Marine and Coastal Intelligence Platform) is organized into 5 unified layers:

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer E: Frontend UI                     │
│  React + Vite + TypeScript + Tailwind + MapLibre + Recharts │
│  5 Workspaces: Fisherman | Marine | Protected | Authority | DM│
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON
┌──────────────────────────────▼──────────────────────────────┐
│                  Layer D: API & Orchestrator                │
│  FastAPI v1 Endpoints (/marine, /hazards, /investigations)  │
│  Deterministic Execution Engine & Planning                  │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
┌──────────────▼──────────────┐ ┌──────────────▼──────────────┐
│  Layer C: Specialist Agents │ │ Layer C: Verification Agent │
│  1. Ocean Research          │ │ 4. Evidence & Scientific    │
│  2. Marine Hazard           │ │    Verification Agent       │
│  3. Coastal Impact & Risk   │ │                             │
└──────────────┬──────────────┘ └──────────────┬──────────────┘
               │                               │
┌──────────────▼───────────────────────────────▼──────────────┐
│            Layer B: Shared Persistence & Evidence           │
│  PostgreSQL (Observations, Hazards, Geometries, Evidence)   │
│  SQLAlchemy 2.x + Alembic Migrations + UTC + WGS84          │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                  Layer A: Data Acquisition                  │
│  Open-Meteo | NOAA IBTrACS | GDACS | OSM Overpass | WorldPop │
└─────────────────────────────────────────────────────────────┘
```

## 2. Shared Principles
- **Real data first**: No fabricated observations or mock forecasts presented as truth.
- **Evidence-backed**: Every finding links to an explicit Evidence ID.
- **Deterministic computations**: Distance, intersection, and anomaly arithmetic run in Python, not hallucinated by LLMs.
- **Honest uncertainty**: Explicit flags for stale data, missing coverage, and unverified hypotheses.
- **Single application**: All workspaces use the identical backend API, agent pool, and DB.

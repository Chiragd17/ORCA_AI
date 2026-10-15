# ORCA 3-Person Team Integration Guide

## 1. Team Responsibilities

- **Person 1**: Ocean Intelligence & Research Agent (`backend/app/agents/ocean_research/`)
  - Implements SST, wave, wind, current, chlorophyll data fetching & analysis.
  - Exposes findings & evidence according to `docs/agent-contract.md`.
- **Person 2**: Marine Hazard & Forecast Agent (`backend/app/agents/marine_hazard/`)
  - Implements IBTrACS cyclone track loader, GDACS hazard ingestion, marine hazard forecast queries.
  - Exposes findings & evidence according to `docs/agent-contract.md`.
- **Person 3**: Coastal Impact & Risk Agent + Evidence & Scientific Verification Agent + Shared Orchestrator
  - Implements geospatial exposure analysis in `coastal_risk/`.
  - Implements verification engine in `evidence_verification/`.
  - Coordinates the multi-agent execution pipeline in `orchestrator/`.

## 2. Git Workflow
1. Branch naming convention:
   - `feature/person-1-ocean-agent`
   - `feature/person-2-hazard-agent`
   - `feature/person-3-coastal-verification-orchestrator`
2. Commit small, working changes with clear messages.
3. Coordinate before modifying shared files:
   - `backend/app/agents/base.py`
   - `backend/app/schemas/`
   - `backend/app/models/`
   - `backend/alembic/`
   - `frontend/src/lib/api-client.ts`

## 3. Pre-Merge Checklist
1. All unit tests pass (`pytest`).
2. Schema migrations are compatible (`alembic check` / `alembic upgrade head`).
3. Frontend TypeScript compiles without errors (`npm run build`).
4. Output conforms to `docs/agent-contract.md`.

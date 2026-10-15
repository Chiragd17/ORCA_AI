# ORCA Shared API Contract (v1)

Base URL: `/api/v1`

## Endpoints Summary

### System Health
- **`GET /health`**
  - Response: `{"status": "ok", "version": "0.1.0", "timestamp": "ISO8601 UTC"}`

### Marine Intelligence
- **`GET /api/v1/marine/observations`**
  - Query parameters:
    - `lat` (float, required): Latitude [-90, 90]
    - `lon` (float, required): Longitude [-180, 180]
    - `start_date` (ISO date, optional)
    - `end_date` (ISO date, optional)
  - Returns: Marine observation series (SST, wave height, wind speed, chlorophyll) with source and evidence metadata.

### Hazards & Storms
- **`GET /api/v1/hazards`**
  - Query parameters:
    - `basin` (string, optional, e.g. "arabian_sea", "indian_ocean")
    - `status` (string, optional: "active", "historical")
    - `limit` (integer, default 20)
  - Returns: List of cyclone/hazard events, tracks, intensity, and observation timestamps.

### Investigations (Orchestration Entrypoint)
- **`POST /api/v1/investigations`**
  - Request Body:
    ```json
    {
      "workspace": "fisherman",
      "prompt": "Check wave conditions and wind speeds offshore Mangaluru for tomorrow morning.",
      "latitude": 12.87,
      "longitude": 74.88,
      "target_time": "2026-10-16T06:00:00Z",
      "parameters": {}
    }
    ```
  - Response: Returns created `investigation_id`, status (`queued` / `running`), and initial execution plan.

- **`GET /api/v1/investigations/{investigation_id}`**
  - Returns: Current investigation state, active agent, status (`running`, `completed`, `failed`), and final synthesized answer.

- **`GET /api/v1/investigations/{investigation_id}/events`**
  - Returns: Chronological list of genuine execution events emitted by the orchestrator (`investigation_started`, `agent_started`, `tool_completed`, `evidence_added`, `verification_passed`, `investigation_completed`).

- **`GET /api/v1/investigations/{investigation_id}/evidence`**
  - Returns: All supporting evidence records linked to the findings of this investigation.

- **`GET /api/v1/investigations/{investigation_id}/report`**
  - Returns: Structured scientific report with claims, evidence links, verification statuses, uncertainty levels, and limitations.

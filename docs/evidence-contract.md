# ORCA Shared Evidence & Verification Contract

## 1. Evidence Record Schema

Every piece of data used to support a finding must be formalized as an `EvidenceRecord`:

```python
class EvidenceRecord(BaseModel):
    id: str  # e.g., "ev-om-sst-20261015-01"
    source_name: str  # e.g., "Open-Meteo Marine API"
    source_uri: str  # URL or dataset identifier
    observation_time: Optional[datetime]  # When measurement occurred
    retrieval_time: datetime  # When fetched by ORCA (UTC)
    latitude: Optional[float]
    longitude: Optional[float]
    data_type: str  # e.g., "sea_surface_temperature", "cyclone_track_point"
    value: Optional[Any]
    unit: Optional[str]
    metadata: Dict[str, Any] = {}
```

## 2. Verification States

The Evidence & Scientific Verification Agent applies strict verification rules:

- **`verified`**: Evidence exists, timestamps are compatible, calculations reproduced, and claims are supported.
- **`unverified`**: Finding is plausible but lacks direct or sufficient evidence records.
- **`needs_review`**: Contradictory evidence exists, or claim extrapolates beyond dataset resolution.
- **`conflicting`**: Multiple credible sources yield irreconcilable values for the same spacetime window.
- **`insufficient_evidence`**: No evidence records available to substantiate the claim.

## 3. Strict Rules
- Stale observations must NOT be represented as current conditions.
- Proximity does not imply damage without clear geospatial criteria.
- LLM statements without evidence IDs are labelled `ai_interpretation` and cannot be marked `verified`.

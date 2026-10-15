from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field

class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    NEEDS_REVIEW = "needs_review"
    CONFLICTING = "conflicting"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

class FindingCategory(str, Enum):
    OBSERVATION = "observation"
    FORECAST = "forecast"
    HISTORICAL_RECORD = "historical_record"
    DETERMINISTIC_CALCULATION = "deterministic_calculation"
    AI_INTERPRETATION = "ai_interpretation"

class EvidenceRecord(BaseModel):
    id: str = Field(..., description="Stable, unique evidence identifier (e.g., ev-om-sst-01)")
    source_name: str = Field(..., description="Source dataset or provider name")
    source_uri: str = Field(..., description="URL or source identifier")
    observation_time: Optional[datetime] = Field(None, description="Observation or valid forecast timestamp in UTC")
    retrieval_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when record was retrieved by ORCA in UTC"
    )
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    data_type: str = Field(..., description="Type of measurement or feature (e.g., sst, wave_height)")
    value: Optional[Any] = Field(None, description="Raw observation or structured measurement value")
    unit: Optional[str] = Field(None, description="Unit of measurement (e.g. °C, m, m/s, knots)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional provenance or quality metadata")

class Finding(BaseModel):
    id: Optional[str] = None
    claim: str = Field(..., description="Clear assertional statement or measurement claim")
    value: Optional[Any] = Field(None, description="Observed or derived numerical or categorical value")
    unit: Optional[str] = Field(None, description="Physical unit of value")
    category: FindingCategory = Field(default=FindingCategory.OBSERVATION)
    evidence_ids: List[str] = Field(default_factory=list, description="List of supporting EvidenceRecord IDs")
    uncertainty: Optional[str] = Field(None, description="Methodological or instrument uncertainty")
    verification_status: VerificationStatus = Field(default=VerificationStatus.UNVERIFIED)

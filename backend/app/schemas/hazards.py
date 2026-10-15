from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.evidence import EvidenceRecord

class TrackPoint(BaseModel):
    time: datetime
    is_forecast: bool = False
    latitude: float
    longitude: float
    wind_speed_knots: Optional[float] = None
    central_pressure_hpa: Optional[float] = None
    storm_category: Optional[str] = None

class HazardEventResponse(BaseModel):
    id: str
    name: str
    event_type: str
    basin: Optional[str] = None
    status: str
    tracks: List[TrackPoint] = Field(default_factory=list)
    evidence: List[EvidenceRecord] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

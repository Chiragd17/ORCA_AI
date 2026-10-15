from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.evidence import EvidenceRecord

class MarineObservationPoint(BaseModel):
    time: datetime
    latitude: float
    longitude: float
    sea_surface_temperature_celsius: Optional[float] = None
    wave_height_meters: Optional[float] = None
    wave_period_seconds: Optional[float] = None
    wave_direction_degrees: Optional[float] = None
    wind_speed_knots: Optional[float] = None
    wind_direction_degrees: Optional[float] = None
    chlorophyll_mg_m3: Optional[float] = None

class MarineObservationResponse(BaseModel):
    latitude: float
    longitude: float
    source: str
    observations: List[MarineObservationPoint]
    evidence: List[EvidenceRecord] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)

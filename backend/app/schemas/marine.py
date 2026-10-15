from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.evidence import EvidenceRecord


class MarineObservationPoint(BaseModel):
    time: datetime
    latitude: float
    longitude: float
    sea_surface_temperature_celsius: float | None = None
    wave_height_meters: float | None = None
    wave_period_seconds: float | None = None
    wave_direction_degrees: float | None = None
    ocean_current_velocity_mps: float | None = None
    ocean_current_direction_degrees: float | None = None
    wind_speed_knots: float | None = None
    wind_direction_degrees: float | None = None
    chlorophyll_mg_m3: float | None = None

class MarineObservationResponse(BaseModel):
    latitude: float
    longitude: float
    source: str
    observations: list[MarineObservationPoint]
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

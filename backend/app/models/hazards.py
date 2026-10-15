from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class HazardEvent(Base):
    __tablename__ = "hazard_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)  # cyclone, storm_surge, tsunami
    name: Mapped[str] = mapped_column(String(128))
    basin: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, historical
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    tracks: Mapped[List["HazardTrack"]] = relationship("HazardTrack", back_populates="event", cascade="all, delete-orphan")

class HazardTrack(Base):
    __tablename__ = "hazard_tracks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("hazard_events.id"), index=True)
    observation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_forecast: Mapped[bool] = mapped_column(default=False)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    wind_speed_knots: Mapped[Optional[float]] = mapped_column(Float)
    central_pressure_hpa: Mapped[Optional[float]] = mapped_column(Float)
    storm_category: Mapped[Optional[str]] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    event: Mapped["HazardEvent"] = relationship("HazardEvent", back_populates="tracks")

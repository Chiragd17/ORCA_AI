from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(String(256))
    license_info: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

class MarineObservation(Base):
    __tablename__ = "marine_observations"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "observation_time",
            "latitude",
            "longitude",
            name="uq_marine_obs_source_time_lat_lon",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_sources.id"), index=True)
    observation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float, index=True)

    # Measurements with explicit units
    sea_surface_temperature_celsius: Mapped[float | None] = mapped_column(Float)
    wave_height_meters: Mapped[float | None] = mapped_column(Float)
    wave_period_seconds: Mapped[float | None] = mapped_column(Float)
    wave_direction_degrees: Mapped[float | None] = mapped_column(Float)
    ocean_current_velocity_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocean_current_direction_degrees: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_knots: Mapped[float | None] = mapped_column(Float)
    wind_direction_degrees: Mapped[float | None] = mapped_column(Float)
    chlorophyll_mg_m3: Mapped[float | None] = mapped_column(Float)

    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

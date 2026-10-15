from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marine import DataSource, MarineObservation
from app.utils import haversine_distance_km

Tuple_Result = tuple[str, MarineObservation]


class MarineRepository:
    """
    SQLAlchemy repository for marine data sources and observations.
    Ensures idempotent upserts and spatial/temporal queries.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_data_source(
        self,
        source_id: str,
        name: str,
        base_url: str | None = None,
        description: str | None = None,
        license_info: str | None = None,
    ) -> DataSource:
        stmt = select(DataSource).where(DataSource.id == source_id)
        result = await self.session.execute(stmt)
        source = result.scalar_one_or_none()
        if not source:
            source = DataSource(
                id=source_id,
                name=name,
                base_url=base_url,
                description=description,
                license_info=license_info,
                created_at=datetime.now(UTC),
            )
            self.session.add(source)
            await self.session.flush()
        return source

    async def upsert_observation(
        self,
        source_id: str,
        observation_time: datetime,
        latitude: float,
        longitude: float,
        sea_surface_temperature_celsius: float | None = None,
        wave_height_meters: float | None = None,
        wave_period_seconds: float | None = None,
        wave_direction_degrees: float | None = None,
        wind_speed_knots: float | None = None,
        wind_direction_degrees: float | None = None,
        chlorophyll_mg_m3: float | None = None,
        metadata_json: dict | None = None,
    ) -> Tuple_Result:
        """
        Idempotent insert or update based on (source_id, observation_time, latitude, longitude).
        """
        # Ensure UTC timezone
        if observation_time.tzinfo is None:
            observation_time = observation_time.replace(tzinfo=UTC)

        stmt = select(MarineObservation).where(
            and_(
                MarineObservation.source_id == source_id,
                MarineObservation.observation_time == observation_time,
                MarineObservation.latitude == latitude,
                MarineObservation.longitude == longitude,
            )
        )
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            # Update fields if changed
            existing.sea_surface_temperature_celsius = sea_surface_temperature_celsius
            existing.wave_height_meters = wave_height_meters
            existing.wave_period_seconds = wave_period_seconds
            existing.wave_direction_degrees = wave_direction_degrees
            existing.wind_speed_knots = wind_speed_knots
            existing.wind_direction_degrees = wind_direction_degrees
            existing.chlorophyll_mg_m3 = chlorophyll_mg_m3
            existing.metadata_json = metadata_json or {}
            return "updated", existing
        else:
            obs = MarineObservation(
                id=f"obs-{uuid.uuid4().hex[:12]}",
                source_id=source_id,
                observation_time=observation_time,
                latitude=latitude,
                longitude=longitude,
                sea_surface_temperature_celsius=sea_surface_temperature_celsius,
                wave_height_meters=wave_height_meters,
                wave_period_seconds=wave_period_seconds,
                wave_direction_degrees=wave_direction_degrees,
                wind_speed_knots=wind_speed_knots,
                wind_direction_degrees=wind_direction_degrees,
                chlorophyll_mg_m3=chlorophyll_mg_m3,
                metadata_json=metadata_json or {},
                created_at=datetime.now(UTC),
            )
            self.session.add(obs)
            return "inserted", obs

    async def bulk_ingest(self, records: list[dict[str, Any]]) -> dict[str, int]:
        counts = {"processed": len(records), "inserted": 0, "updated": 0, "failed": 0}
        for r in records:
            try:
                action, _ = await self.upsert_observation(**r)
                if action == "inserted":
                    counts["inserted"] += 1
                else:
                    counts["updated"] += 1
            except Exception:
                counts["failed"] += 1
        await self.session.commit()
        return counts

    async def query_observations(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[MarineObservation]:
        """
        Retrieves marine observations filtered by time and approximate bounding box,
        then refined by deterministic great-circle Haversine distance.
        """
        # 1 deg latitude is approx 111km
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * max(0.1, abs(abs(latitude) - 90.0) / 90.0))

        conditions = [
            MarineObservation.latitude.between(latitude - lat_delta, latitude + lat_delta),
            MarineObservation.longitude.between(longitude - lon_delta, longitude + lon_delta),
        ]
        if start_time:
            conditions.append(MarineObservation.observation_time >= start_time)
        if end_time:
            conditions.append(MarineObservation.observation_time <= end_time)

        stmt = select(MarineObservation).where(and_(*conditions)).order_by(MarineObservation.observation_time.asc())
        result = await self.session.execute(stmt)
        candidates = result.scalars().all()

        # Refine by exact Haversine distance
        refined = [
            obs for obs in candidates
            if haversine_distance_km(latitude, longitude, obs.latitude, obs.longitude) <= radius_km
        ]
        return refined

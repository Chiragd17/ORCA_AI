import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Set

from app.db.repositories.marine import MarineRepository
from app.models.marine import MarineObservation
from app.providers.data.historical_marine import HistoricalMarineDataLoader
from app.utils import haversine_distance_km
from app.agents.ocean_research.calculations import validate_geographic_coordinates

SUPPORTED_MARINE_VARIABLES: Set[str] = {
    "sea_surface_temperature_celsius",
    "wave_height_meters",
    "wave_period_seconds",
    "wave_direction_degrees",
    "wind_speed_knots",
    "wind_direction_degrees",
}

VARIABLE_ALIASES: Dict[str, str] = {
    "sst": "sea_surface_temperature_celsius",
    "sea_surface_temperature": "sea_surface_temperature_celsius",
    "temperature": "sea_surface_temperature_celsius",
    "wave_height": "wave_height_meters",
    "waves": "wave_height_meters",
    "wave_period": "wave_period_seconds",
    "wave_direction": "wave_direction_degrees",
    "wind_speed": "wind_speed_knots",
    "wind": "wind_speed_knots",
    "wind_direction": "wind_direction_degrees",
}

VARIABLE_UNITS: Dict[str, str] = {
    "sea_surface_temperature_celsius": "°C",
    "wave_height_meters": "m",
    "wave_period_seconds": "s",
    "wave_direction_degrees": "degrees",
    "wind_speed_knots": "knots",
    "wind_direction_degrees": "degrees",
}

class MarineResearchQueryService:
    """
    Query service executing marine research queries against either:
    1. Shared PostgreSQL database via MarineRepository.
    2. Real validated historical scientific dataset via HistoricalMarineDataLoader.
    Ensures input validation, variable checking, spatial radius filtering, and temporal bounds.
    """
    def __init__(
        self,
        repository: Optional[MarineRepository] = None,
        historical_loader: Optional[HistoricalMarineDataLoader] = None,
    ):
        self.repository = repository
        self.historical_loader = historical_loader or HistoricalMarineDataLoader()

    def canonicalize_variable(self, variable_name: str) -> Optional[str]:
        """Resolves alias or canonical variable name."""
        cleaned = variable_name.strip().lower()
        if cleaned in SUPPORTED_MARINE_VARIABLES:
            return cleaned
        return VARIABLE_ALIASES.get(cleaned)

    def validate_query_parameters(
        self,
        latitude: Optional[float],
        longitude: Optional[float],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        variables: Optional[List[str]] = None,
        radius_km: float = 50.0,
    ) -> Tuple[bool, List[str]]:
        """
        Validates spatial coordinates, time window ordering, radius limits, and supported variables.
        """
        errors = []
        is_coord_valid, coord_err = validate_geographic_coordinates(latitude, longitude)
        if not is_coord_valid and coord_err:
            errors.append(coord_err)

        if radius_km <= 0.0 or radius_km > 1000.0:
            errors.append(f"Invalid search radius {radius_km} km: must be between 0.1 and 1000.0 km.")

        if start_time and end_time:
            # Ensure timezone-aware UTC comparison
            st = start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
            et = end_time if end_time.tzinfo else end_time.replace(tzinfo=timezone.utc)
            if st > et:
                errors.append(
                    f"Invalid temporal range: start_time ({st.isoformat()}) must not be after end_time ({et.isoformat()})."
                )

        if variables:
            for v in variables:
                canon = self.canonicalize_variable(v)
                if not canon:
                    errors.append(
                        f"Unsupported marine variable '{v}'. Supported variables: {sorted(list(SUPPORTED_MARINE_VARIABLES))}."
                    )

        return len(errors) == 0, errors

    def _filter_historical_records(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Filters local historical dataset by spatial radius and temporal window."""
        all_hist, _, _ = self.historical_loader.load_local_dataset()
        filtered = []
        for r in all_hist:
            r_lat = r["latitude"]
            r_lon = r["longitude"]
            dist_km = haversine_distance_km(latitude, longitude, r_lat, r_lon)
            if dist_km <= radius_km:
                obs_t = r["observation_time"]
                if start_time:
                    st = start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
                    if obs_t < st:
                        continue
                if end_time:
                    et = end_time if end_time.tzinfo else end_time.replace(tzinfo=timezone.utc)
                    if obs_t > et:
                        continue
                filtered.append(r)
        return filtered

    async def get_observations(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Retrieves observation records for a given geographic point and radius.
        Returns:
            (records, source_type) where source_type is 'database_repository',
            'database_fallback', or 'historical_dataset'.
        """
        if self.repository:
            try:
                db_records = await self.repository.query_observations(
                    latitude=latitude,
                    longitude=longitude,
                    radius_km=radius_km,
                    start_time=start_time,
                    end_time=end_time,
                )
                if db_records:
                    normalized = []
                    for obs in db_records:
                        normalized.append({
                            "id": obs.id,
                            "source_id": obs.source_id,
                            "observation_time": obs.observation_time,
                            "latitude": obs.latitude,
                            "longitude": obs.longitude,
                            "sea_surface_temperature_celsius": obs.sea_surface_temperature_celsius,
                            "wave_height_meters": obs.wave_height_meters,
                            "wave_period_seconds": obs.wave_period_seconds,
                            "wave_direction_degrees": obs.wave_direction_degrees,
                            "wind_speed_knots": obs.wind_speed_knots,
                            "wind_direction_degrees": obs.wind_direction_degrees,
                            "chlorophyll_mg_m3": obs.chlorophyll_mg_m3,
                            "metadata_json": obs.metadata_json or {},
                        })
                    return normalized, "database_repository"
            except Exception:
                # Disclose repository query failure and fall back safely to local historical scientific archive
                fallback = self._filter_historical_records(
                    latitude=latitude,
                    longitude=longitude,
                    radius_km=radius_km,
                    start_time=start_time,
                    end_time=end_time,
                )
                return fallback, "database_fallback"

        # Fallback to local historical scientific dataset
        filtered = self._filter_historical_records(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            start_time=start_time,
            end_time=end_time,
        )
        return filtered, "historical_dataset"

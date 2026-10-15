from datetime import UTC, datetime
from typing import Any

from app.agents.ocean_research.calculations import validate_geographic_coordinates
from app.db.repositories.marine import MarineRepository
from app.providers.data.historical_marine import HistoricalMarineDataLoader
from app.utils import haversine_distance_km

SUPPORTED_MARINE_VARIABLES: set[str] = {
    "sea_surface_temperature_celsius",
    "wave_height_meters",
    "wave_period_seconds",
    "wave_direction_degrees",
    "ocean_current_velocity_mps",
    "ocean_current_direction_degrees",
    "wind_speed_knots",
    "wind_direction_degrees",
}

VARIABLE_ALIASES: dict[str, str] = {
    "sst": "sea_surface_temperature_celsius",
    "sea_surface_temperature": "sea_surface_temperature_celsius",
    "temperature": "sea_surface_temperature_celsius",
    "wave_height": "wave_height_meters",
    "waves": "wave_height_meters",
    "wave_period": "wave_period_seconds",
    "wave_direction": "wave_direction_degrees",
    "current_velocity": "ocean_current_velocity_mps",
    "ocean_current_velocity": "ocean_current_velocity_mps",
    "current": "ocean_current_velocity_mps",
    "current_direction": "ocean_current_direction_degrees",
    "ocean_current_direction": "ocean_current_direction_degrees",
    "wind_speed": "wind_speed_knots",
    "wind": "wind_speed_knots",
    "wind_direction": "wind_direction_degrees",
}

VARIABLE_UNITS: dict[str, str] = {
    "sea_surface_temperature_celsius": "°C",
    "wave_height_meters": "m",
    "wave_period_seconds": "s",
    "wave_direction_degrees": "degrees",
    "ocean_current_velocity_mps": "m/s",
    "ocean_current_direction_degrees": "degrees",
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
        repository: MarineRepository | None = None,
        historical_loader: HistoricalMarineDataLoader | None = None,
    ):
        self.repository = repository
        self.historical_loader = historical_loader or HistoricalMarineDataLoader()

    def canonicalize_variable(self, variable_name: str) -> str | None:
        """Resolves alias or canonical variable name."""
        cleaned = variable_name.strip().lower()
        if cleaned in SUPPORTED_MARINE_VARIABLES:
            return cleaned
        return VARIABLE_ALIASES.get(cleaned)

    def validate_query_parameters(
        self,
        latitude: float | None,
        longitude: float | None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        variables: list[str] | None = None,
        radius_km: float = 50.0,
    ) -> tuple[bool, list[str]]:
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
            st = start_time if start_time.tzinfo else start_time.replace(tzinfo=UTC)
            et = end_time if end_time.tzinfo else end_time.replace(tzinfo=UTC)
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
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
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
                    st = start_time if start_time.tzinfo else start_time.replace(tzinfo=UTC)
                    if obs_t < st:
                        continue
                if end_time:
                    et = end_time if end_time.tzinfo else end_time.replace(tzinfo=UTC)
                    if obs_t > et:
                        continue
                filtered.append(r)
        return filtered

    async def get_observations(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        allow_fixture_fallback: bool = False,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Retrieves observation records for a given geographic point and radius.
        Returns:
            (records, source_type) where source_type is:
            - 'database_repository': records from real database
            - 'database_empty': database exists and was queried, but 0 records matched
            - 'database_error': database query failed with an exception
            - 'no_repository_configured': no repository configured
            - 'sample_fixture_demo': explicitly requested or allowed demo/test fixture
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
                            "ocean_current_velocity_mps": getattr(obs, "ocean_current_velocity_mps", None),
                            "ocean_current_direction_degrees": getattr(obs, "ocean_current_direction_degrees", None),
                            "wind_speed_knots": obs.wind_speed_knots,
                            "wind_direction_degrees": obs.wind_direction_degrees,
                            "chlorophyll_mg_m3": obs.chlorophyll_mg_m3,
                            "metadata_json": obs.metadata_json or {},
                        })
                    return normalized, "database_repository"
                else:
                    if allow_fixture_fallback:
                        fallback = self._filter_historical_records(
                            latitude=latitude,
                            longitude=longitude,
                            radius_km=radius_km,
                            start_time=start_time,
                            end_time=end_time,
                        )
                        return fallback, "sample_fixture_demo"
                    return [], "database_empty"
            except Exception:
                if allow_fixture_fallback:
                    fallback = self._filter_historical_records(
                        latitude=latitude,
                        longitude=longitude,
                        radius_km=radius_km,
                        start_time=start_time,
                        end_time=end_time,
                    )
                    return fallback, "sample_fixture_demo"
                return [], "database_error"

        if allow_fixture_fallback:
            filtered = self._filter_historical_records(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                start_time=start_time,
                end_time=end_time,
            )
            return filtered, "sample_fixture_demo"

        return [], "no_repository_configured"

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.evidence import EvidenceRecord
from app.schemas.marine import MarineObservationPoint


class OpenMeteoMarineClient:
    """
    Client for Open-Meteo Marine API.
    Provides numerical wave, sea-surface temperature, and ocean current model forecasts.
    Note: Values represent numerical model outputs, not direct in-situ sensor measurements.
    """
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = 12.0,
        demo_mode: bool = False,
    ):
        self.base_url = base_url or settings.OPEN_METEO_BASE_URL
        self.timeout = timeout_seconds
        self.demo_mode = demo_mode

    async def fetch_marine_data(
        self,
        latitude: float,
        longitude: float,
        start_date: str | None = None,
        end_date: str | None = None,
        demo_mode: bool | None = None,
    ) -> tuple[list[MarineObservationPoint], list[EvidenceRecord], list[str]]:
        """
        Retrieves numerical wave, sea-surface temperature, and ocean model forecast data for given coordinates.
        Returns:
            (observations, evidence_records, limitations)
        """
        limitations: list[str] = []
        evidence_records: list[EvidenceRecord] = []
        observations: list[MarineObservationPoint] = []
        effective_demo = self.demo_mode if demo_mode is None else demo_mode

        # Validate coordinates
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            limitations.append(f"Invalid coordinate bounds: lat={latitude}, lon={longitude}.")
            return observations, evidence_records, limitations

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": [
                "sea_surface_temperature",
                "wave_height",
                "wave_direction",
                "wave_period",
                "ocean_current_velocity",
                "ocean_current_direction",
            ],
            "timezone": "UTC",
        }
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        query_url = f"{self.base_url}?latitude={latitude}&longitude={longitude}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.base_url, params=params)
                resp.raise_for_status()
                data = resp.json()

            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            ssts = hourly.get("sea_surface_temperature", [])
            wave_heights = hourly.get("wave_height", [])
            wave_periods = hourly.get("wave_period", [])
            wave_directions = hourly.get("wave_direction", [])
            current_velocities = hourly.get("ocean_current_velocity", [])
            current_directions = hourly.get("ocean_current_direction", [])

            ev_id = f"ev-om-live-{uuid.uuid4().hex[:10]}"
            evidence = EvidenceRecord(
                id=ev_id,
                source_name="Open-Meteo Marine API",
                source_uri=query_url,
                observation_time=datetime.fromisoformat(times[0].replace("Z", "+00:00")) if times else None,
                retrieval_time=datetime.now(UTC),
                latitude=latitude,
                longitude=longitude,
                data_type="marine_wave_current_series",
                value={"sample_count": len(times)},
                unit="°C, m, s, deg, m/s",
                metadata={
                    "status": "live_query",
                    "params": params,
                    "data_nature": "numerical_model_forecast",
                    "is_sensor_observation": False,
                    "model_source": "Open-Meteo Marine numerical model forecast (auto-selected best-match)",
                    "current_velocity_samples": len(current_velocities),
                    "current_velocity_unit": "m/s (converted from km/h)",
                },
            )
            evidence_records.append(evidence)

            for i in range(len(times)):
                t_str = times[i]
                dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                # Open-Meteo ocean_current_velocity is in km/h -> convert to m/s: 1 km/h = 1/3.6 m/s
                curr_kmh = current_velocities[i] if i < len(current_velocities) and current_velocities[i] is not None else None
                curr_mps = round(curr_kmh / 3.6, 3) if curr_kmh is not None else None
                curr_dir = current_directions[i] if i < len(current_directions) and current_directions[i] is not None else None

                point = MarineObservationPoint(
                    time=dt,
                    latitude=latitude,
                    longitude=longitude,
                    sea_surface_temperature_celsius=ssts[i] if i < len(ssts) and ssts[i] is not None else None,
                    wave_height_meters=wave_heights[i] if i < len(wave_heights) and wave_heights[i] is not None else None,
                    wave_period_seconds=wave_periods[i] if i < len(wave_periods) and wave_periods[i] is not None else None,
                    wave_direction_degrees=wave_directions[i] if i < len(wave_directions) and wave_directions[i] is not None else None,
                    ocean_current_velocity_mps=curr_mps,
                    ocean_current_direction_degrees=curr_dir,
                    wind_speed_knots=None,  # Not provided by marine API endpoint
                    wind_direction_degrees=None,
                    chlorophyll_mg_m3=None,  # Not provided by Open-Meteo
                )
                observations.append(point)

            limitations.append("Surface wind variables are not provided by Open-Meteo Marine API (marine-api.open-meteo.com); requires atmospheric weather API.")
            limitations.append("Chlorophyll observations are unavailable through Open-Meteo Marine API.")
            limitations.append("Open-Meteo values represent numerical model forecasts and estimates rather than direct in-situ buoy/sensor measurements.")

        except Exception as e:
            if effective_demo:
                logger.warning(f"Live Open-Meteo query failed ({e!s}). Demo mode enabled: loading labelled sample fixture.")
                limitations.append(f"Live provider query error: {e!s}. Using SAMPLE FIXTURE / DEMO DATA (offline demonstration mode).")
                observations, evidence_records = self._load_scientific_fixture(latitude, longitude, is_demo=True)
            else:
                logger.warning(f"Live Open-Meteo query failed ({e!s}). Returning empty observations with limitation.")
                limitations.append(f"Live marine provider unavailable ({e!s}). No live numerical model forecast retrieved.")
                observations = []
                evidence_records = []

        return observations, evidence_records, limitations

    def _load_scientific_fixture(
        self, latitude: float, longitude: float, is_demo: bool = True
    ) -> tuple[list[MarineObservationPoint], list[EvidenceRecord]]:
        fixture_path = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "marine_sample.json"
        if not fixture_path.exists():
            return [], []

        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        sst_list = hourly.get("sea_surface_temperature", [])
        wave_heights = hourly.get("wave_height", [])
        wave_periods = hourly.get("wave_period", [])
        wave_directions = hourly.get("wave_direction", [])
        wind_speeds = hourly.get("wind_speed_knots", [])
        wind_directions = hourly.get("wind_direction_degrees", [])

        ev_id = f"ev-fixture-marine-{uuid.uuid4().hex[:10]}"
        evidence = EvidenceRecord(
            id=ev_id,
            source_name="SAMPLE FIXTURE / DEMO DATA (Offline Reference)",
            source_uri=str(fixture_path),
            observation_time=datetime.fromisoformat(times[0].replace("Z", "+00:00")) if times else None,
            retrieval_time=datetime.now(UTC),
            latitude=latitude,
            longitude=longitude,
            data_type="marine_sample_fixture",
            value={"sample_count": len(times)},
            unit="°C, m, s, knots",
            metadata={
                "is_fixture": True,
                "is_demo": is_demo,
                "fixture_file": fixture_path.name,
                "data_nature": "offline_reference_sample_fixture",
            },
        )

        obs = []
        for i in range(len(times)):
            t_str = times[i]
            dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
            point = MarineObservationPoint(
                time=dt,
                latitude=latitude,
                longitude=longitude,
                sea_surface_temperature_celsius=sst_list[i] if i < len(sst_list) else None,
                wave_height_meters=wave_heights[i] if i < len(wave_heights) else None,
                wave_period_seconds=wave_periods[i] if i < len(wave_periods) else None,
                wave_direction_degrees=wave_directions[i] if i < len(wave_directions) else None,
                ocean_current_velocity_mps=None,
                ocean_current_direction_degrees=None,
                wind_speed_knots=wind_speeds[i] if i < len(wind_speeds) else None,
                wind_direction_degrees=wind_directions[i] if i < len(wind_directions) else None,
                chlorophyll_mg_m3=None,
            )
            obs.append(point)

        return obs, [evidence]


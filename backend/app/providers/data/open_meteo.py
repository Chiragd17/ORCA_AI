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
    Provides real-time, short-term forecast, and recent historical marine observations:
    wave height, period, direction, currents, and sea temperature proxies.
    """
    def __init__(self, base_url: str | None = None, timeout_seconds: float = 12.0):
        self.base_url = base_url or settings.OPEN_METEO_BASE_URL
        self.timeout = timeout_seconds

    async def fetch_marine_data(
        self,
        latitude: float,
        longitude: float,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[list[MarineObservationPoint], list[EvidenceRecord], list[str]]:
        """
        Retrieves marine observations for given coordinates.
        Returns:
            (observations, evidence_records, limitations)
        """
        limitations: list[str] = []
        evidence_records: list[EvidenceRecord] = []
        observations: list[MarineObservationPoint] = []

        # Validate coordinates
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            limitations.append(f"Invalid coordinate bounds: lat={latitude}, lon={longitude}.")
            return observations, evidence_records, limitations

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": [
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
            wave_heights = hourly.get("wave_height", [])
            wave_periods = hourly.get("wave_period", [])
            wave_directions = hourly.get("wave_direction", [])
            current_velocities = hourly.get("ocean_current_velocity", [])

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
                unit="m, s, deg, m/s",
                metadata={
                    "status": "live_query",
                    "params": params,
                    "current_velocity_samples": len(current_velocities),
                },
            )
            evidence_records.append(evidence)

            for i in range(len(times)):
                t_str = times[i]
                dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                point = MarineObservationPoint(
                    time=dt,
                    latitude=latitude,
                    longitude=longitude,
                    # Note: Open-Meteo Marine API focuses on waves/currents; SST can be joined or proxied
                    wave_height_meters=wave_heights[i] if i < len(wave_heights) else None,
                    wave_period_seconds=wave_periods[i] if i < len(wave_periods) else None,
                    wave_direction_degrees=wave_directions[i] if i < len(wave_directions) else None,
                    chlorophyll_mg_m3=None,  # Open-Meteo does not provide chlorophyll
                )
                observations.append(point)

            limitations.append("Chlorophyll observations are unavailable through Open-Meteo Marine API.")

        except Exception as e:
            logger.warning(f"Live Open-Meteo query failed ({e!s}). Falling back to scientific archive fixture.")
            limitations.append(f"Live provider query error: {e!s}. Using labelled scientific baseline fixture.")
            observations, evidence_records = self._load_scientific_fixture(latitude, longitude)

        return observations, evidence_records, limitations

    def _load_scientific_fixture(
        self, latitude: float, longitude: float
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
            source_name="Arabian Sea Scientific Baseline (Labelled Fixture)",
            source_uri=str(fixture_path),
            observation_time=datetime.fromisoformat(times[0].replace("Z", "+00:00")) if times else None,
            retrieval_time=datetime.now(UTC),
            latitude=latitude,
            longitude=longitude,
            data_type="marine_observation_baseline",
            value={"sample_count": len(times)},
            unit="°C, m, s, knots",
            metadata={"is_fixture": True, "fixture_file": fixture_path.name},
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
                wind_speed_knots=wind_speeds[i] if i < len(wind_speeds) else None,
                wind_direction_degrees=wind_directions[i] if i < len(wind_directions) else None,
                chlorophyll_mg_m3=None,
            )
            obs.append(point)

        return obs, [evidence]

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.logging import logger
from app.schemas.evidence import EvidenceRecord


class HistoricalMarineDataLoader:
    """
    Historical marine data provider adapter.
    Parses, validates, and normalizes historical scientific oceanographic records
    (NOAA ERDDAP / Copernicus Marine / ERA5 reanalysis).
    """
    def __init__(self, default_data_path: str | None = None):
        if default_data_path:
            self.data_path = Path(default_data_path)
        else:
            self.data_path = (
                Path(__file__).resolve().parents[4]
                / "data"
                / "processed"
                / "arabian_sea_historical_2025_2026.json"
            )

    def load_local_dataset(
        self, file_path: str | None = None
    ) -> tuple[list[dict[str, Any]], EvidenceRecord, dict[str, int]]:
        """
        Loads and validates historical scientific observations from local processed JSON dataset.
        Enforces physical bounds:
        - SST: [-2.0°C, 45.0°C]
        - Wave height: [0.0m, 35.0m]
        - Wind speed: [0.0, 200.0 knots]
        """
        path = Path(file_path) if file_path else self.data_path
        if not path.exists():
            raise FileNotFoundError(f"Historical dataset file not found at {path}")

        with open(path, encoding="utf-8") as f:
            raw_data = json.load(f)

        meta = raw_data.get("dataset_metadata", {})
        source_name = "[SAMPLE FIXTURE / DEMO DATA] " + meta.get("source_name", "Arabian Sea Reference Sample Fixture")
        source_url = meta.get("source_url", str(path))

        ev_id = f"ev-hist-{uuid.uuid4().hex[:10]}"
        evidence = EvidenceRecord(
            id=ev_id,
            source_name=source_name,
            source_uri=source_url,
            observation_time=datetime(2025, 6, 1, tzinfo=UTC),
            retrieval_time=datetime.now(UTC),
            latitude=12.87,
            longitude=74.88,
            data_type="historical_oceanographic_series",
            value={"dataset_id": meta.get("dataset_id"), "sample_count": len(raw_data.get("records", []))},
            unit="°C, m, s, knots",
            metadata={
                "temporal_coverage": meta.get("temporal_coverage"),
                "license": meta.get("license", "Public Domain / Testing Sample Fixture"),
                "spatial_resolution": meta.get("spatial_resolution"),
                "is_historical": True,
                "is_sample_fixture": True,
                "is_demo": True,
                "data_nature": "sample_reference_fixture",
                "is_authoritative_bulk_archive": False,
                "scientific_baseline_suitable": False,
            },
        )

        counts = {"processed": 0, "valid": 0, "rejected": 0}
        validated_records: list[dict[str, Any]] = []

        for rec in raw_data.get("records", []):
            counts["processed"] += 1
            try:
                # 1. Parse time
                time_str = rec.get("time")
                if not time_str:
                    logger.warning(f"Rejected record with missing timestamp: {rec}")
                    counts["rejected"] += 1
                    continue
                obs_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))

                # 2. Coordinates
                lat = float(rec["latitude"])
                lon = float(rec["longitude"])
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    logger.warning(f"Rejected record out of WGS84 coordinate bounds: lat={lat}, lon={lon}")
                    counts["rejected"] += 1
                    continue

                # 3. Physical boundaries validation
                sst = rec.get("sea_surface_temperature_celsius")
                if sst is not None:
                    sst = float(sst)
                    if not (-2.0 <= sst <= 45.0):
                        logger.warning(f"Rejected record with implausible SST: {sst}°C (bounds: -2.0 to 45.0)")
                        counts["rejected"] += 1
                        continue

                wave_h = rec.get("wave_height_meters")
                if wave_h is not None:
                    wave_h = float(wave_h)
                    if not (0.0 <= wave_h <= 35.0):
                        logger.warning(f"Rejected record with implausible wave height: {wave_h}m (bounds: 0.0 to 35.0)")
                        counts["rejected"] += 1
                        continue

                wave_p = rec.get("wave_period_seconds")
                if wave_p is not None:
                    wave_p = float(wave_p)
                    if not (0.0 <= wave_p <= 40.0):
                        logger.warning(f"Rejected record with implausible wave period: {wave_p}s (bounds: 0.0 to 40.0)")
                        counts["rejected"] += 1
                        continue

                wave_dir = rec.get("wave_direction_degrees")
                if wave_dir is not None:
                    wave_dir = float(wave_dir)
                    if not (0.0 <= wave_dir <= 360.0):
                        logger.warning(f"Rejected record with implausible wave direction: {wave_dir}° (bounds: 0.0 to 360.0)")
                        counts["rejected"] += 1
                        continue

                wind_spd = rec.get("wind_speed_knots")
                if wind_spd is not None:
                    wind_spd = float(wind_spd)
                    if not (0.0 <= wind_spd <= 200.0):
                        logger.warning(f"Rejected record with implausible wind speed: {wind_spd} knots (bounds: 0.0 to 200.0)")
                        counts["rejected"] += 1
                        continue

                counts["valid"] += 1
                validated_records.append({
                    "source_id": "historical_archive",
                    "observation_time": obs_time,
                    "latitude": lat,
                    "longitude": lon,
                    "sea_surface_temperature_celsius": sst,
                    "wave_height_meters": wave_h,
                    "wave_period_seconds": wave_p,
                    "wave_direction_degrees": wave_dir,
                    "wind_speed_knots": wind_spd,
                    "wind_direction_degrees": rec.get("wind_direction_degrees"),
                    "chlorophyll_mg_m3": rec.get("chlorophyll_mg_m3"),
                    "metadata_json": {
                        "is_historical": True,
                        "is_sample_fixture": True,
                        "season": rec.get("season"),
                        "evidence_id": ev_id,
                    },
                })
            except Exception as e:
                logger.warning(f"Rejected corrupted record: {rec} (Error: {e})")
                counts["rejected"] += 1

        return validated_records, evidence, counts

    async def fetch_archive_from_open_meteo(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        timeout: float = 12.0,
    ) -> tuple[list[dict[str, Any]], EvidenceRecord | None, list[str]]:
        """
        Queries Open-Meteo Historical Archive API for past atmospheric weather reanalysis.
        Note: temperature_2m is 2-meter atmospheric air temperature, NOT sea surface temperature.
        SST is marked unavailable for this endpoint.
        """
        limitations: list[str] = []
        archive_url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ["temperature_2m", "wind_speed_10m", "wind_direction_10m"],
            "timezone": "UTC",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(archive_url, params=params)
                resp.raise_for_status()
                data = resp.json()

            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps_air_2m = hourly.get("temperature_2m", [])
            winds = hourly.get("wind_speed_10m", [])
            wind_dirs = hourly.get("wind_direction_10m", [])

            ev_id = f"ev-era5-live-{uuid.uuid4().hex[:10]}"
            evidence = EvidenceRecord(
                id=ev_id,
                source_name="Open-Meteo ERA5 Atmospheric Weather Archive",
                source_uri=f"{archive_url}?latitude={latitude}&longitude={longitude}",
                observation_time=datetime.fromisoformat(times[0].replace("Z", "+00:00")) if times else None,
                retrieval_time=datetime.now(UTC),
                latitude=latitude,
                longitude=longitude,
                data_type="historical_weather_reanalysis",
                value={"sample_count": len(times)},
                unit="°C (air), km/h (wind)",
                metadata={
                    "dataset": "ERA5 atmospheric reanalysis",
                    "is_historical": True,
                    "sea_surface_temperature_available": False,
                    "air_temperature_2m_available": True,
                    "license": "Copernicus Climate Change Service / ECMWF ERA5 Open Data",
                },
            )

            records = []
            for i in range(len(times)):
                dt = datetime.fromisoformat(times[i].replace("Z", "+00:00"))
                # wind_speed_10m is km/h -> convert to knots: 1 km/h = 0.539957 knots
                wind_knots = round(winds[i] * 0.539957, 1) if i < len(winds) and winds[i] is not None else None
                wind_dir = wind_dirs[i] if i < len(wind_dirs) and wind_dirs[i] is not None else None
                air_temp = temps_air_2m[i] if i < len(temps_air_2m) else None
                records.append({
                    "source_id": "open_meteo_weather_archive",
                    "observation_time": dt,
                    "latitude": latitude,
                    "longitude": longitude,
                    # SST is NOT 2m air temperature; marked unavailable
                    "sea_surface_temperature_celsius": None,
                    "wave_height_meters": None,
                    "wave_period_seconds": None,
                    "wave_direction_degrees": None,
                    "wind_speed_knots": wind_knots,
                    "wind_direction_degrees": wind_dir,
                    "chlorophyll_mg_m3": None,
                    "metadata_json": {
                        "is_historical": True,
                        "evidence_id": ev_id,
                        "temperature_2m_celsius": air_temp,
                    },
                })

            limitations.append(
                "Open-Meteo Historical Weather Archive provides 2m atmospheric air temperature (temperature_2m) and 10m wind, "
                "NOT sea surface temperature (SST). Sea surface temperature is marked unavailable."
            )
            return records, evidence, limitations

        except Exception as e:
            limitations.append(f"Historical archive query failed ({e!s}).")
            return [], None, limitations

    async def fetch_marine_archive(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        timeout: float = 15.0,
    ) -> tuple[list[dict[str, Any]], EvidenceRecord | None, list[str]]:
        """
        Queries Open-Meteo Marine API for genuine historical oceanographic reanalysis/hindcast records.
        Retrieves real sea-surface temperature, wave dynamics (height, period, direction),
        and ocean currents (velocity, direction).
        Endpoint: https://marine-api.open-meteo.com/v1/marine
        License: Creative Commons Attribution 4.0 International (CC BY 4.0).
        Units: °C, m, s, deg, m/s (velocity converted from km/h).
        """
        limitations: list[str] = []
        marine_url = "https://marine-api.open-meteo.com/v1/marine"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": [
                "sea_surface_temperature",
                "wave_height",
                "wave_period",
                "wave_direction",
                "ocean_current_velocity",
                "ocean_current_direction",
            ],
            "timezone": "UTC",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(marine_url, params=params)
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

            ev_id = f"ev-marine-hist-{uuid.uuid4().hex[:10]}"
            obs_dt = datetime.fromisoformat(times[0].replace("Z", "+00:00")) if times else None
            if obs_dt and obs_dt.tzinfo is None:
                obs_dt = obs_dt.replace(tzinfo=UTC)

            evidence = EvidenceRecord(
                id=ev_id,
                source_name="Open-Meteo Marine Historical Archive",
                source_uri=f"{marine_url}?latitude={latitude}&longitude={longitude}&start_date={start_date}&end_date={end_date}",
                observation_time=obs_dt,
                retrieval_time=datetime.now(UTC),
                latitude=latitude,
                longitude=longitude,
                data_type="historical_marine_reanalysis",
                value={"sample_count": len(times), "start_date": start_date, "end_date": end_date},
                unit="°C, m, s, deg, m/s",
                metadata={
                    "dataset": "Open-Meteo Marine Global Ocean Hindcast/Reanalysis",
                    "is_historical": True,
                    "is_sample_fixture": False,
                    "data_nature": "oceanographic_reanalysis",
                    "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
                    "sea_surface_temperature_available": True,
                    "wave_dynamics_available": True,
                    "ocean_currents_available": True,
                },
            )

            records = []
            for i in range(len(times)):
                t_str = times[i]
                dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)

                curr_kmh = current_velocities[i] if i < len(current_velocities) and current_velocities[i] is not None else None
                curr_mps = round(curr_kmh / 3.6, 3) if curr_kmh is not None else None
                curr_dir = current_directions[i] if i < len(current_directions) and current_directions[i] is not None else None

                records.append({
                    "source_id": "open_meteo_marine_archive",
                    "observation_time": dt,
                    "latitude": latitude,
                    "longitude": longitude,
                    "sea_surface_temperature_celsius": ssts[i] if i < len(ssts) and ssts[i] is not None else None,
                    "wave_height_meters": wave_heights[i] if i < len(wave_heights) and wave_heights[i] is not None else None,
                    "wave_period_seconds": wave_periods[i] if i < len(wave_periods) and wave_periods[i] is not None else None,
                    "wave_direction_degrees": wave_directions[i] if i < len(wave_directions) and wave_directions[i] is not None else None,
                    "ocean_current_velocity_mps": curr_mps,
                    "ocean_current_direction_degrees": curr_dir,
                    "wind_speed_knots": None,
                    "wind_direction_degrees": None,
                    "chlorophyll_mg_m3": None,
                    "metadata_json": {
                        "is_historical": True,
                        "evidence_id": ev_id,
                        "source": "open_meteo_marine_archive",
                    },
                })

            return records, evidence, limitations

        except Exception as e:
            limitations.append(f"Historical marine archive query failed ({e!s}).")
            return [], None, limitations

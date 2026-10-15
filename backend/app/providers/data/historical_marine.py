import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import httpx

from app.core.logging import logger
from app.schemas.marine import MarineObservationPoint
from app.schemas.evidence import EvidenceRecord

class HistoricalMarineDataLoader:
    """
    Historical marine data provider adapter.
    Parses, validates, and normalizes historical scientific oceanographic records
    (NOAA ERDDAP / Copernicus Marine / ERA5 reanalysis).
    """
    def __init__(self, default_data_path: Optional[str] = None):
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
        self, file_path: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], EvidenceRecord, Dict[str, int]]:
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

        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        meta = raw_data.get("dataset_metadata", {})
        source_name = meta.get("source_name", "Historical Marine Scientific Archive")
        source_url = meta.get("source_url", str(path))

        ev_id = f"ev-hist-{uuid.uuid4().hex[:10]}"
        evidence = EvidenceRecord(
            id=ev_id,
            source_name=source_name,
            source_uri=source_url,
            observation_time=datetime(2025, 6, 1, tzinfo=timezone.utc),
            retrieval_time=datetime.now(timezone.utc),
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
                "data_nature": meta.get("data_nature", "sample_reference_fixture"),
                "is_authoritative_bulk_archive": False,
            },
        )

        counts = {"processed": 0, "valid": 0, "rejected": 0}
        validated_records: List[Dict[str, Any]] = []

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
    ) -> Tuple[List[Dict[str, Any]], Optional[EvidenceRecord], List[str]]:
        """
        Queries Open-Meteo Historical Archive API for past marine/weather reanalysis.
        """
        limitations: List[str] = []
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
            temps = hourly.get("temperature_2m", [])
            winds = hourly.get("wind_speed_10m", [])

            ev_id = f"ev-era5-live-{uuid.uuid4().hex[:10]}"
            evidence = EvidenceRecord(
                id=ev_id,
                source_name="Open-Meteo ERA5 Historical Archive",
                source_uri=f"{archive_url}?latitude={latitude}&longitude={longitude}",
                observation_time=datetime.fromisoformat(times[0].replace("Z", "+00:00")) if times else None,
                retrieval_time=datetime.now(timezone.utc),
                latitude=latitude,
                longitude=longitude,
                data_type="historical_reanalysis_series",
                value={"sample_count": len(times)},
                unit="°C, km/h",
                metadata={"dataset": "ERA5 reanalysis", "is_historical": True},
            )

            records = []
            for i in range(len(times)):
                dt = datetime.fromisoformat(times[i].replace("Z", "+00:00"))
                # wind_speed_10m is km/h -> convert to knots: 1 km/h = 0.539957 knots
                wind_knots = round(winds[i] * 0.539957, 1) if i < len(winds) and winds[i] is not None else None
                records.append({
                    "source_id": "open_meteo_archive",
                    "observation_time": dt,
                    "latitude": latitude,
                    "longitude": longitude,
                    "sea_surface_temperature_celsius": temps[i] if i < len(temps) else None,
                    "wave_height_meters": None,
                    "wave_period_seconds": None,
                    "wave_direction_degrees": None,
                    "wind_speed_knots": wind_knots,
                    "wind_direction_degrees": None,
                    "chlorophyll_mg_m3": None,
                    "metadata_json": {"is_historical": True, "evidence_id": ev_id},
                })
            return records, evidence, limitations

        except Exception as e:
            limitations.append(f"Historical archive query failed ({str(e)}). Falling back to local scientific archive.")
            return [], None, limitations

from typing import Optional
from fastapi import APIRouter, Query
from app.schemas.marine import MarineObservationResponse, MarineObservationPoint

router = APIRouter()

from app.providers.data.open_meteo import OpenMeteoMarineClient

client = OpenMeteoMarineClient()

@router.get("/observations", response_model=MarineObservationResponse, tags=["Marine"])
async def get_marine_observations(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in WGS84"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in WGS84"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """
    Retrieves marine observations (waves, currents, sea state) for the requested coordinates.
    """
    obs, evidence_records, limitations = await client.fetch_marine_data(
        latitude=lat, longitude=lon, start_date=start_date, end_date=end_date
    )
    return MarineObservationResponse(
        latitude=lat,
        longitude=lon,
        source="Open-Meteo Marine API",
        observations=obs,
        evidence=evidence_records,
        limitations=limitations,
    )

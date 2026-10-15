from typing import Optional
from fastapi import APIRouter, Query
from app.schemas.marine import MarineObservationResponse, MarineObservationPoint

router = APIRouter()

@router.get("/observations", response_model=MarineObservationResponse, tags=["Marine"])
async def get_marine_observations(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude in WGS84"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude in WGS84"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """
    Retrieves marine observations (SST, wave height, winds, chlorophyll) for the requested coordinates.
    """
    # Baseline contract response
    return MarineObservationResponse(
        latitude=lat,
        longitude=lon,
        source="Open-Meteo Marine API / Local Store",
        observations=[],
        evidence=[],
        limitations=["Marine observations endpoint ready for live data provider ingestion."],
    )

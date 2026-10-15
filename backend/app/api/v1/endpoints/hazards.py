from typing import Optional, List
from fastapi import APIRouter, Query
from app.schemas.hazards import HazardEventResponse

router = APIRouter()

@router.get("", response_model=List[HazardEventResponse], tags=["Hazards"])
async def list_hazards(
    basin: Optional[str] = Query(None, description="Basin name (e.g., arabian_sea, indian_ocean)"),
    status: Optional[str] = Query(None, description="Event status: active or historical"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Retrieves hazard events (cyclones, storm surges, alerts) from NOAA IBTrACS and GDACS.
    """
    # Baseline contract response
    return []

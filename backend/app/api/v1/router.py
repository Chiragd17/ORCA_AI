from fastapi import APIRouter
from app.api.v1.endpoints import health, marine, hazards, investigations, reports

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(marine.router, prefix="/marine")
api_router.include_router(hazards.router, prefix="/hazards")
api_router.include_router(investigations.router, prefix="/investigations")
api_router.include_router(reports.router, prefix="/reports")

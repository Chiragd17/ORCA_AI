from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.v1.router import api_router
from app.api.v1.endpoints.health import router as health_router

setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Open-Source Marine and Coastal Intelligence Platform API",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root health endpoint
app.include_router(health_router)

# Mount v1 API
app.include_router(api_router, prefix="/api/v1")

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to ORCA Marine & Coastal Intelligence Platform",
        "docs": "/api/v1/docs",
        "health": "/health",
    }

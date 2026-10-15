import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_get_marine_observations_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/marine/observations?lat=12.87&lon=74.88")
    assert response.status_code == 200
    data = response.json()
    assert data["latitude"] == 12.87
    assert data["longitude"] == 74.88
    assert "observations" in data
    assert len(data["observations"]) > 0
    assert len(data["evidence"]) > 0
    assert "limitations" in data
    obs_sample = data["observations"][0]
    assert "ocean_current_velocity_mps" in obs_sample
    assert "ocean_current_direction_degrees" in obs_sample
    assert "sea_surface_temperature_celsius" in obs_sample
    assert "wave_height_meters" in obs_sample

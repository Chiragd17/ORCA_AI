import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.base import Base
from app.db.repositories.marine import MarineRepository
from app.providers.data.historical_marine import HistoricalMarineDataLoader

@pytest.fixture
async def in_memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()

@pytest.mark.asyncio
async def test_marine_repository_idempotency(in_memory_db: AsyncSession):
    repo = MarineRepository(in_memory_db)
    
    # 1. Ensure DataSource exists
    source = await repo.ensure_data_source(
        source_id="open_meteo",
        name="Open-Meteo Marine API",
        base_url="https://marine-api.open-meteo.com/v1/marine",
    )
    assert source.id == "open_meteo"

    # 2. Ingest initial record
    t0 = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    records = [
        {
            "source_id": "open_meteo",
            "observation_time": t0,
            "latitude": 12.87,
            "longitude": 74.88,
            "sea_surface_temperature_celsius": 28.9,
            "wave_height_meters": 1.4,
            "wave_period_seconds": 7.5,
        }
    ]

    res1 = await repo.bulk_ingest(records)
    assert res1["processed"] == 1
    assert res1["inserted"] == 1
    assert res1["updated"] == 0

    # 3. Repeat EXACT same ingestion (Idempotency test)
    res2 = await repo.bulk_ingest(records)
    assert res2["processed"] == 1
    assert res2["inserted"] == 0
    assert res2["updated"] == 1  # Updated without duplicating

    # 4. Query observations to confirm count is still exactly 1
    stored = await repo.query_observations(
        latitude=12.87,
        longitude=74.88,
        radius_km=10.0,
    )
    assert len(stored) == 1
    assert stored[0].wave_height_meters == 1.4
    assert stored[0].sea_surface_temperature_celsius == 28.9

@pytest.mark.asyncio
async def test_marine_repository_historical_ingestion(in_memory_db: AsyncSession):
    repo = MarineRepository(in_memory_db)
    loader = HistoricalMarineDataLoader()
    records, evidence, counts = loader.load_local_dataset()

    await repo.ensure_data_source(
        source_id="historical_archive",
        name=evidence.source_name,
        base_url=evidence.source_uri,
    )

    # Ingest all historical records
    ingest_res = await repo.bulk_ingest(records)
    assert ingest_res["processed"] == counts["valid"]
    assert ingest_res["inserted"] == counts["valid"]
    assert ingest_res["failed"] == 0

    # Re-run same batch to verify zero duplicate creation
    reingest_res = await repo.bulk_ingest(records)
    assert reingest_res["inserted"] == 0
    assert reingest_res["updated"] == counts["valid"]

    # Spatial query for Karnataka Coast offshore records
    queried = await repo.query_observations(
        latitude=12.87,
        longitude=74.88,
        radius_km=25.0,
    )
    assert len(queried) == counts["valid"]

@pytest.mark.asyncio
async def test_marine_repository_spatial_filtering(in_memory_db: AsyncSession):
    repo = MarineRepository(in_memory_db)
    await repo.ensure_data_source("test_src", "Test Source")

    t = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    # Point A: Mangaluru (12.87, 74.88)
    # Point B: Mumbai (~18.92, 72.83) > 700km away
    records = [
        {
            "source_id": "test_src",
            "observation_time": t,
            "latitude": 12.87,
            "longitude": 74.88,
            "wave_height_meters": 1.5,
        },
        {
            "source_id": "test_src",
            "observation_time": t,
            "latitude": 18.92,
            "longitude": 72.83,
            "wave_height_meters": 2.2,
        },
    ]
    await repo.bulk_ingest(records)

    # Query within 50km of Mangaluru
    nearby = await repo.query_observations(latitude=12.87, longitude=74.88, radius_km=50.0)
    assert len(nearby) == 1
    assert nearby[0].latitude == 12.87

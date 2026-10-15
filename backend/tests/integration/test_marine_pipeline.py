import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.base import Base
from app.db.repositories.marine import MarineRepository
from app.providers.data.historical_marine import HistoricalMarineDataLoader
from app.agents.ocean_research.agent import OceanResearchAgent
from app.agents.base import InvestigationTask, AgentStatus
from app.schemas.investigations import WorkspaceType
from app.schemas.evidence import FindingCategory

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

    # Spatial query for Mangaluru station offshore records (within 25km)
    mangaluru_records = await repo.query_observations(
        latitude=12.87,
        longitude=74.88,
        radius_km=25.0,
    )
    assert len(mangaluru_records) == 15

    # Spatial query for Karwar station offshore records (within 25km)
    karwar_records = await repo.query_observations(
        latitude=14.80,
        longitude=74.12,
        radius_km=25.0,
    )
    assert len(karwar_records) == 8

    # Regional query encompassing both stations (within 300km)
    all_regional = await repo.query_observations(
        latitude=13.50,
        longitude=74.50,
        radius_km=300.0,
    )
    assert len(all_regional) == counts["valid"]

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

@pytest.mark.asyncio
async def test_ocean_research_agent_with_persisted_repository(in_memory_db: AsyncSession):
    repo = MarineRepository(in_memory_db)
    loader = HistoricalMarineDataLoader()
    records, evidence, _ = loader.load_local_dataset()

    await repo.ensure_data_source(
        source_id="historical_archive",
        name=evidence.source_name,
        base_url=evidence.source_uri,
    )
    await repo.bulk_ingest(records)

    # Instantiate agent injected with persisted database repository
    agent = OceanResearchAgent(marine_repository=repo)
    task = InvestigationTask(
        investigation_id="task-persisted-repo-01",
        workspace=WorkspaceType.MARINE_MONITORING,
        prompt="Analyze historical sea state and compare Southwest Monsoon waves against Post-Monsoon baseline",
        latitude=12.87,
        longitude=74.88,
    )

    result = await agent.run(task)
    assert result.agent_id == "ocean_research"
    assert result.status == AgentStatus.COMPLETED
    assert len(result.findings) >= 2

    # Verify deterministic calculation from database records
    comp_findings = [f for f in result.findings if f.category == FindingCategory.DETERMINISTIC_CALCULATION]
    assert len(comp_findings) > 0

@pytest.mark.asyncio
async def test_marine_repository_record_versioning_update(in_memory_db: AsyncSession):
    """
    Verifies that re-publishing an observation with updated or calibrated measurements
    updates the existing record in place without duplicating the logical entity.
    """
    repo = MarineRepository(in_memory_db)
    await repo.ensure_data_source("test_calib_src", "Calibration Station")

    t_obs = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
    initial_rec = {
        "source_id": "test_calib_src",
        "observation_time": t_obs,
        "latitude": 13.0,
        "longitude": 74.5,
        "wave_height_meters": 2.1,
        "metadata_json": {"version": 1, "quality_flag": "preliminary"},
    }
    await repo.bulk_ingest([initial_rec])

    # Calibrated revised publication for the exact same timestamp and location
    revised_rec = {
        "source_id": "test_calib_src",
        "observation_time": t_obs,
        "latitude": 13.0,
        "longitude": 74.5,
        "wave_height_meters": 2.35,  # Calibrated value
        "metadata_json": {"version": 2, "quality_flag": "quality_controlled"},
    }
    await repo.bulk_ingest([revised_rec])

    stored = await repo.query_observations(latitude=13.0, longitude=74.5, radius_km=5.0)
    assert len(stored) == 1
    assert stored[0].wave_height_meters == 2.35
    assert stored[0].metadata_json["version"] == 2
    assert stored[0].metadata_json["quality_flag"] == "quality_controlled"

@pytest.mark.asyncio
async def test_marine_repository_metadata_and_provenance_retention(in_memory_db: AsyncSession):
    """
    Verifies that complete source metadata, evidence IDs, and quality attributes
    survive persistence and retrieval intact.
    """
    repo = MarineRepository(in_memory_db)
    await repo.ensure_data_source("prov_src", "Provenance Source")

    t_obs = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)
    rec = {
        "source_id": "prov_src",
        "observation_time": t_obs,
        "latitude": 12.87,
        "longitude": 74.88,
        "sea_surface_temperature_celsius": 28.7,
        "wave_height_meters": 1.6,
        "metadata_json": {
            "evidence_id": "ev-provenance-test-01",
            "sensor": "acoustic_doppler_current_profiler",
            "qa_status": "passed_level_2",
            "reanalysis_grid": "0.1deg",
        },
    }
    await repo.bulk_ingest([rec])

    retrieved = await repo.query_observations(latitude=12.87, longitude=74.88, radius_km=10.0)
    assert len(retrieved) == 1
    meta = retrieved[0].metadata_json
    assert meta["evidence_id"] == "ev-provenance-test-01"
    assert meta["sensor"] == "acoustic_doppler_current_profiler"
    assert meta["qa_status"] == "passed_level_2"
    assert meta["reanalysis_grid"] == "0.1deg"



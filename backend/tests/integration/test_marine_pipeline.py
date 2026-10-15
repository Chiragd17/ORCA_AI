from datetime import UTC, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.base import AgentStatus, InvestigationTask
from app.agents.ocean_research.agent import OceanResearchAgent
from app.db.base import Base
from app.db.repositories.marine import MarineRepository
from app.providers.data.historical_marine import HistoricalMarineDataLoader
from app.schemas.evidence import FindingCategory
from app.schemas.investigations import WorkspaceType


@pytest.fixture
async def in_memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def enable_sqlite_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
    t0 = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
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

    t = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
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

    t_obs = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
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

    t_obs = datetime(2026, 9, 15, 6, 0, tzinfo=UTC)
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


@pytest.mark.asyncio
async def test_import_historical_marine_data_service(in_memory_db: AsyncSession):
    """
    Verifies that the import_historical_marine_data service ingests the real processed
    scientific dataset into the repository with 100% success and zero validation failures.
    """
    from contextlib import asynccontextmanager
    from unittest.mock import patch

    from app.services.import_marine_data import import_historical_marine_data

    @asynccontextmanager
    async def mock_session():
        yield in_memory_db

    with patch("app.services.import_marine_data.AsyncSessionLocal", side_effect=mock_session):
        res = await import_historical_marine_data()
        assert res["status"] == "success"
        assert res["loaded_counts"]["valid"] == 23
        assert res["ingest_summary"]["inserted"] == 23
        assert res["ingest_summary"]["failed"] == 0


@pytest.mark.asyncio
async def test_marine_repository_foreign_key_rejection(in_memory_db: AsyncSession):
    """
    Regression test: foreign key enforcement on MarineObservation.source_id -> data_sources.id.
    Inserting a record with an unregistered source_id MUST fail with an integrity violation.
    """
    repo = MarineRepository(in_memory_db)
    t0 = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    records = [
        {
            "source_id": "nonexistent_source_id_xyz",
            "observation_time": t0,
            "latitude": 12.87,
            "longitude": 74.88,
            "sea_surface_temperature_celsius": 28.5,
        }
    ]

    ingest_res = await repo.bulk_ingest(records)
    # With foreign keys enforced, the insert fails and is counted as failed
    assert ingest_res["failed"] == 1
    assert ingest_res["inserted"] == 0

    # Query observations to confirm nothing was saved
    obs = await repo.query_observations(12.87, 74.88, radius_km=10.0)
    assert len(obs) == 0


@pytest.mark.asyncio
async def test_import_marine_data_mismatched_source_id_fails_truthfully(in_memory_db: AsyncSession):
    """
    Regression test: verifies that if ensure_data_source registers a source ID that does
    not match what records have, the service truthfully reports status="failed" and does not claim success.
    """
    from contextlib import asynccontextmanager
    from unittest.mock import patch

    from app.services.import_marine_data import import_historical_marine_data

    @asynccontextmanager
    async def mock_session():
        yield in_memory_db

    # Force a mismatch: ensure_data_source registers copernicus_mismatch but records have historical_archive
    original_ensure = MarineRepository.ensure_data_source

    async def mismatched_ensure(self, source_id, name, **kwargs):
        return await original_ensure(self, "mismatched_source_id_only", name, **kwargs)

    with patch("app.services.import_marine_data.AsyncSessionLocal", side_effect=mock_session), \
         patch.object(MarineRepository, "ensure_data_source", mismatched_ensure):
        res = await import_historical_marine_data()
        assert res["status"] == "failed"
        assert res["ingest_summary"]["failed"] == 23
        assert res["ingest_summary"]["inserted"] == 0


@pytest.mark.asyncio
async def test_marine_repository_partial_update_field_preservation(in_memory_db: AsyncSession):
    """
    Regression test: non-destructive upsert.
    Preserves existing valid fields (SST, wave height, wave period, ocean currents)
    when an incoming update contains only partial data (None for other fields).
    """
    repo = MarineRepository(in_memory_db)
    await repo.ensure_data_source(
        source_id="test_partial_source",
        name="Test Partial Update Provider",
    )

    t0 = datetime(2026, 10, 15, 6, 0, tzinfo=UTC)

    # 1. Initial complete observation
    rec1 = {
        "source_id": "test_partial_source",
        "observation_time": t0,
        "latitude": 13.00,
        "longitude": 74.50,
        "sea_surface_temperature_celsius": 28.5,
        "wave_height_meters": 1.75,
        "wave_period_seconds": 8.0,
        "wave_direction_degrees": 240.0,
        "ocean_current_velocity_mps": 0.42,
        "ocean_current_direction_degrees": 180.0,
        "wind_speed_knots": 12.0,
        "metadata_json": {"source": "buoy_initial", "calibrated": True},
    }
    await repo.bulk_ingest([rec1])

    # Verify initial record
    stored = await repo.query_observations(13.00, 74.50, radius_km=5.0)
    assert len(stored) == 1
    assert stored[0].sea_surface_temperature_celsius == 28.5
    assert stored[0].wave_height_meters == 1.75
    assert stored[0].ocean_current_velocity_mps == 0.42
    assert stored[0].wind_speed_knots == 12.0
    assert stored[0].metadata_json.get("calibrated") is True

    # 2. Incoming partial update: updates SST and wind, leaves waves and ocean currents as None
    rec2 = {
        "source_id": "test_partial_source",
        "observation_time": t0,
        "latitude": 13.00,
        "longitude": 74.50,
        "sea_surface_temperature_celsius": 29.1,
        "wave_height_meters": None,
        "wave_period_seconds": None,
        "wave_direction_degrees": None,
        "ocean_current_velocity_mps": None,
        "ocean_current_direction_degrees": None,
        "wind_speed_knots": 15.5,
        "metadata_json": {"update_batch": "satellite_sst_pass"},
    }
    update_res = await repo.bulk_ingest([rec2])
    assert update_res["updated"] == 1
    assert update_res["inserted"] == 0

    # 3. Verify that wave_height and ocean currents were PRESERVED and not erased to None
    refreshed = await repo.query_observations(13.00, 74.50, radius_km=5.0)
    assert len(refreshed) == 1
    assert refreshed[0].sea_surface_temperature_celsius == 29.1  # Updated
    assert refreshed[0].wind_speed_knots == 15.5  # Updated
    assert refreshed[0].wave_height_meters == 1.75  # Preserved!
    assert refreshed[0].wave_period_seconds == 8.0  # Preserved!
    assert refreshed[0].wave_direction_degrees == 240.0  # Preserved!
    assert refreshed[0].ocean_current_velocity_mps == 0.42  # Preserved!
    assert refreshed[0].ocean_current_direction_degrees == 180.0  # Preserved!
    # Metadata was merged, not erased
    assert refreshed[0].metadata_json.get("calibrated") is True
    assert refreshed[0].metadata_json.get("update_batch") == "satellite_sst_pass"


@pytest.mark.asyncio
async def test_marine_repository_sequential_repeated_and_overlapping_batches(in_memory_db: AsyncSession):
    """
    Regression test: tests repeated sequential ingestion idempotency and multi-batch ingestion
    using identical and overlapping batches.
    """
    repo = MarineRepository(in_memory_db)
    await repo.ensure_data_source("sequential_test_source", "Sequential Batch Testing Source")

    t_base = datetime(2026, 10, 15, 0, 0, tzinfo=UTC)
    batch = [
        {
            "source_id": "sequential_test_source",
            "observation_time": t_base.replace(hour=h),
            "latitude": 12.0 + h * 0.1,
            "longitude": 74.0 + h * 0.1,
            "wave_height_meters": 1.0 + h * 0.1,
        }
        for h in range(5)
    ]

    # First ingestion run: all records are newly inserted
    res1 = await repo.bulk_ingest(batch)
    assert res1["inserted"] == 5
    assert res1["updated"] == 0
    assert res1["failed"] == 0

    # Repeated ingestion run of identical batch: all records are updated in place idempotently
    res2 = await repo.bulk_ingest(batch)
    assert res2["inserted"] == 0
    assert res2["updated"] == 5
    assert res2["failed"] == 0

    # Overlapping batch with partially new, partially existing records
    overlapping_batch = [
        {
            "source_id": "sequential_test_source",
            "observation_time": t_base.replace(hour=h),
            "latitude": 12.0 + h * 0.1,
            "longitude": 74.0 + h * 0.1,
            "wave_height_meters": 1.0 + h * 0.1,
        }
        for h in range(3, 8)  # h=3,4 exist; h=5,6,7 are new
    ]
    res3 = await repo.bulk_ingest(overlapping_batch)
    assert res3["inserted"] == 3
    assert res3["updated"] == 2
    assert res3["failed"] == 0

    # Ensure total persisted count is exactly 8 unique records without duplicates
    all_obs = await repo.query_observations(12.35, 74.35, radius_km=100.0)
    assert len(all_obs) == 8


@pytest.mark.asyncio
async def test_marine_repository_high_latitude_and_antimeridian_wrapping(in_memory_db: AsyncSession):
    """
    Regression test: verifies spherical bounding box queries at high latitudes
    and longitude wrapping across the antimeridian (+/-180.0).
    """
    repo = MarineRepository(in_memory_db)
    await repo.ensure_data_source("polar_pacific_source", "Polar and Pacific Source")

    t0 = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    # 1. Antimeridian test points (around 180°/-180° in Bering Sea/Aleutians)
    p_west = {
        "source_id": "polar_pacific_source",
        "observation_time": t0,
        "latitude": 52.0,
        "longitude": 179.8,  # East longitude (near 180)
        "wave_height_meters": 3.2,
    }
    p_east = {
        "source_id": "polar_pacific_source",
        "observation_time": t0,
        "latitude": 52.0,
        "longitude": -179.8,  # West longitude (across antimeridian)
        "wave_height_meters": 3.4,
    }
    await repo.bulk_ingest([p_west, p_east])

    # Query centered at 52.0°N, 179.9°E with radius 50km (which spans the -180/180 border)
    results = await repo.query_observations(latitude=52.0, longitude=179.9, radius_km=50.0)
    assert len(results) == 2  # Both points retrieved across the antimeridian seam!

    # 2. High latitude point (85.0°N in Arctic Ocean)
    p_arctic = {
        "source_id": "polar_pacific_source",
        "observation_time": t0,
        "latitude": 85.0,
        "longitude": 10.0,
        "wave_height_meters": 0.5,
    }
    await repo.bulk_ingest([p_arctic])

    arctic_res = await repo.query_observations(latitude=85.0, longitude=10.0, radius_km=25.0)
    assert len(arctic_res) == 1
    assert arctic_res[0].wave_height_meters == 0.5


def _is_postgres_env_available() -> bool:
    """Helper to detect if live PostgreSQL is available for real database tests."""
    import os
    return bool(os.getenv("RUN_REAL_POSTGRES_TESTS", "").lower() in ("1", "true"))


@pytest.mark.skipif(not _is_postgres_env_available(), reason="Genuine PostgreSQL environment not available or not configured (RUN_REAL_POSTGRES_TESTS != 1)")
@pytest.mark.asyncio
async def test_postgresql_real_db_foreign_key_and_uniqueness():
    """
    Test suite for genuine PostgreSQL database operations when configured.
    Verifies actual PostgreSQL UNIQUE constraint enforcement and Foreign Key error handling.
    """
    from sqlalchemy.exc import IntegrityError

    from app.db.base import Base
    from app.db.session import async_session_maker, engine

    # Create approved tables on the actual PostgreSQL instance if not present
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        repo = MarineRepository(session)
        source_id = "real_pg_verified_source"
        await repo.ensure_data_source(source_id, "Real PostgreSQL Verified Source")

        t_obs = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)

        # 1. Insert valid observation
        rec_valid = {
            "source_id": source_id,
            "observation_time": t_obs,
            "latitude": 13.0,
            "longitude": 74.5,
            "sea_surface_temperature_celsius": 29.1,
            "wave_height_meters": 1.7,
        }
        upserted = await repo.upsert_observation(rec_valid)
        assert upserted.id is not None
        assert upserted.wave_height_meters == 1.7

        # 2. Reject record with unknown source_id (foreign key violation)
        rec_invalid_fk = {
            "source_id": "non_existent_source_id_9999",
            "observation_time": t_obs,
            "latitude": 13.0,
            "longitude": 74.5,
            "wave_height_meters": 1.9,
        }
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await repo.upsert_observation(rec_invalid_fk)

        # 3. Verify unique constraint & upsert: updating the same valid entity
        rec_update = {
            "source_id": source_id,
            "observation_time": t_obs,
            "latitude": 13.0,
            "longitude": 74.5,
            "sea_surface_temperature_celsius": 29.4,
            "wave_height_meters": 1.85,  # calibrated value
            "forecast_run_time": datetime(2026, 10, 15, 6, 0, tzinfo=UTC),
        }
        refreshed = await repo.upsert_observation(rec_update)
        assert refreshed.id == upserted.id
        assert refreshed.wave_height_meters == 1.85
        assert refreshed.sea_surface_temperature_celsius == 29.4

        # Verify only 1 record exists at this point
        all_obs = await repo.query_observations(13.0, 74.5, radius_km=10.0)
        matching = [o for o in all_obs if o.source_id == source_id and o.observation_time == t_obs]
        assert len(matching) == 1




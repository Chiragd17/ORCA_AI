from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.base import AgentResult, AgentStatus, InvestigationTask
from app.agents.ocean_research.agent import OceanResearchAgent
from app.db.base import Base
from app.db.repositories.marine import MarineRepository
from app.evidence.registry import EvidenceRegistry
from app.evidence.verification import verify_findings
from app.orchestrator.service import OrchestratorService
from app.providers.data.historical_marine import HistoricalMarineDataLoader
from app.schemas.evidence import FindingCategory
from app.schemas.investigations import (
    EventType,
    InvestigationCreateRequest,
    InvestigationStatus,
    WorkspaceType,
)


def make_mock_marine_payload(start_dt: datetime | None = None, hours: int = 48) -> dict:
    """Deterministic Open-Meteo marine payload mock."""
    base = start_dt or datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    times = [(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00Z") for i in range(hours)]
    return {
        "latitude": 12.87,
        "longitude": 74.88,
        "generationtime_ms": 1.2,
        "utc_offset_seconds": 0,
        "timezone": "UTC",
        "timezone_abbreviation": "UTC",
        "hourly": {
            "time": times,
            "sea_surface_temperature": [28.5 + 0.1 * (i % 5) for i in range(hours)],
            "wave_height": [1.5 + 0.05 * (i % 8) for i in range(hours)],
            "wave_period": [8.0 for _ in range(hours)],
            "wave_direction": [240.0 for _ in range(hours)],
            "ocean_current_velocity": [1.8 for _ in range(hours)],
            "ocean_current_direction": [190.0 for _ in range(hours)],
        },
    }


def make_genuine_historical_records(lat: float = 12.87, lon: float = 74.88) -> list[dict]:
    """Generates genuine, non-fixture historical oceanographic records across Southwest Monsoon and Post-Monsoon."""
    records = []
    # Southwest Monsoon: July 2025 (months 6-9)
    for d in range(1, 13):
        records.append({
            "source_id": "open_meteo_marine_archive",
            "observation_time": datetime(2025, 7, d, 12, 0, tzinfo=UTC),
            "latitude": lat,
            "longitude": lon,
            "sea_surface_temperature_celsius": 28.2 + 0.1 * (d % 3),
            "wave_height_meters": 2.8 + 0.1 * (d % 4),
            "wave_period_seconds": 9.5,
            "wave_direction_degrees": 245.0,
            "ocean_current_velocity_mps": 0.45,
            "ocean_current_direction_degrees": 180.0,
            "wind_speed_knots": 18.0,
            "wind_direction_degrees": 240.0,
            "metadata_json": {
                "data_nature": "oceanographic_reanalysis",
                "is_historical": True,
                "is_sample_fixture": False,
                "scientific_baseline_suitable": True,
                "model": "copernicus_marine",
            },
        })
    # Post-Monsoon: November 2025 (months 10-12)
    for d in range(1, 13):
        records.append({
            "source_id": "open_meteo_marine_archive",
            "observation_time": datetime(2025, 11, d, 12, 0, tzinfo=UTC),
            "latitude": lat,
            "longitude": lon,
            "sea_surface_temperature_celsius": 29.1 + 0.1 * (d % 3),
            "wave_height_meters": 1.2 + 0.05 * (d % 4),
            "wave_period_seconds": 6.5,
            "wave_direction_degrees": 210.0,
            "ocean_current_velocity_mps": 0.25,
            "ocean_current_direction_degrees": 160.0,
            "wind_speed_knots": 8.0,
            "wind_direction_degrees": 60.0,
            "metadata_json": {
                "data_nature": "oceanographic_reanalysis",
                "is_historical": True,
                "is_sample_fixture": False,
                "scientific_baseline_suitable": True,
                "model": "copernicus_marine",
            },
        })
    return records


@pytest.fixture
async def shared_db_session():
    """Isolated async SQLite database session mimicking PostgreSQL SQLAlchemy operations with FK enforcement."""
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
async def test_shared_task_invocation_and_result_schema():
    """
    1. Verify agent invocation using exact shared InvestigationTask contract
    2. Verify result conforms to Pydantic AgentResult schema and types
    """
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent()
        task = InvestigationTask(
            investigation_id="inv-contract-001",
            workspace=WorkspaceType.FISHERMAN,
            prompt="Karnataka offshore marine wave height and sea conditions",
            latitude=12.87,
            longitude=74.88,
            target_time=datetime.now(UTC) + timedelta(hours=6),
            context={"location_name": "Mangaluru Port Offshore"},
        )

        result = await agent.run(task)

        assert isinstance(result, AgentResult)
        assert result.agent_id == "ocean_research"
        assert result.status in [AgentStatus.COMPLETED, AgentStatus.PARTIAL]
        assert isinstance(result.findings, list)
        assert isinstance(result.evidence, list)
        assert isinstance(result.limitations, list)
        assert isinstance(result.errors, list)

        for fnd in result.findings:
            assert fnd.id.startswith("fnd-")
            assert fnd.claim
            assert len(fnd.evidence_ids) > 0
            assert fnd.category in [
                FindingCategory.OBSERVATION,
                FindingCategory.FORECAST,
                FindingCategory.HISTORICAL_RECORD,
                FindingCategory.DETERMINISTIC_CALCULATION,
                FindingCategory.AI_INTERPRETATION,
            ]


@pytest.mark.asyncio
async def test_persisted_repository_evidence_reference_integrity(shared_db_session: AsyncSession):
    """
    3. Marine repository access against genuine persisted reanalysis records.
    4. Evidence references in returned findings referencing persisted DB evidence.
    """
    repo = MarineRepository(shared_db_session)
    await repo.ensure_data_source(
        source_id="open_meteo_marine_archive",
        name="Open-Meteo Marine Historical Archive",
        base_url="https://marine-api.open-meteo.com/v1/marine",
        license_info="CC BY 4.0",
    )
    records = make_genuine_historical_records(lat=12.87, lon=74.88)
    await repo.bulk_ingest(records)

    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent(marine_repository=repo)
        task = InvestigationTask(
            investigation_id="inv-db-evidence-002",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Historical sea surface temperature summary and seasonal monsoon wave height baseline",
            latitude=12.87,
            longitude=74.88,
        )

        result = await agent.run(task)
        assert result.status == AgentStatus.COMPLETED

        # Check evidence record attribution
        db_ev_records = [e for e in result.evidence if "db://postgres" in str(e.source_uri)]
        assert len(db_ev_records) == 1
        db_ev = db_ev_records[0]
        assert db_ev.source_name == "PostgreSQL Marine Repository (ORCA Shared Backend)"
        assert db_ev.metadata["storage"] == "postgresql_shared_repository"
        assert db_ev.metadata["record_count"] >= 10
        assert db_ev.metadata["data_nature"] == "oceanographic_reanalysis"

        # Verify findings cite this database evidence ID
        hist_findings = [
            f for f in result.findings
            if f.category in [FindingCategory.HISTORICAL_RECORD, FindingCategory.DETERMINISTIC_CALCULATION]
        ]
        assert len(hist_findings) > 0
        for f in hist_findings:
            assert db_ev.id in f.evidence_ids
            # Must not be marked as demo/sample fixture
            assert "[SAMPLE FIXTURE" not in f.claim

        # Verify findings through the shared evidence audit system
        reg = EvidenceRegistry()
        reg.register_many(result.evidence)
        summary = verify_findings(result.findings, reg)
        assert summary["unverified"] == 0
        assert summary["insufficient_evidence"] == 0
        assert summary["verified"] == len(result.findings)


@pytest.mark.asyncio
async def test_persisted_sample_fixture_excluded_in_production_mode(shared_db_session: AsyncSession):
    """
    Verifies that sample fixture records persisted in the database are strictly
    EXCLUDED during normal production analysis, and only accessible under explicit demo mode.
    """
    repo = MarineRepository(shared_db_session)
    loader = HistoricalMarineDataLoader()
    fixture_records, fixture_evidence, _ = loader.load_local_dataset()

    await repo.ensure_data_source(
        source_id="historical_archive",
        name=fixture_evidence.source_name,
        base_url=fixture_evidence.source_uri,
    )
    # Ingest the 23-record sample fixture into DB
    await repo.bulk_ingest(fixture_records)

    agent = OceanResearchAgent(marine_repository=repo, demo_mode=False)

    # 1. Normal production query: must NOT use fixture records
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        prod_task = InvestigationTask(
            investigation_id="task-prod-fixture-isolation",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Historical monsoon wave height baseline analysis",
            latitude=12.87,
            longitude=74.88,
        )
        res_prod = await agent.run(prod_task)
        # Fixture records must not produce historical findings in production
        hist_findings_prod = [f for f in res_prod.findings if f.category == FindingCategory.HISTORICAL_RECORD]
        assert len(hist_findings_prod) == 0
        assert any("Offline sample fixture was not substituted in production mode" in lim for lim in res_prod.limitations)

        # 2. Explicit demo mode query: fixtures are permitted and clearly labeled
        demo_task = InvestigationTask(
            investigation_id="task-demo-fixture-permitted",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Historical monsoon wave height baseline analysis",
            latitude=12.87,
            longitude=74.88,
            context={"demo_mode": True},
        )
        res_demo = await agent.run(demo_task)
        demo_findings = [f for f in res_demo.findings if "[SAMPLE FIXTURE / DEMO DATA]" in f.claim]
        assert len(demo_findings) > 0
        assert res_demo.status == AgentStatus.PARTIAL


@pytest.mark.asyncio
async def test_mixed_real_and_fixture_records_isolation(shared_db_session: AsyncSession):
    """
    Verifies that when a database contains both genuine reanalysis records and sample fixtures
    at the same location, normal production analysis isolates and uses ONLY genuine records.
    """
    repo = MarineRepository(shared_db_session)
    await repo.ensure_data_source("open_meteo_marine_archive", "Genuine Reanalysis")
    await repo.ensure_data_source("historical_archive", "Sample Fixture Archive")

    real_records = make_genuine_historical_records(lat=12.87, lon=74.88)
    await repo.bulk_ingest(real_records)

    loader = HistoricalMarineDataLoader()
    fixture_recs, _, _ = loader.load_local_dataset()
    await repo.bulk_ingest(fixture_recs)

    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent(marine_repository=repo, demo_mode=False)
        task = InvestigationTask(
            investigation_id="task-mixed-isolation",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Historical sea surface temperature summary and monsoon analysis",
            latitude=12.87,
            longitude=74.88,
        )
        result = await agent.run(task)
        # Should derive historical findings exclusively from real records
        assert result.status == AgentStatus.COMPLETED
        hist_fnd = [f for f in result.findings if f.category == FindingCategory.HISTORICAL_RECORD]
        assert len(hist_fnd) > 0
        for f in hist_fnd:
            assert "[SAMPLE FIXTURE" not in f.claim
            assert "DEMO FIXTURE" not in f.uncertainty


@pytest.mark.asyncio
async def test_database_failure_graceful_fallback_and_limitation(shared_db_session: AsyncSession):
    """
    6. Database failure behaviour:
       When database repository raises an error, agent does not crash,
       does NOT silently substitute fixture in production mode,
       and explicitly discloses limitation.
    """
    repo = MarineRepository(shared_db_session)
    repo.query_observations = AsyncMock(
        side_effect=OperationalError("SELECT connection failed", None, None)
    )

    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent(marine_repository=repo)
        task = InvestigationTask(
            investigation_id="inv-db-err-003",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Historical sea state and wave height comparison",
            latitude=12.87,
            longitude=74.88,
        )

        # 1. In production mode: database failure must NOT silently substitute fixture
        result = await agent.run(task)
        assert result.status in (AgentStatus.PARTIAL, AgentStatus.UNAVAILABLE)
        fixture_findings = [f for f in result.findings if "SAMPLE FIXTURE" in f.claim]
        assert len(fixture_findings) == 0
        assert any("Database repository query failed" in lim for lim in result.limitations)
        assert any("Offline sample fixture was not substituted in production mode" in lim for lim in result.limitations)

        # 2. In explicit demo mode: fixture is permitted but unmistakably labelled
        task_demo = InvestigationTask(
            investigation_id="inv-db-err-demo-004",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Historical sea state and wave height comparison",
            latitude=12.87,
            longitude=74.88,
            context={"demo_mode": True},
        )
        res_demo = await agent.run(task_demo)
        demo_findings = [f for f in res_demo.findings if "[SAMPLE FIXTURE / DEMO DATA]" in f.claim]
        assert len(demo_findings) > 0
        for f in demo_findings:
            assert "DEMO FIXTURE ONLY" in f.uncertainty
        assert any("SAMPLE FIXTURE / DEMO DATA" in lim for lim in res_demo.limitations)


@pytest.mark.asyncio
async def test_live_provider_outage_historical_analysis_resilience(shared_db_session: AsyncSession):
    """
    7. Historical analysis during live-provider outages:
       Live provider timeout or failure does not block historical analysis from stored real records.
    """
    repo = MarineRepository(shared_db_session)
    await repo.ensure_data_source("open_meteo_marine_archive", "Genuine Reanalysis")
    records = make_genuine_historical_records(lat=12.87, lon=74.88)
    await repo.bulk_ingest(records)

    agent = OceanResearchAgent(marine_repository=repo)
    # Simulate live client complete provider outage
    agent.live_client.fetch_marine_data = AsyncMock(
        return_value=([], [], ["External live provider connection timeout (504 Gateway Timeout)."])
    )

    task = InvestigationTask(
        investigation_id="inv-live-down-004",
        workspace=WorkspaceType.FISHERMAN,
        prompt="Historical monsoon wave height comparison vs post-monsoon baseline",
        latitude=12.87,
        longitude=74.88,
    )

    result = await agent.run(task)
    assert result.status == AgentStatus.COMPLETED
    assert len(result.findings) >= 2
    assert any("504" in lim or "Live provider" in lim or "not retrieved" in lim for lim in result.limitations)


@pytest.mark.asyncio
async def test_live_observation_persistence_into_shared_repository(shared_db_session: AsyncSession):
    """
    Verifies that live observations ingested during agent execution are persisted
    into MarineRepository with observation_time and ingested_at kept distinct.
    """
    repo = MarineRepository(shared_db_session)
    agent = OceanResearchAgent(marine_repository=repo)

    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        task = InvestigationTask(
            investigation_id="inv-persist-live-005",
            workspace=WorkspaceType.FISHERMAN,
            prompt="Current wave height check",
            latitude=12.87,
            longitude=74.88,
        )

        result = await agent.run(task)
        assert result.status == AgentStatus.COMPLETED

        # Verify records were persisted into database repository
        stored_live = await repo.query_observations(latitude=12.87, longitude=74.88, radius_km=10.0)
        assert len(stored_live) > 0
        sample = stored_live[0]
        assert sample.source_id == "open_meteo"
        assert sample.observation_time is not None
        assert "ingested_at" in sample.metadata_json
        ingested_at = datetime.fromisoformat(sample.metadata_json["ingested_at"])
        assert isinstance(ingested_at, datetime)


@pytest.mark.asyncio
async def test_orchestrator_integration_with_ocean_research(shared_db_session: AsyncSession):
    """
    8. Integration with Orchestrator's invocation mechanism:
       Verifies end-to-end execution through OrchestratorService, event bus emissions,
       and evidence verification.
    """
    repo = MarineRepository(shared_db_session)
    await repo.ensure_data_source("open_meteo_marine_archive", "Genuine Reanalysis")
    records = make_genuine_historical_records(lat=12.87, lon=74.88)
    await repo.bulk_ingest(records)

    orchestrator = OrchestratorService()
    ocean_agent = orchestrator._agents.get("ocean_research")
    assert ocean_agent is not None
    assert isinstance(ocean_agent, OceanResearchAgent)
    ocean_agent.set_repository(repo)

    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        request = InvestigationCreateRequest(
            workspace=WorkspaceType.FISHERMAN,
            prompt="Offshore wave conditions and historical monsoon pattern",
            latitude=12.87,
            longitude=74.88,
        )

        response = await orchestrator.execute_investigation(request)

        assert response.status == InvestigationStatus.COMPLETED
        assert response.workspace == WorkspaceType.FISHERMAN
        assert len(response.findings) >= 2

        # Check genuine execution events emitted
        events = orchestrator.get_event_bus(response.id).get_events()
        event_types = [e.event_type for e in events]
        assert EventType.INVESTIGATION_STARTED in event_types
        assert EventType.TOOL_COMPLETED in event_types
        assert EventType.AGENT_STARTED in event_types
        assert EventType.EVIDENCE_ADDED in event_types
        assert EventType.AGENT_COMPLETED in event_types
        assert EventType.VERIFICATION_PASSED in event_types
        assert EventType.INVESTIGATION_COMPLETED in event_types

        # Check evidence registered in orchestrator registry
        reg = orchestrator.get_evidence_registry(response.id)
        all_ev = reg.list_all()
        assert len(all_ev) >= 2


@pytest.mark.asyncio
async def test_agent_status_handling_all_branches():
    """
    5. Correct handling of completed, partial, unavailable, and failed results.
    """
    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        agent = OceanResearchAgent()

        # 1. COMPLETED: Standard valid query
        res_completed = await agent.run(InvestigationTask(
            investigation_id="st-01",
            workspace=WorkspaceType.FISHERMAN,
            prompt="Wave height check",
            latitude=12.87,
            longitude=74.88,
        ))
        assert res_completed.status == AgentStatus.COMPLETED

        # 2. PARTIAL: Prompt requesting unsupported variable (chlorophyll)
        res_partial = await agent.run(InvestigationTask(
            investigation_id="st-02",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Chlorophyll concentration and ocean wave spectra",
            latitude=12.87,
            longitude=74.88,
        ))
        assert res_partial.status == AgentStatus.PARTIAL
        assert any("Chlorophyll" in lim for lim in res_partial.limitations)

        # 3. UNAVAILABLE: Coordinates with no available data and live client returning empty
        with patch.object(agent.live_client, "fetch_marine_data", AsyncMock(return_value=([], [], ["Unavailable"]))):
            res_unavail = await agent.run(InvestigationTask(
                investigation_id="st-03",
                workspace=WorkspaceType.MARINE_MONITORING,
                prompt="Historical data for remote oceanic region",
                latitude=85.0,
                longitude=-170.0,
            ))
            assert res_unavail.status == AgentStatus.UNAVAILABLE

        # 4. FAILED: Invalid coordinates exceeding physical bounds
        res_failed = await agent.run(InvestigationTask(
            investigation_id="st-04",
            workspace=WorkspaceType.FISHERMAN,
            prompt="Invalid coordinate query",
            latitude=120.0,
            longitude=200.0,
        ))
        assert res_failed.status == AgentStatus.FAILED
        assert len(res_failed.errors) > 0


@pytest.mark.asyncio
async def test_repository_injection_via_task_context(shared_db_session: AsyncSession):
    """
    Verifies that OceanResearchAgent dynamically recognizes repositories or sessions
    injected via task.context (useful for per-request FastAPI dependencies).
    """
    repo = MarineRepository(shared_db_session)
    await repo.ensure_data_source("open_meteo_marine_archive", "Genuine Reanalysis")
    records = make_genuine_historical_records(lat=12.87, lon=74.88)
    await repo.bulk_ingest(records)

    agent = OceanResearchAgent()
    assert agent.marine_repository is None

    mock_resp = httpx.Response(200, json=make_mock_marine_payload(), request=httpx.Request("GET", "https://test.local"))
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        # Pass repository in task.context
        task_with_repo = InvestigationTask(
            investigation_id="ctx-repo-01",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Historical sea surface temperature summary",
            latitude=12.87,
            longitude=74.88,
            context={"repository": repo},
        )
        res_repo = await agent.run(task_with_repo)
        assert res_repo.status == AgentStatus.COMPLETED
        assert any("db://postgres" in str(e.source_uri) for e in res_repo.evidence)

        # Pass session in task.context
        task_with_session = InvestigationTask(
            investigation_id="ctx-sess-02",
            workspace=WorkspaceType.MARINE_MONITORING,
            prompt="Historical sea surface temperature summary",
            latitude=12.87,
            longitude=74.88,
            context={"session": shared_db_session},
        )
        res_sess = await agent.run(task_with_session)
        assert res_sess.status == AgentStatus.COMPLETED
        assert any("db://postgres" in str(e.source_uri) for e in res_sess.evidence)

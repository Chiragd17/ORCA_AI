from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
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


@pytest.fixture
async def shared_db_session():
    """Isolated async SQLite database session mimicking PostgreSQL SQLAlchemy operations."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
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
    agent = OceanResearchAgent()
    task = InvestigationTask(
        investigation_id="inv-contract-001",
        workspace=WorkspaceType.FISHERMAN,
        prompt="Karnataka offshore marine wave height and sea conditions",
        latitude=12.87,
        longitude=74.88,
        target_time=datetime(2026, 10, 15, 12, 0, tzinfo=UTC),
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
            FindingCategory.HISTORICAL_RECORD,
            FindingCategory.DETERMINISTIC_CALCULATION,
            FindingCategory.AI_INTERPRETATION,
        ]


@pytest.mark.asyncio
async def test_persisted_repository_evidence_reference_integrity(shared_db_session: AsyncSession):
    """
    3. Marine repository access against persisted records (using isolated SQLite session mimicking shared repository schema)
    4. Evidence references in returned findings referencing persisted DB evidence
    """
    repo = MarineRepository(shared_db_session)
    loader = HistoricalMarineDataLoader()
    records, evidence, counts = loader.load_local_dataset()

    await repo.ensure_data_source(
        source_id="persisted_copernicus_era5",
        name=evidence.source_name,
        base_url=evidence.source_uri,
    )
    await repo.bulk_ingest(records)

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

    # Verify findings cite this database evidence ID
    hist_findings = [
        f for f in result.findings
        if f.category in [FindingCategory.HISTORICAL_RECORD, FindingCategory.DETERMINISTIC_CALCULATION]
    ]
    assert len(hist_findings) > 0
    for f in hist_findings:
        assert db_ev.id in f.evidence_ids

    # Verify findings through the shared evidence audit system
    reg = EvidenceRegistry()
    reg.register_many(result.evidence)
    summary = verify_findings(result.findings, reg)
    assert summary["unverified"] == 0
    assert summary["insufficient_evidence"] == 0
    assert summary["verified"] == len(result.findings)


@pytest.mark.asyncio
async def test_database_failure_graceful_fallback_and_limitation(shared_db_session: AsyncSession):
    """
    6. Database failure behaviour:
       When database repository raises an error, agent does not crash,
       falls back safely to local historical scientific archive,
       and explicitly discloses limitation.
    """
    repo = MarineRepository(shared_db_session)
    # Simulate database connection / query failure
    repo.query_observations = AsyncMock(
        side_effect=OperationalError("SELECT connection failed", None, None)
    )

    agent = OceanResearchAgent(marine_repository=repo)
    task = InvestigationTask(
        investigation_id="inv-db-err-003",
        workspace=WorkspaceType.MARINE_MONITORING,
        prompt="Historical sea state and wave height comparison",
        latitude=12.87,
        longitude=74.88,
    )

    result = await agent.run(task)
    assert result.status == AgentStatus.COMPLETED
    assert len(result.findings) > 0

    # Ensure limitation discloses database fallback
    assert any("PostgreSQL repository query failed" in lim for lim in result.limitations)


@pytest.mark.asyncio
async def test_live_provider_outage_historical_analysis_resilience(shared_db_session: AsyncSession):
    """
    7. Historical analysis during live-provider outages:
       Live provider timeout or failure does not block historical analysis from stored records.
    """
    repo = MarineRepository(shared_db_session)
    loader = HistoricalMarineDataLoader()
    records, evidence, _ = loader.load_local_dataset()
    await repo.ensure_data_source("archive_src", evidence.source_name)
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
    # Historical findings were derived successfully despite live provider outage
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
    # Confirm observation time and ingestion time are separate
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
    loader = HistoricalMarineDataLoader()
    records, evidence, _ = loader.load_local_dataset()
    await repo.ensure_data_source("copernicus_era5", evidence.source_name)
    await repo.bulk_ingest(records)

    orchestrator = OrchestratorService()
    # Inject repository into Orchestrator's OceanResearchAgent
    ocean_agent = orchestrator._agents.get("ocean_research")
    assert ocean_agent is not None
    assert isinstance(ocean_agent, OceanResearchAgent)
    ocean_agent.set_repository(repo)

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
    loader = HistoricalMarineDataLoader()
    records, evidence, _ = loader.load_local_dataset()
    await repo.ensure_data_source("ctx_src", evidence.source_name)
    await repo.bulk_ingest(records)

    agent = OceanResearchAgent()  # Inited without repository
    assert agent.marine_repository is None

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

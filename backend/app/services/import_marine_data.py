import asyncio
import sys
from typing import Any

from app.core.logging import logger
from app.db.repositories.marine import MarineRepository
from app.db.session import AsyncSessionLocal
from app.providers.data.historical_marine import HistoricalMarineDataLoader


async def import_historical_marine_data(dataset_path: str | None = None) -> dict[str, Any]:
    """
    Executes idempotent bulk ingestion of the offline sample reference fixture
    into the shared PostgreSQL database via MarineRepository.
    Records carry is_sample_fixture=True and are excluded from normal production queries.
    """
    loader = HistoricalMarineDataLoader(default_data_path=dataset_path)
    records, evidence, counts = loader.load_local_dataset()

    logger.info(
        f"Loaded {counts['valid']} valid historical records from {loader.data_path} "
        f"({counts['rejected']} rejected out of {counts['processed']} total)."
    )

    try:
        async with AsyncSessionLocal() as session:
            repo = MarineRepository(session)
            # Ensure canonical data source registration matching record source_id
            canonical_source_id = "historical_archive"
            await repo.ensure_data_source(
                source_id=canonical_source_id,
                name=evidence.source_name,
                base_url=evidence.source_uri,
                description="Curated seasonal reference sample archive for regional marine baseline testing",
                license_info=evidence.metadata.get("license"),
            )
            # Execute idempotent bulk upsert
            ingest_summary = await repo.bulk_ingest(records)

            logger.info(
                f"Ingestion complete: {ingest_summary['processed']} processed, "
                f"{ingest_summary['inserted']} newly inserted, "
                f"{ingest_summary['updated']} updated/deduplicated, "
                f"{ingest_summary['failed']} failed."
            )

            status = "failed" if ingest_summary["failed"] > 0 else "success"
            return {
                "dataset_path": str(loader.data_path),
                "loaded_counts": counts,
                "ingest_summary": ingest_summary,
                "status": status,
            }
    except Exception as e:
        logger.error(f"Database ingestion failed: {e}")
        return {
            "dataset_path": str(loader.data_path),
            "loaded_counts": counts,
            "error": str(e),
            "status": "failed",
        }


async def import_marine_archive_data(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """
    Fetches genuine historical marine observations from Open-Meteo Marine API
    and ingests them idempotently into the shared PostgreSQL database.
    """
    loader = HistoricalMarineDataLoader()
    records, evidence, limitations = await loader.fetch_marine_archive(
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
    )
    if not records or not evidence:
        return {
            "status": "failed",
            "error": "Failed to retrieve records from Open-Meteo Marine Historical Archive",
            "limitations": limitations,
        }

    try:
        async with AsyncSessionLocal() as session:
            repo = MarineRepository(session)
            await repo.ensure_data_source(
                source_id="open_meteo_marine_archive",
                name=evidence.source_name,
                base_url=evidence.source_uri,
                description="Open-Meteo Marine historical oceanographic reanalysis/hindcast",
                license_info=evidence.metadata.get("license"),
            )
            ingest_summary = await repo.bulk_ingest(records)
            status = "failed" if ingest_summary["failed"] > 0 else "success"
            return {
                "source_id": "open_meteo_marine_archive",
                "sample_count": len(records),
                "ingest_summary": ingest_summary,
                "status": status,
                "limitations": limitations,
            }
    except Exception as e:
        logger.error(f"Database ingestion of marine archive failed: {e}")
        return {
            "source_id": "open_meteo_marine_archive",
            "error": str(e),
            "status": "failed",
        }


# Explicit alias separating fixture/demo ingestion from genuine reanalysis
import_sample_fixture_data = import_historical_marine_data


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    result = asyncio.run(import_historical_marine_data(path))
    print("\n--- Marine Data Ingestion Summary ---")
    for k, v in result.items():
        print(f"  {k}: {v}")
    if result.get("status") != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()

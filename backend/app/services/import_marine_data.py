import asyncio
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.core.logging import logger
from app.db.session import AsyncSessionLocal
from app.db.repositories.marine import MarineRepository
from app.providers.data.historical_marine import HistoricalMarineDataLoader


async def import_historical_marine_data(dataset_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes idempotent bulk ingestion of the validated historical marine scientific dataset
    into the shared PostgreSQL database via MarineRepository.
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
            # Ensure data source registration
            await repo.ensure_data_source(
                source_id="copernicus_marine_era5",
                name=evidence.source_name,
                base_url=evidence.source_uri,
                description="Validated multi-season reanalysis archive (SST, waves, currents, wind)",
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
            return {
                "dataset_path": str(loader.data_path),
                "loaded_counts": counts,
                "ingest_summary": ingest_summary,
                "status": "success",
            }
    except Exception as e:
        logger.error(f"Database ingestion failed: {e}")
        return {
            "dataset_path": str(loader.data_path),
            "loaded_counts": counts,
            "error": str(e),
            "status": "failed",
        }


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

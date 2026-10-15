from typing import Dict, List, Optional
from app.schemas.evidence import EvidenceRecord

class EvidenceRegistry:
    """
    Central registry for tracking and resolving evidence records during investigations.
    Can operate in-memory during orchestration and sync with database persistence.
    """
    def __init__(self):
        self._records: Dict[str, EvidenceRecord] = {}

    def register(self, record: EvidenceRecord) -> EvidenceRecord:
        self._records[record.id] = record
        return record

    def register_many(self, records: List[EvidenceRecord]) -> List[EvidenceRecord]:
        for r in records:
            self.register(r)
        return records

    def get(self, evidence_id: str) -> Optional[EvidenceRecord]:
        return self._records.get(evidence_id)

    def list_all(self) -> List[EvidenceRecord]:
        return list(self._records.values())

    def clear(self) -> None:
        self._records.clear()

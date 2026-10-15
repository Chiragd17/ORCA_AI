from typing import List, Dict, Any
from app.schemas.evidence import Finding, EvidenceRecord, VerificationStatus
from app.evidence.registry import EvidenceRegistry

def verify_findings(findings: List[Finding], registry: EvidenceRegistry) -> Dict[str, Any]:
    """
    Deterministically evaluates a list of findings against the evidence registry.
    Returns verification summary metrics and updates finding verification statuses.
    """
    total = len(findings)
    verified_count = 0
    unverified_count = 0
    insufficient_count = 0

    for finding in findings:
        if not finding.evidence_ids:
            finding.verification_status = VerificationStatus.INSUFFICIENT_EVIDENCE
            insufficient_count += 1
            continue

        # Check if all referenced evidence records exist
        missing_ids = [eid for eid in finding.evidence_ids if not registry.get(eid)]
        if missing_ids:
            finding.verification_status = VerificationStatus.INSUFFICIENT_EVIDENCE
            insufficient_count += 1
        else:
            finding.verification_status = VerificationStatus.VERIFIED
            verified_count += 1

    return {
        "total_findings": total,
        "verified": verified_count,
        "unverified": unverified_count,
        "insufficient_evidence": insufficient_count,
        "verification_rate": (verified_count / total) if total > 0 else 0.0,
    }

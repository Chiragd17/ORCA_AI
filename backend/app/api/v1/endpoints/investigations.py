from typing import List
from fastapi import APIRouter, HTTPException, Path
from app.schemas.investigations import (
    InvestigationCreateRequest,
    InvestigationResponse,
    ExecutionEvent,
    InvestigationReportResponse,
)
from app.schemas.evidence import EvidenceRecord
from app.orchestrator.service import orchestrator_service
from app.evidence.verification import verify_findings

router = APIRouter()

@router.post("", response_model=InvestigationResponse, tags=["Investigations"])
async def create_investigation(request: InvestigationCreateRequest):
    """
    Initiates an investigation across relevant specialist agents through the Orchestrator.
    """
    result = await orchestrator_service.execute_investigation(request)
    return result

@router.get("/{investigation_id}", response_model=InvestigationResponse, tags=["Investigations"])
async def get_investigation(
    investigation_id: str = Path(..., description="Unique investigation identifier")
):
    """
    Retrieves current state and findings for an investigation.
    """
    inv = orchestrator_service.get_investigation(investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return inv

@router.get("/{investigation_id}/events", response_model=List[ExecutionEvent], tags=["Investigations"])
async def get_investigation_events(
    investigation_id: str = Path(..., description="Unique investigation identifier")
):
    """
    Returns the genuine execution event stream emitted during an investigation.
    """
    bus = orchestrator_service.get_event_bus(investigation_id)
    return bus.get_events()

@router.get("/{investigation_id}/evidence", response_model=List[EvidenceRecord], tags=["Investigations"])
async def get_investigation_evidence(
    investigation_id: str = Path(..., description="Unique investigation identifier")
):
    """
    Returns all supporting evidence records registered during the investigation.
    """
    reg = orchestrator_service.get_evidence_registry(investigation_id)
    return reg.list_all()

@router.get("/{investigation_id}/report", response_model=InvestigationReportResponse, tags=["Investigations"])
async def get_investigation_report(
    investigation_id: str = Path(..., description="Unique investigation identifier")
):
    """
    Returns a structured scientific report with claims, evidence links, and verification status.
    """
    inv = orchestrator_service.get_investigation(investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")

    reg = orchestrator_service.get_evidence_registry(investigation_id)
    v_summary = verify_findings(inv.findings, reg)

    return InvestigationReportResponse(
        investigation_id=inv.id,
        workspace=inv.workspace,
        title=f"ORCA Scientific Investigation Report: {inv.workspace.value.replace('_', ' ').title()}",
        summary=inv.final_answer or "No summary available.",
        findings=inv.findings,
        evidence=reg.list_all(),
        verification_summary=v_summary,
        limitations=inv.limitations,
        generated_at=inv.completed_at or inv.created_at,
    )

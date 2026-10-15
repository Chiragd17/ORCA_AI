from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class InvestigationModel(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace: Mapped[str] = mapped_column(String(64), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)  # queued, running, completed, failed
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    target_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    final_answer: Mapped[Optional[str]] = mapped_column(Text)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    events: Mapped[List["InvestigationEventModel"]] = relationship(
        "InvestigationEventModel", back_populates="investigation", cascade="all, delete-orphan"
    )
    findings: Mapped[List["InvestigationFindingModel"]] = relationship(
        "InvestigationFindingModel", back_populates="investigation", cascade="all, delete-orphan"
    )

class InvestigationEventModel(Base):
    __tablename__ = "investigation_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(64))
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    investigation: Mapped["InvestigationModel"] = relationship("InvestigationModel", back_populates="events")

class InvestigationFindingModel(Base):
    __tablename__ = "investigation_findings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), index=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    claim: Mapped[str] = mapped_column(Text)
    value: Mapped[Optional[str]] = mapped_column(Text)
    unit: Mapped[Optional[str]] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(64))
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    uncertainty: Mapped[Optional[str]] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    investigation: Mapped["InvestigationModel"] = relationship("InvestigationModel", back_populates="findings")

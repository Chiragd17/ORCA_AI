from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Float, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class EvidenceRecordModel(Base):
    __tablename__ = "evidence_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_name: Mapped[str] = mapped_column(String(128), index=True)
    source_uri: Mapped[str] = mapped_column(String(512))
    observation_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    retrieval_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    data_type: Mapped[str] = mapped_column(String(64), index=True)
    raw_value: Mapped[Optional[str]] = mapped_column(Text)
    unit: Mapped[Optional[str]] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

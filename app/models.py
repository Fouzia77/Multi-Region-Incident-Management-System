"""
SQLAlchemy ORM models for the incidents table.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="OPEN")
    severity = Column(String(50), nullable=False)
    assigned_team = Column(String(100), nullable=True)
    vector_clock = Column(JSONB, nullable=False)
    version_conflict = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

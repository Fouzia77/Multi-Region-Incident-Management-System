"""
Pydantic schemas for request validation and response serialization.
"""
from __future__ import annotations
from typing import Optional, Dict
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


# ─── Shared ────────────────────────────────────────────────────────────────────

VectorClockSchema = Dict[str, int]


# ─── Incident ──────────────────────────────────────────────────────────────────

class IncidentCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    severity: str = Field(..., max_length=50)


class IncidentUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(None, max_length=50)
    severity: Optional[str] = Field(None, max_length=50)
    assigned_team: Optional[str] = Field(None, max_length=100)
    vector_clock: VectorClockSchema  # REQUIRED: client must send their current clock


class IncidentResolve(BaseModel):
    status: Optional[str] = Field(None, max_length=50)
    assigned_team: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None


class IncidentResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    status: str
    severity: str
    assigned_team: Optional[str]
    vector_clock: VectorClockSchema
    version_conflict: bool
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Replication ───────────────────────────────────────────────────────────────

class ReplicateRequest(BaseModel):
    """Full incident payload sent from one region to another for replication."""
    id: UUID
    title: str
    description: Optional[str]
    status: str
    severity: str
    assigned_team: Optional[str]
    vector_clock: VectorClockSchema
    version_conflict: bool
    updated_at: datetime

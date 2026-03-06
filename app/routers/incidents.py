"""
Incidents router — public-facing API endpoints.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.database import get_db
from app.models import Incident
from app.schemas import IncidentCreate, IncidentUpdate, IncidentResolve, IncidentResponse
from app.vector_clock import new_clock, increment, compare, merge, ClockRelation

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _to_response(incident: Incident) -> IncidentResponse:
    return IncidentResponse(
        id=incident.id,
        title=incident.title,
        description=incident.description,
        status=incident.status,
        severity=incident.severity,
        assigned_team=incident.assigned_team,
        vector_clock=incident.vector_clock,
        version_conflict=incident.version_conflict,
        updated_at=incident.updated_at,
    )


# ─── Create ────────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=IncidentResponse)
async def create_incident(payload: IncidentCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new incident in this region.
    Initialises the vector clock with local counter = 1, all others = 0.
    """
    vc = new_clock()
    vc = increment(vc, config.REGION_ID)  # {"us":1,"eu":0,"apac":0}

    incident = Incident(
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        status="OPEN",
        assigned_team=None,
        vector_clock=vc,
        version_conflict=False,
    )
    db.add(incident)
    await db.flush()
    await db.refresh(incident)
    return _to_response(incident)


# ─── Read one ──────────────────────────────────────────────────────────────────

@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _to_response(incident)


# ─── List all ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[IncidentResponse])
async def list_incidents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Incident).order_by(Incident.updated_at.desc()))
    return [_to_response(i) for i in result.scalars().all()]


# ─── Update ────────────────────────────────────────────────────────────────────

@router.put("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: UUID,
    payload: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update an incident.

    The request MUST include the vector_clock the client last saw.
    - If the request clock is BEFORE the stored clock → reject with 409 (stale update).
    - Otherwise accept, increment local clock, and save.
    """
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    relation = compare(payload.vector_clock, incident.vector_clock)

    if relation == ClockRelation.BEFORE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Stale update rejected",
                "reason": "The provided vector_clock is causally BEFORE the current stored version.",
                "stored_clock": incident.vector_clock,
                "provided_clock": payload.vector_clock,
            },
        )

    # Accept the update — merge clocks then increment local counter
    merged_vc = merge(payload.vector_clock, incident.vector_clock)
    new_vc = increment(merged_vc, config.REGION_ID)

    if payload.title is not None:
        incident.title = payload.title
    if payload.description is not None:
        incident.description = payload.description
    if payload.status is not None:
        incident.status = payload.status
    if payload.severity is not None:
        incident.severity = payload.severity
    if payload.assigned_team is not None:
        incident.assigned_team = payload.assigned_team

    incident.vector_clock = new_vc
    incident.version_conflict = False  # cleared on explicit update

    await db.flush()
    await db.refresh(incident)
    return _to_response(incident)


# ─── Resolve conflict ──────────────────────────────────────────────────────────

@router.post("/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_conflict(
    incident_id: UUID,
    payload: IncidentResolve,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually resolve a version conflict.
    - Updates the incident with the supplied fields.
    - Clears the version_conflict flag.
    - Increments the local vector clock to mark the resolution event.
    """
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    if not incident.version_conflict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incident does not have an active version conflict.",
        )

    if payload.status is not None:
        incident.status = payload.status
    if payload.assigned_team is not None:
        incident.assigned_team = payload.assigned_team
    if payload.description is not None:
        incident.description = payload.description

    incident.version_conflict = False
    incident.vector_clock = increment(incident.vector_clock, config.REGION_ID)

    await db.flush()
    await db.refresh(incident)
    return _to_response(incident)

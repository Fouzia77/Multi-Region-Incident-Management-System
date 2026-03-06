"""
Internal replication endpoint — receives incident data from peer regions.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Incident
from app.schemas import ReplicateRequest
from app.vector_clock import compare, merge, ClockRelation

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/replicate", status_code=status.HTTP_200_OK)
async def replicate(payload: ReplicateRequest, db: AsyncSession = Depends(get_db)):
    """
    Receive a replicated incident from a peer region.

    Vector clock comparison logic:
    - vc_in AFTER  vc_local → overwrite local record with incoming data, merge clocks
    - vc_in BEFORE vc_local → incoming data is stale, ignore it
    - vc_in EQUAL  vc_local → already have this exact version, ignore (idempotent)
    - vc_in CONCURRENT     → conflict! keep local version but set version_conflict=True, merge clocks
    """
    result = await db.execute(select(Incident).where(Incident.id == payload.id))
    local = result.scalar_one_or_none()

    vc_in = payload.vector_clock

    if local is None:
        # We've never seen this incident — accept it as-is
        incident = Incident(
            id=payload.id,
            title=payload.title,
            description=payload.description,
            status=payload.status,
            severity=payload.severity,
            assigned_team=payload.assigned_team,
            vector_clock=vc_in,
            version_conflict=payload.version_conflict,
        )
        db.add(incident)
        return {"action": "created"}

    vc_local = local.vector_clock
    relation = compare(vc_in, vc_local)

    if relation == ClockRelation.BEFORE or relation == ClockRelation.EQUAL:
        # Incoming is stale or identical — safe to ignore (idempotency guaranteed)
        return {"action": "ignored", "reason": relation.value}

    elif relation == ClockRelation.AFTER:
        # Incoming is newer — overwrite
        local.title = payload.title
        local.description = payload.description
        local.status = payload.status
        local.severity = payload.severity
        local.assigned_team = payload.assigned_team
        local.vector_clock = merge(vc_in, vc_local)
        local.version_conflict = payload.version_conflict
        return {"action": "overwritten"}

    else:  # CONCURRENT
        # Conflict detected — keep our local version, flag it
        local.vector_clock = merge(vc_in, vc_local)
        local.version_conflict = True
        return {"action": "conflict_flagged"}

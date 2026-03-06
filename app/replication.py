"""
Background replication worker.

Runs every REPLICATION_INTERVAL seconds. For each peer region URL,
attempts to replicate all local incidents to that peer's /internal/replicate endpoint.

Design notes:
- Replication is idempotent: peers ignore BEFORE/EQUAL clocks, so repeated sends are safe.
- Errors are caught per-peer so one failing peer doesn't block the others.
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app import config
from app.database import AsyncSessionLocal
from app.models import Incident

logger = logging.getLogger(__name__)


def _incident_to_dict(incident: Incident) -> dict:
    return {
        "id": str(incident.id),
        "title": incident.title,
        "description": incident.description,
        "status": incident.status,
        "severity": incident.severity,
        "assigned_team": incident.assigned_team,
        "vector_clock": incident.vector_clock,
        "version_conflict": incident.version_conflict,
        "updated_at": incident.updated_at.isoformat() if incident.updated_at else datetime.now(timezone.utc).isoformat(),
    }


async def replicate_to_peer(peer_url: str, incidents: list[dict]) -> None:
    """Send all incidents to a single peer's /internal/replicate endpoint."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        for incident_data in incidents:
            try:
                resp = await client.post(
                    f"{peer_url}/internal/replicate",
                    json=incident_data,
                )
                if resp.status_code not in (200, 201):
                    logger.warning(
                        "Replication to %s returned %s: %s",
                        peer_url, resp.status_code, resp.text[:200],
                    )
            except httpx.RequestError as exc:
                logger.warning("Replication to %s failed: %s", peer_url, exc)


async def replication_worker() -> None:
    """
    Periodically replicate all local incidents to all peer regions.
    Runs forever as a background task.
    """
    logger.info(
        "[Replication Worker] started for region=%s, peers=%s, interval=%ds",
        config.REGION_ID,
        config.PEER_URLS,
        config.REPLICATION_INTERVAL,
    )

    while True:
        await asyncio.sleep(config.REPLICATION_INTERVAL)

        if not config.PEER_URLS:
            continue

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Incident))
                incidents = [_incident_to_dict(i) for i in result.scalars().all()]

            if not incidents:
                continue

            tasks = [
                replicate_to_peer(peer_url, incidents)
                for peer_url in config.PEER_URLS
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.debug(
                "[Replication Worker] pushed %d incidents to %d peers",
                len(incidents), len(config.PEER_URLS),
            )

        except Exception as exc:
            logger.error("[Replication Worker] unexpected error: %s", exc)

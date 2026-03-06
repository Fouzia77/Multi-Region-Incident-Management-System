"""
Main FastAPI application entry point.
"""
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app import config
from app.database import init_db
from app.replication import replication_worker
from app.routers import incidents, internal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: initialise DB tables and launch background replication worker.
    Shutdown: worker task is cancelled automatically.
    """
    logger.info("Starting region service: %s", config.REGION_ID)
    await init_db()
    task = asyncio.create_task(replication_worker())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=f"Incident Management — Region {config.REGION_ID.upper()}",
    description="Distributed multi-region incident management with vector clocks.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(incidents.router)
app.include_router(internal.router)


@app.get("/health", tags=["health"])
async def health():
    """Health check endpoint used by Docker and load balancers."""
    return {"status": "healthy", "region": config.REGION_ID}

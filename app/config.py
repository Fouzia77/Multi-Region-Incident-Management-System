"""
Application configuration loaded from environment variables.
"""
import os

# Identity of this region: "us", "eu", or "apac"
REGION_ID: str = os.environ.get("REGION_ID", "us")

# Comma-separated URLs of the other two peer region services
# e.g. "http://region-eu:8000,http://region-apac:8000"
_peer_urls_raw: str = os.environ.get("PEER_URLS", "")
PEER_URLS: list[str] = [u.strip() for u in _peer_urls_raw.split(",") if u.strip()]

# How often (in seconds) the background replication worker runs
REPLICATION_INTERVAL: int = int(os.environ.get("REPLICATION_INTERVAL", "5"))

# Database URL (asyncpg-compatible)
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    f"postgresql+asyncpg://postgres:postgres@db-{REGION_ID}:5432/incidents",
)

# Multi-Region Incident Management System

A distributed backend for a multi-region incident management platform that guarantees **causal ordering** using **vector clocks**. Built with Python/FastAPI and PostgreSQL, orchestrated entirely via Docker Compose.

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                      Docker Compose Network                      │
│                                                                  │
│  ┌─────────────────┐   ┌─────────────────┐  ┌─────────────────┐│
│  │   region-us     │   │   region-eu     │  │  region-apac    ││
│  │  :8001          │◄──►  :8002          │◄─►  :8003          ││
│  │  (FastAPI)      │   │  (FastAPI)      │  │  (FastAPI)      ││
│  └────────┬────────┘   └────────┬────────┘  └────────┬────────┘│
│           │                     │                    │          │
│  ┌────────▼────────┐   ┌────────▼────────┐  ┌───────▼────────┐│
│  │    db-us        │   │    db-eu        │  │   db-apac      ││
│  │  (PostgreSQL)   │   │  (PostgreSQL)   │  │  (PostgreSQL)  ││
│  └─────────────────┘   └─────────────────┘  └────────────────┘│
└────────────────────────────────────────────────────────────────┘
```

Each region service:
- Has its **own isolated PostgreSQL database**
- Exposes public endpoints for incident management
- Exposes an **internal replication endpoint** for peer-to-peer sync
- Runs a **background replication worker** that pushes updates to peers every 5 seconds

---

## Vector Clocks

Vector clocks track the causal history of each incident across regions.

```
Format:  {"us": <int>, "eu": <int>, "apac": <int>}
Example: {"us": 2, "eu": 1, "apac": 0}
```

### Operations

| Operation | Description |
|-----------|-------------|
| **Increment** | On local create/update: `vc[region_id] += 1` |
| **Compare**   | Determine causal relationship (BEFORE/AFTER/EQUAL/CONCURRENT) |
| **Merge**     | `merged[i] = max(vc1[i], vc2[i])` — combines causal knowledge |

### Comparison Rules

- **BEFORE**: All entries in `vc1 ≤ vc2`, and at least one is strictly less
- **AFTER**: All entries in `vc1 ≥ vc2`, and at least one is strictly greater
- **EQUAL**: All entries are identical
- **CONCURRENT**: Neither BEFORE nor AFTER — a **conflict** has occurred

---

## Quick Start

### Prerequisites
- Docker and Docker Compose
- `curl` and `jq` (for the simulation script)

### Run

```bash
git clone <repo-url>
cd Multi-Region-Incident-Management-System
docker-compose up --build
```

All 6 services (3 app + 3 DB) will start automatically. Wait ~60 seconds for all health checks to pass.

### Service URLs

| Service     | URL                   | Region |
|-------------|----------------------|--------|
| region-us   | http://localhost:8001 | US     |
| region-eu   | http://localhost:8002 | EU     |
| region-apac | http://localhost:8003 | APAC   |

---

## API Reference

### `POST /incidents`
Create a new incident.

```bash
curl -X POST http://localhost:8001/incidents \
  -H "Content-Type: application/json" \
  -d '{"title":"DB Outage","description":"Primary DB unreachable","severity":"HIGH"}'
```

**Response (201):**
```json
{
  "id": "uuid-here",
  "title": "DB Outage",
  "status": "OPEN",
  "severity": "HIGH",
  "vector_clock": {"us": 1, "eu": 0, "apac": 0},
  "version_conflict": false,
  ...
}
```

---

### `GET /incidents/{id}`
Fetch a single incident by ID.

---

### `GET /incidents`
List all incidents (newest first).

---

### `PUT /incidents/{id}`
Update an incident. **Must include** the `vector_clock` from your last read.

```bash
curl -X PUT http://localhost:8001/incidents/<id> \
  -H "Content-Type: application/json" \
  -d '{"status":"ACKNOWLEDGED","assigned_team":"SRE-US","vector_clock":{"us":1,"eu":0,"apac":0}}'
```

- Returns **200** with updated clock if accepted
- Returns **409** if the provided clock is causally BEFORE the stored version (stale update)

---

### `POST /incidents/{id}/resolve`
Resolve a version conflict.

```bash
curl -X POST http://localhost:8001/incidents/<id>/resolve \
  -H "Content-Type: application/json" \
  -d '{"status":"RESOLVED","assigned_team":"SRE-Managers"}'
```

---

### `POST /internal/replicate`
Internal endpoint — called by peer regions to propagate updates.

```bash
curl -X POST http://localhost:8002/internal/replicate \
  -H "Content-Type: application/json" \
  -d '<full-incident-json>'
```

---

### `GET /health`
Health check endpoint used by Docker and load balancers.

---

## Conflict Detection

### Scenario

1. US creates incident → `vc = {"us":1,"eu":0,"apac":0}`
2. Incident replicates to EU
3. **Partition begins**
4. US updates → `vc = {"us":2,"eu":0,"apac":0}`
5. EU updates (concurrently) → `vc = {"us":1,"eu":1,"apac":0}`
6. **Partition heals** — US replicates to EU
7. EU's `/internal/replicate` compares `{"us":2,...}` vs `{"us":1,"eu":1,...}`
   - Neither is BEFORE the other → **CONCURRENT** → `version_conflict = true`

---

## Partition Simulation Script

```bash
chmod +x simulate_partition.sh
./simulate_partition.sh
```

The script:
1. Creates an incident in `region-us`
2. Waits for replication
3. Makes concurrent updates to `region-us` and `region-eu`
4. Triggers replication (simulating partition heal)
5. Prints the conflicted incident showing `"version_conflict": true`

---

## Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Key variables:

| Variable | Description |
|----------|-------------|
| `REGION_ID` | Region identifier (`us`, `eu`, `apac`) |
| `DATABASE_URL` | PostgreSQL connection string (asyncpg format) |
| `PEER_URLS` | Comma-separated URLs of other region services |
| `REPLICATION_INTERVAL` | Seconds between background replication pushes (default: 5) |

---

## Database Schema

```sql
CREATE TABLE incidents (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title            VARCHAR(255) NOT NULL,
    description      TEXT,
    status           VARCHAR(50) NOT NULL DEFAULT 'OPEN',
    severity         VARCHAR(50) NOT NULL,
    assigned_team    VARCHAR(100),
    vector_clock     JSONB NOT NULL DEFAULT '{}',
    version_conflict BOOLEAN NOT NULL DEFAULT false,
    updated_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

---

## Project Structure

```
.
├── app/
│   ├── main.py           # FastAPI app, lifespan, middleware
│   ├── config.py         # Environment variable configuration
│   ├── database.py       # Async SQLAlchemy engine & session
│   ├── models.py         # ORM model for incidents
│   ├── schemas.py        # Pydantic request/response schemas
│   ├── vector_clock.py   # Vector clock operations (core logic)
│   ├── replication.py    # Background async replication worker
│   └── routers/
│       ├── incidents.py  # Public API endpoints
│       └── internal.py   # Internal replication endpoint
├── db/
│   └── init.sql          # PostgreSQL schema initialization
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── simulate_partition.sh
└── README.md
```

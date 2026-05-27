"""
Run with:
uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.failsafe import failsafe_loop
from api.routers import alerts, devices, monitor, quarantine, reports, zones
from api.store import add_device, add_zone, get_all_devices, get_all_zones

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def seed_zones() -> None:
    if get_all_zones():
        return

    now = datetime.now(timezone.utc)
    default_zones = [
        {
            "name": "Production Floor",
            "description": "Industrial control and production systems.",
            "subnet": "10.0.10.0/24",
            "ip_range_start": "10.0.10.1",
            "ip_range_end": "10.0.10.254",
        },
        {
            "name": "Admin Network",
            "description": "Administrative workstations and services.",
            "subnet": "10.0.20.0/24",
            "ip_range_start": "10.0.20.1",
            "ip_range_end": "10.0.20.254",
        },
        {
            "name": "Warehouse",
            "description": "Warehouse sensors, scanners, and telemetry hubs.",
            "subnet": "10.0.30.0/24",
            "ip_range_start": "10.0.30.1",
            "ip_range_end": "10.0.30.254",
        },
        {
            "name": "HVAC",
            "description": "Building controls and HVAC gateways.",
            "subnet": "10.0.40.0/24",
            "ip_range_start": "10.0.40.1",
            "ip_range_end": "10.0.40.254",
        },
    ]

    for zone in default_zones:
        add_zone(
            {
                "id": str(uuid4()),
                **zone,
                "device_count": 0,
                "created_at": now,
            }
        )


def seed_devices() -> None:
    if get_all_devices():
        return

    now = datetime.now(timezone.utc)
    mock_devices = [
        {
            "id": str(uuid4()),
            "name": "PLC Controller A1",
            "ip_address": "10.0.10.21",
            "zone": "Production Floor",
            "status": "normal",
            "last_seen": now,
            "anomaly_score": 0.03,
        },
        {
            "id": str(uuid4()),
            "name": "Admin Workstation 02",
            "ip_address": "10.0.20.14",
            "zone": "Admin Network",
            "status": "normal",
            "last_seen": now,
            "anomaly_score": 0.08,
        },
        {
            "id": str(uuid4()),
            "name": "Warehouse Sensor 7",
            "ip_address": "10.0.30.45",
            "zone": "Warehouse",
            "status": "anomaly",
            "last_seen": now,
            "anomaly_score": 0.81,
        },
        {
            "id": str(uuid4()),
            "name": "HVAC Gateway 3",
            "ip_address": "10.0.40.9",
            "zone": "HVAC",
            "status": "quarantined",
            "last_seen": now,
            "anomaly_score": 0.97,
        },
        {
            "id": str(uuid4()),
            "name": "Forklift Telemetry Hub",
            "ip_address": "10.0.30.72",
            "zone": "Warehouse",
            "status": "anomaly",
            "last_seen": now,
            "anomaly_score": 0.66,
        },
    ]

    for device in mock_devices:
        add_device(device)


@asynccontextmanager
async def lifespan(_: FastAPI):
    seed_zones()
    seed_devices()
    task = asyncio.create_task(failsafe_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="IoT Anomaly Detection API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/demo/trigger-anomaly")
def trigger_demo_anomaly() -> dict[str, str]:
    return monitor.trigger_demo_anomaly()


app.include_router(devices.router)
app.include_router(monitor.router)
app.include_router(alerts.router)
app.include_router(quarantine.router)
app.include_router(reports.router)
app.include_router(zones.router)

# ---- Serve Stitch frontend ----
# Mount static assets (JS, CSS, images) at /frontend
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


@app.get("/app/{rest_of_path:path}")
def serve_frontend(rest_of_path: str = "") -> FileResponse:
    """Serve the Stitch-exported HTML. Open http://localhost:8000/app/ in browser."""
    # Check if a specific HTML file was requested
    requested = FRONTEND_DIR / rest_of_path
    if requested.exists() and requested.is_file():
        return FileResponse(str(requested))
    # Default to index.html
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return FileResponse(str(FRONTEND_DIR / "index.html"))

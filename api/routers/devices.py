from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from api.schemas import DeviceCreate, DeviceResponse
from api.store import (
    add_device,
    delete_device,
    find_zone_for_ip,
    get_all_devices,
    get_device,
)


VALID_STATUSES = {"normal", "anomaly", "quarantined"}

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/", response_model=list[DeviceResponse])
def list_devices(status: str | None = Query(default=None)) -> list[DeviceResponse]:
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status filter.")

    devices = get_all_devices()
    if status is not None:
        devices = [device for device in devices if device["status"] == status]

    return [DeviceResponse(**device) for device in devices]


@router.post("/", response_model=DeviceResponse)
def create_device(device: DeviceCreate) -> DeviceResponse:
    now = datetime.now(timezone.utc)
    matched_zone = find_zone_for_ip(device.ip_address)
    stored_device = add_device(
        {
            "id": str(uuid4()),
            "name": device.name,
            "ip_address": device.ip_address,
            "zone": matched_zone["name"] if matched_zone is not None else device.zone,
            "status": "normal",
            "last_seen": now,
            "anomaly_score": 0.0,
        }
    )
    return DeviceResponse(**stored_device)


@router.post("/import")
async def import_devices(file: UploadFile = File(...)) -> dict[str, int]:
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))

    required_columns = {"name", "ip_address", "zone"}
    if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
        raise HTTPException(
            status_code=400,
            detail="CSV must include name, ip_address, and zone columns.",
        )

    imported = 0
    skipped = 0

    for row in reader:
        name = (row.get("name") or "").strip()
        ip_address = (row.get("ip_address") or "").strip()
        zone = (row.get("zone") or "").strip()

        if not name or not ip_address or not zone:
            skipped += 1
            continue

        matched_zone = find_zone_for_ip(ip_address)

        add_device(
            {
                "id": str(uuid4()),
                "name": name,
                "ip_address": ip_address,
                "zone": matched_zone["name"] if matched_zone is not None else zone,
                "status": "normal",
                "last_seen": datetime.now(timezone.utc),
                "anomaly_score": 0.0,
            }
        )
        imported += 1

    return {"imported": imported, "skipped": skipped}


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device_by_id(device_id: str) -> DeviceResponse:
    device = get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found.")
    return DeviceResponse(**device)


@router.delete("/{device_id}")
def remove_device(device_id: str) -> dict[str, bool]:
    deleted = delete_device(device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found.")
    return {"deleted": True}

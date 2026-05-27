from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from api.schemas import ZoneCreate, ZoneResponse, ZoneUpdate
from api.store import (
    add_zone,
    delete_zone,
    find_zone_for_ip,
    get_all_devices,
    get_all_zones,
    get_zone,
    get_zone_by_name,
    update_zone,
)


router = APIRouter(prefix="/zones", tags=["zones"])


def _validate_zone_inputs(
    subnet: str, ip_range_start: str, ip_range_end: str
) -> tuple[str, str, str]:
    if "/" not in subnet:
        raise HTTPException(status_code=400, detail="Invalid subnet format.")

    try:
        start_ip = ipaddress.ip_address(ip_range_start)
        end_ip = ipaddress.ip_address(ip_range_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid IP range.")

    if start_ip >= end_ip:
        raise HTTPException(
            status_code=400,
            detail="ip_range_start must be lower than ip_range_end.",
        )

    return subnet, str(start_ip), str(end_ip)


def _zone_response(zone: dict[str, object]) -> ZoneResponse:
    device_count = sum(1 for device in get_all_devices() if device["zone"] == zone["name"])
    payload = dict(zone)
    payload["device_count"] = device_count
    return ZoneResponse(**payload)


@router.post("/", response_model=ZoneResponse)
def create_zone(zone: ZoneCreate) -> ZoneResponse:
    subnet, ip_range_start, ip_range_end = _validate_zone_inputs(
        zone.subnet, zone.ip_range_start, zone.ip_range_end
    )
    if get_zone_by_name(zone.name) is not None:
        raise HTTPException(status_code=400, detail="Zone name already exists.")

    created = add_zone(
        {
            "id": str(uuid4()),
            "name": zone.name,
            "description": zone.description,
            "subnet": subnet,
            "ip_range_start": ip_range_start,
            "ip_range_end": ip_range_end,
            "device_count": 0,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return _zone_response(created)


@router.get("/", response_model=list[ZoneResponse])
def list_zones() -> list[ZoneResponse]:
    return [_zone_response(zone) for zone in get_all_zones()]


@router.get("/{zone_id}", response_model=ZoneResponse)
def get_zone_by_id(zone_id: str) -> ZoneResponse:
    zone = get_zone(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found.")
    return _zone_response(zone)


@router.put("/{zone_id}", response_model=ZoneResponse)
def edit_zone(zone_id: str, updates: ZoneUpdate) -> ZoneResponse:
    existing = get_zone(zone_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Zone not found.")

    merged = {
        "name": updates.name if updates.name is not None else existing["name"],
        "description": (
            updates.description if updates.description is not None else existing["description"]
        ),
        "subnet": updates.subnet if updates.subnet is not None else existing["subnet"],
        "ip_range_start": (
            updates.ip_range_start
            if updates.ip_range_start is not None
            else existing["ip_range_start"]
        ),
        "ip_range_end": (
            updates.ip_range_end
            if updates.ip_range_end is not None
            else existing["ip_range_end"]
        ),
    }
    subnet, ip_range_start, ip_range_end = _validate_zone_inputs(
        merged["subnet"], merged["ip_range_start"], merged["ip_range_end"]
    )

    name_conflict = get_zone_by_name(merged["name"])
    if name_conflict is not None and name_conflict["id"] != zone_id:
        raise HTTPException(status_code=400, detail="Zone name already exists.")

    updated = update_zone(
        zone_id,
        {
            "name": merged["name"],
            "description": merged["description"],
            "subnet": subnet,
            "ip_range_start": ip_range_start,
            "ip_range_end": ip_range_end,
        },
    )
    return _zone_response(updated)


@router.delete("/{zone_id}")
def remove_zone(zone_id: str) -> dict[str, bool]:
    zone = get_zone(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found.")

    device_count = sum(1 for device in get_all_devices() if device["zone"] == zone["name"])
    if device_count:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a zone with assigned devices.",
        )

    deleted = delete_zone(zone_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Zone not found.")
    return {"deleted": True}


@router.get("/lookup/{ip_address}")
def lookup_zone_by_ip(ip_address: str) -> ZoneResponse | dict[str, object]:
    zone = find_zone_for_ip(ip_address)
    if zone is None:
        return {"zone": None, "message": "IP not in any zone"}
    return _zone_response(zone)
